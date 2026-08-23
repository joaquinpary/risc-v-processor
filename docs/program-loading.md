# Carga de programa: qué se vacía y qué no

> **Estado: resuelto directamente del RTL y las herramientas ya
> implementadas.** No hizo falta escribir ni sintetizar nada nuevo para este
> punto — el mecanismo de carga, el ensamblador y las cuatro preguntas de la
> consigna ya están resueltos en el diseño; este documento es la lectura
> ordenada de esa evidencia. Fuentes: `debug_unit.v`, `top.v`,
> `instruction_fetch.v`, `instruction_decode.v`, `register.v`, `memory.v`,
> `tools/riscv_debug/{protocol,link,riscv_assembler}.py`,
> `examples/demo_*.s`.

---

## 0. Lo que pide la consigna

**El programa debe:** estar en ensamblador, tener un traductor a lenguaje
máquina, y contar con una instrucción HALT/stop.

**El sistema debe:** permitir programar la memoria de programa por software,
permitir reprogramar dinámicamente, y responder:

- a. ¿Es necesario vaciar la memoria (de datos)?
- b. ¿Y los registros?
- c. ¿Se necesita vaciar el pipeline?
- d. ¿Y la memoria de programa?

*Importante: la carga debe ser por UART, sin resintetizar el procesador.*

Todo esto ya está resuelto en el proyecto. Lo que sigue es explicar **cómo**
y, para las cuatro preguntas, **por qué sí o por qué no** con evidencia del
RTL — no es una decisión de diseño que quede abierta, es la consecuencia
directa de cómo está construida cada pieza de memoria.

---

## 1. El mecanismo: protocolo UART de 5 bytes

`debug_unit.v` es una FSM de 3 estados (`IDLE` / `RUNNING` / `SEND_RESP`) que
recibe tramas de 5 bytes (`tools/riscv_debug/protocol.py`): 1 byte de comando
+ 4 de payload, big-endian. Los comandos relevantes para la carga:

| Código | Comando | Efecto |
|---|---|---|
| `0x03` | RESET | `cpu_reset` en alto 1 ciclo + `imem_addr_reg <= 0` |
| `0x10` | LOAD_INSTR | escribe `payload` en la memoria de programa en `imem_addr_reg` y **auto-incrementa** +4 |
| `0x01` | STEP | avanza el procesador un ciclo |
| `0x02` | RUN | corre libre hasta `cpu_halted` |

Ni RESET ni LOAD_INSTR tocan el bitstream: son escrituras normales a través
de los puertos ya sintetizados (`imem_we_o`/`imem_addr_o`/`imem_data_o` de
`debug_unit` → `instruction_i`/`mem_addr_i`/`ins_write_en_i` de
`instruction_fetch`). La reprogramación dinámica sin resintetizar (el punto
que pide la consigna como "importante") queda cumplida por construcción: es
tráfico UART sobre un diseño que ya está corriendo en la FPGA.

### 1.1 La secuencia real de carga

`DebugLink.load_program()` (`tools/riscv_debug/link.py:237`):

```
RESET  →  LOAD_INSTR × N (una trama por instrucción, con pausa entre tramas)  →  RESET
```

El comentario del propio código explica por qué el primer RESET no es
opcional: **el firmware no recibe la dirección de escritura**, `debug_unit`
la auto-incrementa a partir de `imem_addr_reg`. Sin el RESET inicial, cargar
un segundo programa seguiría escribiendo a partir de donde había quedado el
puntero del anterior, no desde la dirección 0.

---

## 2. a. ¿Es necesario vaciar la memoria de datos?

**No, y además el hardware no puede hacerlo.** En `memory.v`, el `reset` que
llega como puerto del módulo **no está conectado a la BRAM de datos** — se
lee la declaración completa del módulo y el `reset` no aparece en ningún
lado del cuerpo. La instancia de `data_memory` solo tiene `clka/addra/dina/
douta/ena/wea` (puerto A) y su espejo de lectura en el puerto B para el
debug port: no existe una entrada de *clear* global.

Es una limitación real del bloque, no una omisión: un `RAMB36E1` de Xilinx
(lo que hay detrás de `data_memory`, ver
`risc-v-processor.srcs/sources_1/ip/data_memory/`) no tiene un pin de borrado
masivo — solo se escribe posición por posición, con `wea`. "Vaciar la
memoria" en el sentido de resetear su contenido a cero requeriría escribir
cero explícitamente en cada palabra usada, ya sea desde el programa mismo (un
bucle de inicialización al principio) o agregando un comando de borrado al
protocolo — no existe hoy y no es gratis, porque el puerto B del debug (el
único con acceso externo a la memoria de datos) está cableado solo para
lectura (`web = 4'b0000` fijo en `memory.v`).

**Consecuencia práctica:** si se reprograma sin volver a programar la placa
(sin re-configurar el bitstream), la memoria de datos conserva lo que dejó la
ejecución anterior. Un programa nuevo que asuma memoria en cero sin
inicializarla explícitamente puede leer basura del programa anterior.

