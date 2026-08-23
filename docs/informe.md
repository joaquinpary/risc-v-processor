# Procesador RISC-V RV32I segmentado sobre FPGA

**Trabajo Práctico Final — Arquitectura de Computadoras**
Santiago Colque · Joaquín Pary
Placa: Digilent Arty A7-35T (Artix-7 `xc7a35ticsg324-1L`)

---

> **Estado del documento.** Las secciones 1 a 8 están completas. Las
> secciones **9 (Verificación y resultados)** y **10 (Limitaciones
> conocidas)** quedan pendientes de redacción.

---

## 1. Alcance y resumen

Se implementó un procesador RISC-V de 32 bits, subconjunto **RV32I**,
con **pipeline de cinco etapas** (IF, ID, EX, MEM, WB), sobre una FPGA
Artix-7. El procesador ejecuta las 32 instrucciones exigidas por la
consigna, resuelve por hardware los tres tipos de riesgo (estructurales,
de datos y de control) y se controla desde una PC mediante una unidad de
depuración propia conectada por UART.

El sistema completo incluye:

| Bloque | Función |
|---|---|
| Procesador segmentado | Ejecuta el programa |
| Unidad de depuración | Carga programas, avanza ciclo a ciclo, lee el estado |
| Interfaz UART | Enlace serie de 9600 baudios con la PC |
| Herramientas de PC | Ensamblador, panel de control (TUI) y utilidades de diagnóstico, en Python |

La frecuencia de funcionamiento determinada experimentalmente es de
**62 MHz**, generada por un MMCM a partir del oscilador de 100 MHz de la
placa (sección 7).

---

## 2. Arquitectura del datapath

### 2.1 Organización general

El diseño sigue la organización clásica de cinco etapas separadas por
registros de segmentación (*latches*). Cada etapa se implementó como un
módulo Verilog independiente, y los latches viven en el módulo de nivel
superior `top.v`, de modo que las etapas son bloques puramente
combinacionales y toda la memoria de estado del pipeline está en un solo
lugar.

```
        IF              ID              EX             MEM             WB
   ┌──────────┐    ┌──────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐
   │instruction│   │instruction│   │ execute  │   │  memory  │   │write_back│
   │  _fetch   │   │  _decode  │   │          │   │          │   │          │
   └──────────┘    └──────────┘    └──────────┘   └──────────┘   └──────────┘
         │  IF/ID       │  ID/EX        │  EX/MEM      │  MEM/WB      │
         └──────────────┴───────────────┴──────────────┴──────────────┘
```

### 2.2 Módulos por etapa

**IF — `instruction_fetch.v`**
Contiene el registro `pc_reg` (contador de programa), el multiplexor de
salto, y la instancia de la memoria de instrucciones. Incluye además el
registro auxiliar `pc_fetched`, que mantiene el PC alineado con *su*
instrucción (ver sección 4).

**ID — `instruction_decode.v`**
Agrupa tres submódulos:

- `control.v` — decodifica el *opcode* y genera el bus de control de 10 bits.
- `imm_gen.v` — extrae y extiende el inmediato según el formato.
- `register.v` — banco de 32 registros de 32 bits.

Calcula además los **registros fuente efectivos**: no todos los formatos
usan los campos `rs1`/`rs2` como registro (en `lui` y `jal` esos bits son
parte del inmediato), y tratarlos como registros provocaría
adelantamientos espurios. Por eso se fuerzan a `x0` cuando no son un
registro real.

**EX — `execute.v`**
Contiene `alu.v` (unidad aritmético-lógica de 10 operaciones) y
`alu_control.v` (decodificación de la operación a partir de `ALUOp`,
`funct3` y el bit 30). Calcula también la dirección destino de los saltos
como `pc + inmediato`.

**MEM — `memory.v`**
Instancia la memoria de datos y resuelve los accesos de sub-palabra:
separa la dirección de byte en índice de palabra y desplazamiento, y
genera las máscaras de escritura por byte.

**WB — `write_back.v`**
Multiplexor final de escritura al banco de registros, entre el resultado
de la ALU, el dato leído de memoria y `PC+4`. Realiza también la
extracción con o sin signo del byte o media palabra leída.

### 2.3 Unidades de apoyo

| Módulo | Función |
|---|---|
| `forwarding_unit.v` | Detecta y resuelve riesgos de datos por adelantamiento |
| `hazard_detection_unit.v` | Detecta el riesgo *load-use* y ordena la parada |
| `debug_unit.v` | Máquina de estados que atiende los comandos de la PC |
| `uart_rx.v`, `uart_tx.v`, `baud_rate_gen.v`, `uart_interface.v` | Enlace serie |
| `clock_wizard` (IP) | MMCM que genera el reloj del sistema |

### 2.4 Memorias

Ambas memorias son *block RAM* generadas con el IP `blk_mem_gen` de
Xilinx, de 1024 palabras de 32 bits (4 KiB cada una):

| | Tipo | Puerto A | Puerto B |
|---|---|---|---|
| `instruction_memory` | Simple Dual Port | Escritura desde UART | Lectura del *fetch* |
| `data_memory` | True Dual Port | Lectura/escritura del procesador | Lectura del depurador |

Esta elección de dos memorias separadas con doble puerto es la que
elimina los riesgos estructurales del diseño, y se justifica en la
sección 5.

---

## 3. Set de instrucciones implementado

Se implementaron las **32 instrucciones** exigidas, cubriendo los seis
formatos del RV32I:

| Formato | Instrucciones | Cantidad |
|---|---|---|
| **R** | `add` `sub` `sll` `slt` `sltu` `xor` `srl` `sra` `or` `and` | 10 |
| **I** aritméticas | `addi` `slti` `sltiu` `xori` `ori` `andi` | 6 |
| **I** desplazamiento | `slli` `srli` `srai` | 3 |
| **I** carga | `lb` `lh` `lw` `lbu` `lhu` | 5 |
| **S** almacenamiento | `sb` `sh` `sw` | 3 |
| **B** salto condicional | `beq` `bne` | 2 |
| **U** | `lui` | 1 |
| **J** | `jal` | 1 |
| **I** salto | `jalr` | 1 |
| | **Total** | **32** |

Quedan fuera del alcance, por no estar en la consigna: `auipc` y las
comparaciones de salto `blt`, `bge`, `bltu`, `bgeu`. El ensamblador de PC
las codifica correctamente pero emite un aviso indicando que este
procesador no las ejecuta, de modo que el error se detecta al ensamblar y
no depurando el hardware.

### 3.1 Detalles de implementación destacables

**Accesos de sub-palabra.** La memoria de datos direcciona palabras, pero
las instrucciones usan direcciones de **byte**. La dirección efectiva se
separa en `result[11:2]` (índice de palabra) y `result[1:0]`
(desplazamiento dentro de la palabra). Para las escrituras se genera una
máscara de habilitación por byte, desplazada al carril correspondiente;
sin eso, un `sb` escribiría siempre el byte 0. Para las lecturas, la
extracción y extensión de signo se hace en la etapa WB, porque la BRAM
entrega el dato recién en ese ciclo.

**`lui`.** Requiere que la ALU sume el inmediato a cero. Se logra
forzando `rs1 = x0` en la etapa ID cuando el opcode es `lui`, lo que
además evita que la unidad de adelantamiento inyecte un valor sobre esos
bits.

---

## 4. Unidad de control y control de la ALU

### 4.1 Bus de control

La unidad de control decodifica el *opcode* y genera un bus de 10 bits
que viaja por el pipeline, angostándose a medida que las señales se
consumen:

```
ALUOp[9:8]  ALUSrc[7]  Branch[6]  MemRead[5]  MemWrite[4]  Jump[3]  RegWrite[2]  MemtoReg[1:0]
```