---

## 3. b. ¿Y los registros?

**Sí, y es automático.** El registro de 32×32 (`register.v`) sí tiene lógica
de *clear* completo:

```verilog
always @(posedge clk) begin
    if (reset) begin
        for (i = 0; i < 32; i = i + 1)
            regs[i] <= 32'b0;
    ...
```

Ese `reset` es el puerto `reset` de `instruction_decode.v`, que en `top.v` se
conecta a `pipeline_reset = sys_reset | cpu_reset`. `cpu_reset` es exactamente
el pulso de un ciclo que genera el comando RESET (`0x03`) del debug_unit. Como
`link.py` manda un RESET antes de cargar y otro después, **los 32 registros
quedan en cero en cada carga de programa**, sin que el usuario tenga que
pedirlo aparte.

Es necesario que sea así: a diferencia de la memoria de datos (donde un
programa razonable puede convivir con basura si inicializa lo que usa), casi
cualquier programa de prueba asume `x1..x31 = 0` al arrancar — los ejemplos
de `examples/` lo asumen todos.

---

## 4. c. ¿Se necesita vaciar el pipeline?

**Sí, y también es automático, con el mismo pulso.** El mismo
`pipeline_reset` que limpia los registros llega, en `top.v`, a **todos** los
niveles de latch:

- `instruction_fetch.v`: `pc_reg <= 0`, `pc_fetched <= 0` (bajo `reset`,
  puerto conectado a `pipeline_reset`).
- IF/ID: `pc_id`, `pc_plus_4_id`, `instruction_id`, `if_id_valid` → todos a
  cero bajo `pipeline_reset`.
- ID/EX, EX/MEM, MEM/WB: mismos bloques `always @(posedge clk_50mhz) if
  (pipeline_reset) ... <= 0` para cada campo, incluido el bus de control
  (`control_bus_ex`, `control_mem`, `control_wb`), que al quedar en cero
  desactiva `RegWrite`/`MemWrite`/etc. de cualquier instrucción que hubiera
  quedado a mitad de camino.

Es imprescindible: sin este vaciado, una instrucción del programa **anterior**
podría seguir viajando por el pipeline en el momento en que empieza a
escribirse el programa **nuevo** en memoria, y terminar escribiendo un
registro o una dirección de memoria con datos que ya no corresponden a nada
que el usuario esperaría. El pulso de RESET del protocolo lo evita porque
llega antes de la primera palabra del programa nuevo.

---

## 5. d. ¿Y la memoria de programa?

**Tampoco se vacía — y acá el diseño ya tuvo que lidiar con la consecuencia.**
Igual que `data_memory`, `instruction_memory` (`instruction_fetch.v`) es una
BRAM sin pin de borrado: el `reset` del módulo solo limpia `pc_reg` y
`pc_fetched`, nunca la instancia de `instruction_memory`. Lo único que hace
el comando RESET sobre la carga de instrucciones es **rebobinar el puntero de
escritura** (`imem_addr_reg <= 0`), no el contenido.

Esto importa porque `LOAD_INSTR` solo escribe tantas palabras como tramas se
manden. Si se carga un programa de 40 palabras y después uno de 20 sin más
cuidado, las direcciones 20 a 39 **conservan las instrucciones del programa
anterior** — y el procesador las va a ejecutar si el flujo de control llega
hasta ahí.

### 5.1 Por qué esto no rompió nada en la práctica: la convención de relleno

Los cinco programas de `examples/demo_*.s` tienen, todos, el mismo comentario
al final:

```asm
# Relleno hasta 28 palabras: asi todos los demos ocupan lo mismo
# y cargar uno sobre otro nunca deja instrucciones del anterior.
        nop
        nop
        nop
        nop
```

Es la solución de facto a esta pregunta: en vez de vaciar la memoria de
programa (que el hardware no permite), **se fija por convención un tamaño
común y se rellena cada programa hasta ese tamaño** con `nop`. Así, cargar
cualquier demo sobre cualquier otro siempre sobreescribe exactamente el mismo
rango de direcciones (palabras 0 a 27), y nunca queda un resto del programa
viejo más allá del nuevo.

Es una disciplina del lado del programa, no una garantía del sistema: si se
carga un programa más largo que 28 palabras y después uno más corto sin
rellenarlo al mismo tamaño, el problema reaparece. Vale la pena decirlo así
de explícito en el informe — es la respuesta completa a la pregunta d, no
solo "no se vacía".

---

## 6. El HALT no es una instrucción real del ISA

La consigna pide que el programa cuente con una instrucción HALT o de stop.
Acá no existe un opcode HALT: se usa la palabra **`0x00000000`** como
centinela de fin de programa, detectada en `top.v`:

```verilog
assign cpu_halted = (instruction_id == 32'b0) && if_id_valid
                                              && (pc_if > 32'h00000010);
```