| Instrucción | Opcode | ALUOp | ALUSrc | Branch | MemRead | MemWrite | Jump | RegWrite | MemtoReg |
|---|---|---|---|---|---|---|---|---|---|
| Tipo R | `0110011` | `10` | 0 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| Tipo I aritmética | `0010011` | `11` | 1 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| Cargas | `0000011` | `00` | 1 | 0 | 1 | 0 | 0 | 1 | `01` (Mem) |
| Almacenamientos | `0100011` | `00` | 1 | 0 | 0 | 1 | 0 | 0 | `00` |
| Saltos condicionales | `1100011` | `01` | 0 | 1 | 0 | 0 | 0 | 0 | `00` |
| `lui` | `0110111` | `00` | 1 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| `jal` | `1101111` | `00` | **0** | 0 | 0 | 0 | 1 | 1 | `10` (PC+4) |
| `jalr` | `1100111` | `00` | **1** | 0 | 0 | 0 | 1 | 1 | `10` (PC+4) |

El bus se trunca al avanzar: 10 bits en ID/EX, 7 en EX/MEM (la etapa EX
consume `ALUOp` y `ALUSrc`) y 3 en MEM/WB (sólo quedan `RegWrite` y
`MemtoReg`).

Obsérvese que `ALUSrc` **no es indiferente** en `jal` y `jalr`: la
resolución del salto distingue una de otra con esa señal
(`jalr = Jump & ALUSrc`), porque `jal` salta a `pc+imm` y `jalr` a
`rs1+imm`.

### 4.2 Control de la ALU

| Código | Operación | | Código | Operación |
|---|---|---|---|---|
| `0000` | AND | | `0101` | SRL |
| `0001` | OR | | `0110` | SUB |
| `0010` | ADD | | `0111` | SLT |
| `0011` | XOR | | `1000` | SRA |
| `0100` | SLL | | `1001` | SLTU |

El `alu_control` traduce `ALUOp` + `funct3` + bit 30 de la instrucción al
código de 4 bits:

- `ALUOp = 00` → ADD (direcciones de memoria, `lui`, `jalr`)
- `ALUOp = 01` → SUB (saltos condicionales: `zero` indica igualdad)
- `ALUOp = 10` → tipo R, se decodifica con `funct3` + bit 30
- `ALUOp = 11` → tipo I aritmético, se decodifica con `funct3`

### 4.3 El bit 30 no significa lo mismo en los dos casos

Es la sutileza más importante de esta tabla. Con `ALUOp = 10` (tipo R) el
bit 30 pertenece al campo `funct7` y distingue `add`/`sub` y `srl`/`sra`.
Con `ALUOp = 11` (tipo I) ese mismo bit **es parte del inmediato**: un
`addi x1, x0, -1` lo tiene en 1, de modo que usarlo para elegir entre
suma y resta convertiría toda suma con número negativo en una resta.

La única excepción son `srli`/`srai`, donde el inmediato sí lleva el
`funct7` en su parte alta porque el desplazamiento sólo usa 5 bits. Por
eso el bit 30 se ignora para `addi` y se usa para `srli`/`srai`, aunque
compartan el mismo `ALUOp`.

---

## 5. Riesgos estructurales

Un **riesgo estructural** ocurre cuando dos instrucciones que están
simultáneamente en el pipeline necesitan el mismo recurso de hardware en
el mismo ciclo. A diferencia de los riesgos de datos y de control, no se
resuelve con lógica de detección: se resuelve **replicando o
particionando el recurso** en tiempo de diseño, o bien deteniendo el
pipeline. En este procesador se optó siempre por lo primero, de modo que
**no queda ningún riesgo estructural sin resolver**: ninguna instrucción
se detiene jamás por competencia de recursos.

A continuación se enumeran los tres conflictos potenciales y cómo se
eliminaron.

### 5.1 Acceso simultáneo a memoria: IF contra MEM

**El conflicto.** En cualquier ciclo dado, la etapa IF está buscando una
instrucción mientras la etapa MEM puede estar leyendo o escribiendo un
dato. Con una única memoria unificada —como en la máquina de un solo
ciclo— ambas etapas competirían por el mismo puerto en todos los ciclos
en que hubiera un `lw` o un `sw` en MEM. La solución clásica sería
detener el pipeline un ciclo en cada acceso a memoria, lo que degradaría
notablemente el rendimiento.

**La solución.** Se instanciaron **dos memorias físicamente separadas**,
`instruction_memory` y `data_memory`, cada una con su propio puerto para
el procesador. Esto es una organización tipo **Harvard** en el nivel de
memoria, y elimina el conflicto por construcción: IF y MEM nunca tocan el
mismo bloque.

En una FPGA esta decisión es además natural y barata: la Artix-7 dispone
de bloques de RAM dedicados e independientes, de modo que duplicar la
memoria no compite por los mismos recursos que la lógica del procesador.

### 5.2 Lectura y escritura del banco de registros en el mismo ciclo

**El conflicto.** La etapa ID lee dos registros mientras la etapa WB
escribe uno, en el mismo ciclo. Son tres accesos simultáneos al mismo
banco. Peor aún: si la instrucción en WB escribe justamente el registro
que ID está leyendo, una lectura ingenua devolvería el valor viejo, y ese
caso —separado por tres etapas— **no lo cubre la unidad de
adelantamiento**, que sólo mira EX/MEM y MEM/WB contra la instrucción que
está en EX.

**La solución.** El banco de registros (`register.v`) se diseñó con
**tres puertos de lectura combinacionales** (`rs1`, `rs2` y un tercero
para el depurador) y **un puerto de escritura sincrónico**, de modo que
los tres accesos ocurren a la vez sin competencia.

El caso de coincidencia entre lectura y escritura se resuelve con un
**bypass de escritura primero** (*write-first*): si el registro que se
está leyendo es el mismo que se está escribiendo en ese ciclo, la lectura
devuelve directamente el dato de entrada en lugar del contenido
almacenado:

```verilog
assign read_data1 = (rs1 == 5'b00000) ? 32'b0 :
                    (reg_write && rd == rs1) ? write_data : regs[rs1];
```

> **Nota de diseño.** En una versión anterior este caso se resolvía
> escribiendo el banco en el **flanco de bajada** del reloj —la técnica
> clásica de "escribir en la primera mitad del ciclo y leer en la
> segunda"—. Se abandonó por dos motivos: dejaba al banco de registros
> como el único bloque del diseño sensible a un flanco distinto al del
> resto, y reducía a medio período el tiempo disponible para el camino de
> escritura. El bypass combinacional consigue la misma visibilidad
> manteniendo todo el diseño en un solo flanco.

### 5.3 Acceso del depurador mientras el procesador ejecuta

**El conflicto.** La unidad de depuración debe poder leer la memoria de
datos y el banco de registros para mostrarlos en la PC, sin interferir
con la ejecución. Si compartiera el puerto del procesador, cada lectura
de depuración robaría un ciclo.

**La solución.** Ambos recursos exponen un puerto adicional dedicado:

- `data_memory` se generó como **True Dual Port RAM**: el procesador usa
  el puerto A y el depurador lee por el puerto B.
- `instruction_memory` se generó como **Simple Dual Port RAM**: el puerto
  A recibe la escritura durante la carga por UART y el puerto B alimenta
  el *fetch*.
- El banco de registros tiene el tercer puerto de lectura mencionado en
  §5.2, exclusivo del depurador.

Gracias a esto, **el depurador puede observar el estado sin detener ni
perturbar al procesador**, que era uno de los objetivos del sistema.

### 5.4 Recursos que no generan conflicto

La ALU, el generador de inmediatos y la unidad de control son recursos
únicos, pero sólo hay **una instrucción por etapa** en cada ciclo, de
modo que nunca son requeridos por dos instrucciones a la vez. No
constituyen riesgo estructural.

---

## 6. Profundidad real del pipeline

### 6.1 El hallazgo

El procesador implementa las cinco etapas lógicas clásicas, pero la
etapa **IF ocupa dos ciclos de reloj**. En niveles de registro el
pipeline tiene **seis**, no cinco.

La causa es que la memoria de instrucciones es una *block RAM* con salida
registrada: su latencia de lectura es de un ciclo, y la palabra aparece
un ciclo después de presentar la dirección. La búsqueda queda partida en:

- **IF1** — `pc_reg` presenta la dirección a la BRAM
- **IF2** — la instrucción está disponible a la salida de la BRAM