Dos guardas evitan falsos positivos:

- `if_id_valid` excluye las burbujas de un *flush* (que también valen
  `instruction_id == 0`) — si no estuviera, cualquier salto tomado se
  confundiría con el fin del programa.
- `pc_if > 0x10` evita que los primeros ciclos después de un reset (donde el
  pipeline todavía se está llenando) disparen un halt prematuro.

Importante: el mnemónico `nop` del ensamblador **no** produce este centinela.
`riscv_assembler.py` lo traduce a la instrucción real `addi x0, x0, 0`
(`0x00000013`), que se ejecuta sin efecto pero no detiene el procesador — se
verifica con el propio test embebido del ensamblador
(`check("nop", one("nop"), 0x00000013)`). El halt ocurre cuando la ejecución
llega a una dirección que **nunca fue escrita**: como `instruction_memory`
(1024 palabras, IP sin archivo de inicialización — `Load_Init_File: false`)
arranca en cero tras configurar la FPGA, todo lo que queda después del último
`LOAD_INSTR` de un programa es, por defecto, el centinela de halt — a menos
que ahí hubiera quedado algo de una carga anterior (la misma situación de
§5).

*Responder lo que pide la consigna ("¿qué pasa si en mi memoria no se
encuentra una instrucción de parada?"):* si el flujo de ejecución nunca llega
a una palabra en cero — por ejemplo, porque un salto lo esquiva, o porque hay
basura no nula de una carga anterior en esa región (§5) — `cpu_halted` nunca
se activa. En modo *continuo* el `RUN` no vuelve nunca a `IDLE` (queda
corriendo indefinidamente, y como en `RUNNING` el `debug_unit` ignora la UART
por completo, el enlace queda mudo hasta un reset físico o volver a
programar — el mismo modo de falla que ya se documentó en
[uart-reliability.md](uart-reliability.md) para un RUN fantasma). En modo
*paso a paso* no hay problema equivalente: cada `STEP` contesta con normalidad
sin importar si hay o no instrucción de parada, así que ese modo no se
cuelga — solo hay que saber cuándo dejar de pedir pasos.

---

## 7. Checklist de la consigna

| Pide la consigna | Estado | Dónde |
|---|---|---|
| Programa en ensamblador | ✅ | `examples/*.s` |
| Traductor a lenguaje máquina | ✅ | `tools/riscv_debug/riscv_assembler.py` |
| Instrucción HALT/stop | ✅ (centinela `0x00000000`, no un opcode real) | `top.v` (`cpu_halted`), §6 |
| Programar por software, sin resintetizar | ✅ | `LOAD_INSTR` vía UART, §1 |
| Reprogramación dinámica | ✅ | `RESET → LOAD_INSTR* → RESET`, §1.1 |
| a. ¿Vaciar memoria de datos? | **No** — y el hardware no lo permite (sin pin de *clear*, puerto de debug de solo lectura) | §2 |
| b. ¿Vaciar registros? | **Sí** — automático, mismo pulso de RESET | §3 |
| c. ¿Vaciar pipeline? | **Sí** — automático, mismo pulso de RESET | §4 |
| d. ¿Vaciar memoria de programa? | **No** — mitigado por convención (relleno a tamaño fijo), no por el sistema | §5 |

---

## 8. Cómo se explica en el informe

> La carga y reprogramación del procesador se realiza íntegramente por UART,
> sin resintetizar: el protocolo de 5 bytes de `debug_unit` expone un comando
> RESET (que reinicia el puntero de escritura de la memoria de programa,
> limpia el banco de 32 registros y vacía todos los latches del pipeline en
> un único pulso) y un comando LOAD_INSTR que escribe una instrucción por
> trama con auto-incremento de dirección. La secuencia de carga es
> RESET → N×LOAD_INSTR → RESET.
>
> De las cuatro preguntas de la consigna, dos tienen respuesta afirmativa y
> dos negativa, y las cuatro se derivan directamente de qué recursos físicos
> tiene o no un pin de borrado masivo. Los registros y el pipeline sí se
> vacían, porque están implementados como flip-flops con lógica de reset
> síncrono explícita, y el pulso de RESET del protocolo los alcanza a los
> dos. La memoria de datos y la memoria de programa **no** se vacían, porque
> ambas son BRAM de Xilinx sin pin de *clear*: solo se pueden escribir
> posición por posición. Para la memoria de programa esto tiene una
> consecuencia concreta —una carga más corta que la anterior deja
> instrucciones residuales en las direcciones no reescritas—, mitigada en
> este proyecto por convención (todos los programas de ejemplo se rellenan
> con `nop` hasta un tamaño fijo común) y no por una garantía del hardware.
> La instrucción HALT que pide la consigna tampoco es un opcode real: se usa
> la palabra `0x00000000` —que no decodifica a ninguna instrucción válida del
> set implementado— como centinela de fin de programa, detectado por
> hardware en la etapa IF/ID.