y recién en el ciclo siguiente el latch IF/ID la captura.

### 6.2 Evidencia

Traza de arranque en frío, siguiendo una instrucción ubicada en la
dirección `0x00`:

| Ciclo | Dónde está | Etapa |
|---|---|---|
| 0 | `pc_reg = 0x00` presenta la dirección | **IF1** |
| 1 | la instrucción sale de la BRAM | **IF2** |
| 2 | está en el latch IF/ID, lista para decodificar | **ID** |
| 3 | está en ID/EX | **EX** |
| 4 | está en EX/MEM | **MEM** |
| 5 | está en MEM/WB | **WB** |

Se pide en el ciclo 0 y se retira en el 5: seis ciclos de latencia.

### 6.3 El camino de datos no tiene este problema

Conviene aclararlo porque la estructura es la misma. En la etapa MEM la
dirección se presenta durante MEM y el dato aparece en WB, donde
`write_back` lo consume directamente. Es decir que **el registro de
salida de la BRAM de datos *es* el latch MEM/WB** para el dato leído: un
solo registro, como corresponde.

La asimetría no viene de que las memorias sean distintas. En ambos casos
el registro de salida de la BRAM cae exactamente sobre la frontera de
etapa y sale gratis. El lado de instrucciones paga un ciclo porque tiene
un **segundo registro apilado encima** (el latch IF/ID), necesario porque
el puerto B de la memoria de instrucciones se generó sin señal de
habilitación y por lo tanto no se puede congelar durante una parada.

### 6.4 Consecuencias

| Consecuencia | Detalle |
|---|---|
| Penalidad de salto | **3 ciclos**, no 2 (ver §8) |
| Registro `pc_fetched` | Necesario para alinear el PC con su instrucción |
| *Skid buffer* | Necesario para no perder la palabra en vuelo durante una parada |
| **Productividad** | **No se ve afectada**: en régimen permanente se retira una instrucción por ciclo |

Tener la salida de la memoria de instrucciones registrada es lo habitual
en un diseño sobre FPGA: es una consecuencia de usar *block RAM*, no un
descuido. El CPI ideal sigue siendo 1.

---

## 7. Riesgos de datos

### 7.1 Adelantamiento (*forwarding*)

Un riesgo de datos aparece cuando una instrucción necesita un operando
que una instrucción anterior todavía no escribió en el banco de
registros. Sin resolverlo habría que detener el pipeline hasta tres
ciclos por cada dependencia.

La `forwarding_unit` es **puramente combinacional**. Compara los
registros fuente de la instrucción que está en EX contra los registros
destino de las instrucciones más viejas que siguen en vuelo, y
selecciona el valor más fresco para cada operando de la ALU mediante dos
multiplexores de 3 a 1:

| Código | Origen del operando |
|---|---|
| `00` | Banco de registros (sin adelantamiento) |
| `10` | Etapa EX/MEM (la instrucción inmediatamente anterior) |
| `01` | Etapa MEM/WB (dos instrucciones antes) |

**Doble riesgo de datos.** Cuando las dos instrucciones anteriores
escriben el mismo registro, debe ganar la más reciente. Esto se
implementa por el **orden de las comparaciones**: se prueba primero
EX/MEM y sólo si no coincide se prueba MEM/WB.

El registro `x0` nunca se adelanta, porque por definición vale cero.

### 7.2 Parada por *load-use*

El adelantamiento no alcanza en un caso: una carga produce su valor al
final de la etapa MEM, de modo que una instrucción inmediatamente
posterior que lea ese registro lo necesita **antes** de que exista. La
única solución es **detener el pipeline exactamente un ciclo**.

La `hazard_detection_unit` detecta la condición:

```
la instrucción en EX es una carga  (MemRead = 1)
        Y
su registro destino coincide con rs1 o rs2 de la instrucción en ID
        Y
ese registro destino no es x0
```

y ante ella emite tres señales:

| Señal | Valor | Efecto |
|---|---|---|
| `pc_write` | 0 (activa baja) | Congela el PC: se vuelve a buscar la misma dirección |
| `if_id_write` | 0 (activa baja) | Congela el latch IF/ID: la instrucción dependiente se queda en ID |
| `control_mux` | 1 (activa alta) | Anula el bus de control que entra a ID/EX: inserta una burbuja |

Tras ese ciclo de parada, el valor ya está disponible en MEM/WB y el
adelantamiento normal se encarga del resto.

### 7.3 El *skid buffer*

La parada tiene una complicación propia de este diseño, derivada de la
sección 6: como el puerto de lectura de la memoria de instrucciones no
tiene señal de habilitación, **la BRAM sigue avanzando aunque el
pipeline esté congelado**, y la palabra que estaba en vuelo se perdería.

Se agregó un registro auxiliar (*skid buffer*) que la retiene durante la
parada y la reinyecta al reanudar. El vaciado por salto tomado debe
invalidarlo, porque en ese caso la palabra guardada pertenece al camino
equivocado.

---

## 8. Riesgos de control

### 8.1 Estrategia: predicción estática "no salta"

Cuando el pipeline encuentra un salto condicional, no sabe si se tomará
hasta haberlo evaluado. La estrategia adoptada es la **predicción
estática de no tomado**: el pipeline sigue buscando instrucciones en
secuencia y, si el salto resulta tomado, se **vacían** (*flush*) las
instrucciones equivocadas que ya entraron.

Su ventaja es el costo cero cuando el salto no se toma, que es el caso
más frecuente en los saltos hacia adelante.

### 8.2 Resolución en EX

La decisión del salto se toma en la etapa **EX**, no en MEM. Cuanto antes
se resuelva, menos instrucciones equivocadas entran al pipeline:
resolverlo en MEM costaría un ciclo más de penalidad.

La ALU resta los operandos en los saltos condicionales (`ALUOp = 01`), de
modo que su señal `zero` indica si son iguales. El campo `funct3` elige
la polaridad:

| `funct3` | Instrucción | Condición |
|---|---|---|
| `000` | `beq` | salta si `zero = 1` |
| `001` | `bne` | salta si `zero = 0` |

El destino es `pc + inmediato` para `beq`, `bne` y `jal`, y el resultado
de la ALU (`rs1 + inmediato`) para `jalr`.

### 8.3 La penalidad real es de 3 ciclos, no de 2

El modelo clásico de cinco etapas indica que resolver en EX cuesta dos
ciclos. **En este diseño cuesta tres**, por la etapa adicional de la
sección 6. Al confirmarse el salto hay tres instrucciones del camino
equivocado en vuelo:

1. la que está en ID,
2. la que ya salió de la memoria de instrucciones y espera a su salida,
3. **la que se está buscando en ese mismo ciclo**, que aparecerá al ciclo
   siguiente — el redireccionamiento del PC llega tarde para evitarla.

Vaciar el latch IF/ID un solo ciclo elimina (1) y (2) pero **deja pasar
(3)**. Por eso el vaciado del frente se extiende **dos ciclos**.

Esto no es un razonamiento teórico: se detectó ejecutando un `jalr`, que
ejecutaba la instrucción ubicada tres lugares después del salto.

### 8.4 Mecanismo de vaciado

| Latch | Acción al vaciar |
|---|---|
| IF/ID | Se pone la instrucción en cero (decodifica como burbuja inofensiva) durante dos ciclos |
| ID/EX | Se anula el bus de control: con `RegWrite`, `MemWrite`, `Branch` y `Jump` en cero, los datos que arrastre la burbuja no tienen efecto |
| *Skid buffer* | Se invalida |

El vaciado tiene **prioridad sobre el congelamiento** de la parada por
*load-use*. En la práctica no pueden coexistir —una instrucción en EX no
puede ser carga y salto a la vez— pero el orden correcto deja la lógica a
prueba de cambios futuros.

### 8.5 El bit de validez del latch IF/ID

Una burbuja de vaciado tiene la instrucción en cero, que es exactamente
el patrón con el que el sistema detecta el fin del programa. Sin
protección, **cada salto tomado detendría el procesador**.

Por eso el latch IF/ID incorpora un bit `if_id_valid` que distingue una
instrucción real de una burbuja, y la detección de fin de programa lo
exige:

```verilog
assign cpu_halted = (instruction_id == 32'b0) && if_id_valid
                                              && (pc_if > 32'h00000010);
```

---

## 9. Timing del sistema

> **Sección basada en `docs/informe-timing-carga.md` §1 y
> `docs/clock-timing.md`.** Resumen de resultados; el desarrollo completo,
> con los reportes de Vivado, está en esos documentos.

### 9.1 Camino crítico y skew son fenómenos distintos

El **camino crítico** es una propiedad del camino de *datos*: la cadena
combinacional más lenta entre dos registros. El **skew** es una propiedad
del árbol de *reloj*: la diferencia de tiempo de llegada del flanco a dos
registros distintos. Comparten la ecuación de cierre de timing pero no
son lo mismo, y en este diseño sólo uno de los dos resultó limitante.

### 9.2 El camino crítico medido

El cuello de botella real, confirmado en tres corridas independientes de
*place & route* a frecuencias distintas, es siempre la misma cadena
funcional:

```
memoria de datos → write_back / forwarding → ALU → control de stall/flush
```

Es decir: **no es la ALU aislada**, como sugeriría la intuición, sino la
realimentación desde la memoria y el adelantamiento hacia la ALU y de ahí
a la lógica que decide parar o vaciar el pipeline. El registro específico
que "pierde" cambia según cómo resuelva el emplazamiento cada corrida,
pero la cadena es siempre la misma.

### 9.3 El skew no es el factor limitante

En el camino crítico a 62 MHz el reporte indica un `Clock Path Skew` de
**−0.016 ns** contra **15.283 ns** de retardo de datos: tres órdenes de
magnitud de diferencia. El árbol de reloj de la FPGA está construido con
recursos dedicados de bajo *skew*, de modo que el margen lo consume casi
enteramente el camino de datos.

### 9.4 Frecuencia de funcionamiento

Se determinó experimentalmente, iterando:

| Corrida | Frecuencia | WNS | WHS | ¿Cierra? |
|---|---|---|---|---|
| Directa, sin MMCM | 100 MHz | −4.218 ns | +0.080 ns | **No** |
| Con MMCM | 50 MHz | +2.616 ns | +0.079 ns | Sí, con holgura |
| Con MMCM | **62 MHz** | **+0.291 ns** | **+0.033 ns** | **Sí, ajustado** |

Partiendo de la corrida a 100 MHz, la estimación de primer orden daba
`F_max ≈ 1/(10 ns − 4.218 ns) ≈ 70 MHz`. Se eligió **62 MHz** como valor
con margen por debajo de esa cota, se reimplementó y se generó el
*bitstream*: cierra, con el camino crítico consumiendo el 94.8 % del
período disponible.

La frecuencia adoptada es por lo tanto **62 MHz**, generada por un MMCM
(IP *Clock Wizard*) a partir del oscilador de 100 MHz de la placa.

---

## 10. Carga de programa

> **Sección basada en `docs/informe-timing-carga.md` §2 y
> `docs/program-loading.md`.**

### 10.1 Mecanismo

El programa se transfiere desde la PC por UART a 9600 baudios, usando un
protocolo propio de **tramas de 5 bytes**:

```
byte 0    : comando
bytes 1-4 : payload de 32 bits, big-endian
```

La secuencia de carga es:

1. **RESET** — reinicia la CPU y pone en cero el puntero de escritura de
   la memoria de instrucciones.
2. **LOAD_INSTR × N** — una trama por instrucción. El firmware **no
   recibe la dirección**: `debug_unit` autoincrementa el puntero en cada
   comando.
3. **RESET final** — deja el PC en 0 y el pipeline limpio.

Que el puntero se autoincremente es lo que vuelve obligatorio el RESET
inicial: es lo único que lo reposiciona.

### 10.2 Qué hace falta vaciar y qué no

| Recurso | ¿Vaciar? | Justificación |
|---|---|---|
| **Pipeline** | **Sí** | Un programa nuevo no puede empezar con instrucciones del anterior en vuelo. Lo hace el RESET, que limpia los cuatro latches. |
| **Banco de registros** | **Sí** | El RESET pone los 32 en cero. Sin esto, un programa vería valores del anterior y los resultados no serían reproducibles. |
| **Memoria de datos** | **No es necesario** | Un programa correcto escribe antes de leer. Además, no vaciarla es lo que permite encadenar programas que se pasan datos, algo que se usó activamente durante la depuración. |
| **Memoria de programa** | **No se vacía** | `LOAD_INSTR` sólo escribe las palabras que recibe; el resto conserva el contenido anterior. |

### 10.3 La consecuencia práctica de no vaciar la memoria de programa

Si se carga un programa **más corto** que el anterior, las palabras
sobrantes del viejo siguen ahí, y el procesador las ejecuta al pasar el
final del nuevo. Es un efecto real y observable.

Se adoptó una convención en lugar de agregar hardware: **todos los
programas de demostración se rellenan con `nop` hasta una longitud
común de 28 palabras**, de modo que cargar cualquiera sobre cualquier
otro lo sobrescribe por completo.

### 10.4 La detención del programa

El fin de la ejecución se detecta cuando una palabra en cero llega a la
etapa ID, con el PC más allá de la dirección `0x10`. Una palabra en cero
no es una instrucción válida del RV32I: no corresponde a ningún opcode,
cae en el caso por defecto de la unidad de control y pone todo el bus de
control en cero.

Es decir que **el HALT no es una instrucción del set**, sino un patrón
que el hardware reconoce. Como la memoria de instrucciones arranca
inicializada en ceros tras configurar la FPGA, todo programa termina
naturalmente al pasar su última instrucción.

Por la profundidad del pipeline, las instrucciones que van detrás de esa
palabra en cero necesitan algunos ciclos más para retirarse. Por eso los
programas de demostración terminan con varios `nop`: garantizan que las
últimas instrucciones útiles alcancen a escribir sus resultados antes de
que la detención congele el pipeline.

---

## 11. Verificación y resultados

> ⏳ **PENDIENTE DE REDACCIÓN.**
>
> Material disponible para esta sección:
>
> - Modelo ciclo a ciclo del pipeline en Python contrastado contra un
>   simulador RV32I secuencial de referencia: 24 casos dirigidos y 400
>   programas aleatorios, 0 diferencias (`tools/test_pipeline.py`).
> - Testbenches exhaustivos de las unidades de riesgos (barrido completo
>   del espacio de entrada).
> - Modelo del encuadre UART (`tools/test_uart_framing.py`).
> - Autotest del ensamblador, incluido el round-trip ensamblar →
>   desensamblar de los 37 mnemónicos.
> - Cinco programas de demostración ejecutados en la placa real, en modo
>   paso a paso y en ejecución libre, con resultados idénticos entre sí y
>   coincidentes con el simulador de referencia.
> - Trazas ciclo a ciclo obtenidas del hardware, comparadas contra el
>   modelo.

---

## 12. Limitaciones conocidas

> ⏳ **PENDIENTE DE REDACCIÓN.**
>
> Material disponible para esta sección:
>
> - **Valor de enlace de `jal`**: escribe `pc+8` en ejecución libre y
>   `pc+4` al ejecutar paso a paso. El destino del salto y el vaciado son
>   correctos en ambos modos. Existe un reproductor mínimo de tres
>   instrucciones (`examples/jal_min.s`). Causa no identificada.
> - **Detención anticipada**: la ejecución libre se detiene unos ciclos
>   antes de que se retiren las últimas instrucciones; se compensa con
>   relleno de `nop`.
> - **Recuperación del modo RUN**: un programa que nunca alcanza una
>   palabra en cero deja la unidad de depuración sin atender la UART, y
>   sólo se recupera reprogramando la placa.
> - **Instrucciones fuera de alcance**: `auipc`, `blt`, `bge`, `bltu`,
>   `bgeu`.
> - **Margen de timing a 62 MHz**: WNS +0.291 ns (1.8 % del período) y
>   WHS +0.033 ns, ajustados frente a variaciones de proceso,
>   temperatura y tensión.
