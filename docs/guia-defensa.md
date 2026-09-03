# Guía para defender el trabajo — desde cero

Esta guía no supone ningún conocimiento previo. Empieza por qué es un
procesador y termina en las decisiones concretas que tomamos.

**Cómo usarla:** leé las partes 1 a 4 hasta entenderlas (son los
fundamentos). Las partes 5 a 8 son lo específico de nuestro trabajo. La
parte 9 son preguntas con respuesta lista.

---

## Parte 1 — Qué es un procesador

Un procesador hace **una sola cosa**, repetida millones de veces por
segundo:

1. Busca una instrucción en la memoria.
2. Averigua qué significa.
3. La ejecuta.
4. Guarda el resultado.
5. Pasa a la siguiente.

Eso es todo. Un procesador es una máquina que repite ese ciclo.

### Las tres piezas

**El contador de programa (PC).** Un número que dice en qué dirección de
memoria está la próxima instrucción. Normalmente avanza de a 4 (cada
instrucción ocupa 4 bytes). Los saltos son, literalmente, cambiarle el
valor al PC.

**Los registros.** 32 cajitas de 32 bits cada una, adentro del
procesador. Son la memoria ultrarrápida donde el procesador hace las
cuentas. **El procesador no puede sumar dos posiciones de memoria
directamente**: primero tiene que traerlas a registros, sumar, y después
guardar el resultado. Eso se llama arquitectura *load-store*, y es la
característica que define a RISC-V.

**La memoria.** Grande y lenta comparada con los registros. Guarda el
programa y los datos.

### Los 32 registros y sus nombres

Cada registro tiene un número (`x0` a `x31`) y un nombre por convención:

| Número | Nombre | Para qué se usa por convención |
|---|---|---|
| `x0` | `zero` | **Siempre vale 0.** No se puede escribir. |
| `x1` | `ra` | *Return address*: a dónde volver de una función |
| `x2` | `sp` | *Stack pointer* |
| `x5`–`x7` | `t0`–`t2` | Temporales |
| `x8`–`x9` | `s0`–`s1` | Guardados |
| `x10`–`x17` | `a0`–`a7` | Argumentos y resultados |
| `x18`–`x27` | `s2`–`s11` | Guardados |
| `x28`–`x31` | `t3`–`t6` | Temporales |

**`x0` es especial y te lo pueden preguntar.** Vale cero siempre, por
hardware. Sirve para muchos trucos: `addi x5, x0, 42` carga la constante
42 (sumarle 42 a cero), y `add x0, x1, x2` es una operación que no hace
nada. Los nombres (`t0`, `a0`...) son **sólo una convención de
programación**: para el hardware son todos iguales.

---

## Parte 2 — Qué es una instrucción

Una instrucción es **un número de 32 bits**. No es texto. Cuando escribís
`add t0, t1, t2`, un programa (el *ensamblador*) lo convierte al número
`0x006283B3`, y eso es lo que se guarda en la memoria.

Esos 32 bits están divididos en campos:

| Campo | Qué dice |
|---|---|
| **opcode** (7 bits) | Qué familia de instrucción es |
| **rd** (5 bits) | Registro **destino** (dónde guardar el resultado) |
| **rs1** (5 bits) | Primer registro **fuente** |
| **rs2** (5 bits) | Segundo registro fuente |
| **funct3** (3 bits) | Cuál de la familia (dentro del mismo opcode) |
| **funct7** (7 bits) | Afina todavía más |
| **inmediato** | Una constante escrita dentro de la instrucción |

5 bits para elegir registro porque 2⁵ = 32, justo la cantidad que hay.

### Por qué hay seis formatos

No todas las instrucciones necesitan lo mismo. `add` necesita dos
registros fuente y uno destino. `addi` necesita un registro y una
constante. Un salto necesita una dirección. Como el espacio es fijo (32
bits), se definieron **seis maneras de repartirlo**:

| Formato | Se usa para | Ejemplo |
|---|---|---|
| **R** | registro op registro | `add t0, t1, t2` |
| **I** | registro op constante, y las cargas | `addi t0, t1, 5` |
| **S** | almacenamientos | `sw t0, 8(t1)` |
| **B** | saltos condicionales | `beq t0, t1, ETIQUETA` |
| **U** | constantes grandes | `lui t0, 0x12345` |
| **J** | saltos incondicionales | `jal ra, ETIQUETA` |

---

## Parte 3 — Las 32 instrucciones, una por una

### 3.1 Aritmética y lógica entre registros (tipo R) — 10 instrucciones

Todas tienen la misma forma: `operación rd, rs1, rs2` → toma dos
registros, opera, guarda en un tercero.

| Instrucción | Qué hace | Ejemplo (`t1=8`, `t2=2`) |
|---|---|---|
| `add rd, rs1, rs2` | Suma | `add t0,t1,t2` → `t0 = 10` |
| `sub rd, rs1, rs2` | Resta | `sub t0,t1,t2` → `t0 = 6` |
| `and rd, rs1, rs2` | Y lógico bit a bit | `8 AND 2 = 0` |
| `or rd, rs1, rs2` | O lógico bit a bit | `8 OR 2 = 10` |
| `xor rd, rs1, rs2` | O exclusivo bit a bit | `8 XOR 2 = 10` |
| `sll rd, rs1, rs2` | Desplaza a la izquierda | `8 << 2 = 32` |
| `srl rd, rs1, rs2` | Desplaza a la derecha, **rellena con ceros** | `8 >> 2 = 2` |
| `sra rd, rs1, rs2` | Desplaza a la derecha, **rellena con el signo** | `-8 >> 2 = -2` |
| `slt rd, rs1, rs2` | ¿rs1 < rs2? (**con signo**) → 1 o 0 | |
| `sltu rd, rs1, rs2` | ¿rs1 < rs2? (**sin signo**) → 1 o 0 | |

**Las dos parejas que importan:**

`srl` contra `sra` — desplazar a la derecha es dividir por potencias de
2. Con un número negativo, rellenar con ceros da un resultado enorme y
positivo (mal); rellenar con el bit de signo mantiene el número negativo
(bien). Por eso existen las dos.

`slt` contra `sltu` — el mismo patrón de bits significa cosas distintas.
`0xFFFFFFF0` es **−16** con signo y **4294967280** sin signo. Con signo
es menor que cero; sin signo es enorme. Nuestro `demo_1_alu` lo muestra:
`s8 = 1` (slt) y `s9 = 0` (sltu), con el mismo operando.

### 3.2 Aritmética con constante (tipo I) — 9 instrucciones

Igual que arriba, pero el segundo operando es un número escrito en la
instrucción en vez de un registro. La `i` final significa *immediate*.

| Instrucción | Qué hace |
|---|---|
| `addi rd, rs1, imm` | rd = rs1 + constante |
| `andi`, `ori`, `xori` | Lógicas con constante |
| `slti`, `sltiu` | Comparaciones con constante |
| `slli`, `srli`, `srai` | Desplazamientos con constante |

No existe `subi`: para restar 5 se hace `addi rd, rs1, -5`.

La constante son 12 bits **con signo**: alcanza para −2048 a +2047.

### 3.3 Cargas — traer de memoria a registro (5 instrucciones)

Forma: `carga rd, desplazamiento(registro_base)`

La dirección se calcula sumando: `registro_base + desplazamiento`.

| Instrucción | Cuánto trae | Cómo completa los bits que faltan |
|---|---|---|
| `lw rd, off(rs1)` | 4 bytes (palabra) | — |
| `lh rd, off(rs1)` | 2 bytes | **Extiende el signo** |
| `lhu rd, off(rs1)` | 2 bytes | Rellena con ceros |
| `lb rd, off(rs1)` | 1 byte | **Extiende el signo** |
| `lbu rd, off(rs1)` | 1 byte | Rellena con ceros |

**Qué es extender el signo.** Traés un byte y tenés que llenar un
registro de 32 bits. Si el byte es `0xFF`:

- Como **número con signo**, `0xFF` es −1 → hay que completar con unos:
  `0xFFFFFFFF`, que es −1 en 32 bits. Eso hace `lb`.
- Como **número sin signo**, `0xFF` es 255 → se completa con ceros:
  `0x000000FF` = 255. Eso hace `lbu`.

Nuestro `demo_2_memoria` lo muestra: el mismo byte da `s3 = −1` con `lb`
y `s4 = 255` con `lbu`.

### 3.4 Almacenamientos — guardar de registro a memoria (3 instrucciones)

Forma: `guardado rs2, desplazamiento(registro_base)`

| Instrucción | Cuánto guarda |
|---|---|
| `sw rs2, off(rs1)` | Los 4 bytes del registro |
| `sh rs2, off(rs1)` | Sólo los 2 bytes de abajo |
| `sb rs2, off(rs1)` | Sólo el byte de abajo |

No hay versiones "u": al guardar no hay nada que extender, se recorta y
listo.

**Por qué `sb` es difícil en hardware.** La memoria está organizada en
palabras de 4 bytes. Para escribir **un solo byte** hay que decirle a la
memoria "escribí sólo este byte y dejá los otros tres como están". Eso se
hace con una **máscara de escritura por byte**, y hay que desplazarla
según cuál de los 4 bytes toca. Es la parte del trabajo que llamamos
"accesos de sub-palabra". `demo_2_memoria` lo demuestra: `s5 =
0x0000FF00`, un byte escrito en el medio y los otros tres intactos.

### 3.5 Saltos condicionales (tipo B) — 2 instrucciones

| Instrucción | Salta si |
|---|---|
| `beq rs1, rs2, ETIQUETA` | rs1 **es igual** a rs2 |
| `bne rs1, rs2, ETIQUETA` | rs1 **es distinto** de rs2 |

Con esto se hacen los `if` y los bucles. Un bucle es un `bne` que salta
**hacia atrás**:

```asm
LOOP:   addi s3, s3, 10      # sumar 10
        addi s2, s2, -1      # descontar 1
        bne  s2, zero, LOOP  # si no llegó a cero, volver
```

El RV32I completo tiene también `blt`, `bge`, `bltu`, `bgeu` (menor,
mayor o igual). **No están en nuestro trabajo** porque la consigna no las
pedía.

### 3.6 Constantes grandes — `lui` (1 instrucción)

Problema: `addi` sólo llega a 12 bits (hasta 2047). ¿Cómo cargás
`0x12345678`?

`lui rd, constante` (*load upper immediate*) pone una constante de 20
bits en la **parte alta** del registro y ceros abajo:

```asm
lui  t0, 0x12345      # t0 = 0x12345000
addi t0, t0, 0x678    # t0 = 0x12345678
```

Entre las dos arman cualquier número de 32 bits.

### 3.7 Saltos incondicionales — 2 instrucciones

| Instrucción | Qué hace |
|---|---|
| `jal rd, ETIQUETA` | Salta **siempre**, y guarda en `rd` la dirección de la instrucción siguiente |
| `jalr rd, off(rs1)` | Salta a `rs1 + off`, y guarda en `rd` la siguiente |

**Para qué guardar la dirección de vuelta.** Son las llamadas a función:
`jal ra, funcion` salta a la función **y anota en `ra` dónde volver**. Al
terminar, la función hace `jalr x0, 0(ra)` y regresa.

Si no te interesa volver (un salto normal), usás `x0` como destino:
`jal x0, ETIQUETA`. El ensamblador te deja escribirlo como `j ETIQUETA`.

### 3.8 Resumen: las 32

| Grupo | Cuántas |
|---|---|
| Tipo R | 10 |
| Tipo I aritméticas | 6 |
| Tipo I desplazamiento | 3 |
| Cargas | 5 |
| Almacenamientos | 3 |
| Saltos condicionales | 2 |
| `lui` | 1 |
| `jal` | 1 |
| `jalr` | 1 |
| **Total** | **32** |

---

## Parte 4 — Qué es el pipeline (segmentación)

### La idea

Ejecutar una instrucción son cinco trabajos distintos:

| Etapa | Sigla | Qué hace |
|---|---|---|
| Búsqueda | **IF** | Trae la instrucción de la memoria |
| Decodificación | **ID** | Ve qué instrucción es y lee los registros |
| Ejecución | **EX** | Hace la cuenta en la ALU |
| Memoria | **MEM** | Lee o escribe memoria (sólo cargas y almacenamientos) |
| Escritura | **WB** | Guarda el resultado en el registro destino |

**Sin pipeline** hacés las cinco para una instrucción, después las cinco
para la siguiente. Una instrucción cada 5 ciclos.

**Con pipeline** es una línea de montaje: cinco puestos trabajando al
mismo tiempo sobre cinco instrucciones distintas.

```
ciclo:      1     2     3     4     5     6     7
instr 1:   IF    ID    EX    MEM   WB
instr 2:         IF    ID    EX    MEM   WB
instr 3:               IF    ID    EX    MEM   WB
```

A partir del ciclo 5 **sale una instrucción por ciclo**.

### El punto que hay que entender

El pipeline **no acelera una instrucción**: una instrucción sigue
tardando 5 ciclos en atravesar el procesador. Lo que mejora es la
**productividad**: en vez de una cada 5 ciclos, sale una por ciclo.

Es exactamente lo mismo que un lavadero: lavar una tanda de ropa sigue
tardando lo mismo, pero si mientras una se seca ya metés otra a lavar,
terminás muchas más tandas por hora.

### Los latches

Entre puesto y puesto hay registros que guardan lo que el anterior
produjo: **IF/ID, ID/EX, EX/MEM, MEM/WB**. Son las cintas
transportadoras. En cada flanco de reloj, todo avanza un puesto.

---

## Parte 5 — Los tres problemas del pipeline

Superponer trabajo trae problemas. Hay exactamente tres, y son "los tres
riesgos" (*hazards*).

### 5.1 Riesgo estructural — dos instrucciones, la misma herramienta

**El problema.** En un mismo ciclo, la etapa IF está buscando una
instrucción en memoria y la etapa MEM puede estar leyendo un dato. Con
**una sola memoria**, chocan.

**Nuestra solución: dos memorias separadas.** Una para instrucciones y
otra para datos. Se llama **arquitectura Harvard**. El conflicto no se
detecta ni se resuelve: **no existe**, porque el recurso está duplicado.

En una FPGA esto es natural: hay bloques de memoria dedicados e
independientes, así que duplicar no cuesta lógica.

**Los otros dos casos que resolvimos igual:**

- **El banco de registros**: ID lee dos registros mientras WB escribe
  uno. Lo hicimos con **tres puertos de lectura y uno de escritura**, así
  los tres accesos ocurren juntos.
- **El depurador**: para mostrar los datos en la PC sin frenar la CPU,
  cada memoria tiene un **segundo puerto** dedicado.

> **Frase para la defensa:** *"Los riesgos estructurales los resolvimos
> por construcción, duplicando recursos, no con lógica de detección.
> Ninguna instrucción se detiene por competencia de recursos."*

### 5.2 Riesgo de datos — necesito un resultado que no está listo

```asm
add t0, t1, t2     # calcula t0
sub t3, t0, t4     # necesita t0 ... pero todavía no se guardó
```

Cuando el `sub` está en ID leyendo registros, el `add` recién está en EX.
El valor todavía no llegó al banco de registros.

**Nuestra solución: adelantamiento (*forwarding*).** El valor **existe**
—salió de la ALU— sólo que está en un latch. En vez de esperar, se lo
pasamos directo por un atajo. Hay dos multiplexores antes de la ALU que
eligen de dónde viene cada operando: del banco de registros, de EX/MEM, o
de MEM/WB.

**Detalle fino (el "doble riesgo"):** si las dos instrucciones anteriores
escriben el mismo registro, tiene que ganar la **más reciente**. Lo
resolvimos con el **orden de las comparaciones**: primero se pregunta por
EX/MEM y sólo si no coincide se mira MEM/WB.

### 5.3 El caso donde el adelantamiento NO alcanza

```asm
lw  t0, 0(t1)      # el dato sale de memoria al FINAL de la etapa MEM
add t2, t0, t3     # lo necesita en EX ... un ciclo antes
```

Acá no hay atajo posible: **el dato todavía no existe**. No se puede
adelantar algo que no se leyó.

**Nuestra solución: parar el pipeline un ciclo** (una "burbuja"). La
unidad de detección de riesgos congela el PC y el latch IF/ID, y mete una
instrucción vacía en la etapa EX. Después de ese ciclo, el dato ya está
disponible y el adelantamiento normal se encarga.

Esto se llama **riesgo load-use**, y es el único que obliga a frenar.

> **Frase que muestra que entendiste:** *"El adelantamiento resuelve
> dónde está el dato; la parada resuelve cuándo existe. Son problemas
> distintos, por eso hacen falta las dos unidades."*

### 5.4 Riesgo de control — no sé cuál es la próxima instrucción

```asm
beq t0, t1, DESTINO
addi t2, zero, 99      # ¿se ejecuta? Depende del beq
```

El pipeline tiene que buscar la instrucción siguiente **antes** de saber
si el salto se toma.

**Nuestra solución: predicción estática "no salta".** Asumimos que el
salto **no** se toma y seguimos derecho. Si resulta que sí se tomaba,
**vaciamos** (*flush*) las instrucciones equivocadas que ya entraron:
les ponemos el bus de control en cero, así no escriben nada.

Ventaja: **si el salto no se toma, no cuesta nada**.

**Y decidimos el salto en la etapa EX, lo más temprano posible.** Cuanto
antes se sepa, menos instrucciones equivocadas entraron. Resolverlo más
tarde costaría un ciclo más de penalidad.

---

## Parte 6 — Las tres cosas que los distinguen

Esto es lo que separa "copié el diagrama del libro" de "entendí el
hardware". Sáquenlo ustedes sin esperar a que lo pregunten.

### 6.1 El pipeline tiene 6 niveles, no 5, y sabemos por qué

El libro asume memorias **asíncronas**: pedís una dirección y el dato
aparece en el instante. **En una FPGA eso no existe.** La memoria interna
(*block RAM*) tiene la salida registrada: pedís la dirección en un ciclo
y la respuesta llega **al ciclo siguiente**.

Consecuencia: la etapa IF ocupa **dos ciclos**. Uno para presentar la
dirección, otro para recibir la instrucción.

**Lo medimos:** una instrucción ubicada en la dirección 0 se pide en el
ciclo 0 y termina en el ciclo 5. Seis ciclos, no cinco.

**Lo que hay que decir:**
- Las etapas **lógicas** siguen siendo cinco.
- **La productividad no cambia**: sigue saliendo una instrucción por ciclo.
- Lo que cambia es la **penalidad de salto: 3 ciclos en vez de 2**.
- **No es un error, es consecuencia de usar block RAM**, y está
  contemplado en el diseño.

### 6.2 La trampa del bit 30

El bit número 30 de la instrucción **significa cosas distintas** según el
formato:

| | Qué es el bit 30 | Para qué sirve |
|---|---|---|
| `add` / `sub` (tipo R) | Parte del campo `funct7` | Distingue suma de resta |
| `addi` (tipo I) | **Parte del número** | No significa nada |

Si el hardware lo usa siempre para elegir entre suma y resta, entonces
**`addi t0, t1, -1` se convierte en una resta**, porque todo número
negativo tiene ese bit en 1. El programa daría mal y sería dificilísimo
de encontrar.

La excepción: `srli` y `srai` **sí** lo usan, porque un desplazamiento
sólo necesita 5 bits y sobra lugar en la constante.

> Si te preguntan qué fue lo más difícil de la unidad de control, esta es
> la respuesta.

### 6.3 El camino crítico no es la ALU

La **frecuencia máxima** de un procesador la fija su camino más lento
entre dos registros: el **camino crítico**. La intuición dice "lo más
lento es la ALU". **Lo medimos y es falso.**

El camino crítico real, confirmado en tres corridas independientes, es:

```
memoria de datos → adelantamiento → ALU → lógica de parada y vaciado
```

Es un **lazo de realimentación**, no una etapa suelta.

Y hay dos conceptos que conviene no confundir:

| | Qué es | Cuánto midió |
|---|---|---|
| **Camino crítico** | La cadena de datos más lenta entre dos registros | 15.283 ns |
| **Skew** | Diferencia de llegada del reloj a dos registros | −0.016 ns |

Tres órdenes de magnitud. El árbol de reloj de la FPGA usa recursos
dedicados de bajo skew, así que **el margen se lo come el camino de
datos, no el reloj**.

---

## Parte 7 — La frecuencia

No la elegimos: la **medimos**, iterando.

| Intento | Frecuencia | Margen (WNS) | ¿Cierra? |
|---|---|---|---|
| Directo, sin ajustar | 100 MHz | −4.218 ns | **No** |
| Con MMCM | 50 MHz | +2.616 ns | Sí, holgado |
| Con MMCM | **62 MHz** | **+0.291 ns** | **Sí, ajustado** |

El **WNS** (*worst negative slack*) es el margen del camino más lento: si
es negativo, el diseño no funciona a esa frecuencia.

Partiendo del intento a 100 MHz, la cuenta estimada daba un máximo de
~70 MHz. Elegimos **62 MHz** con margen, reimplementamos y cerró.

El **MMCM** es un bloque de la FPGA que genera un reloj de la frecuencia
que le pidas a partir del oscilador de 100 MHz de la placa.

---

## Parte 8 — Cómo se carga y se ejecuta un programa

El procesador no tiene teclado ni disco. Todo entra por un cable **UART**
(puerto serie) desde la PC, a 9600 bits por segundo.

**Protocolo propio: tramas de 5 bytes.** El primer byte es el comando y
los otros cuatro el dato.

| Comando | Qué hace |
|---|---|
| `RESET` | Reinicia la CPU y los registros |
| `LOAD_INSTR` | Escribe una instrucción en memoria |
| `STEP` | Avanza **un solo ciclo de reloj** |
| `RUN` | Ejecuta libremente hasta terminar |
| `REQ_REG` / `REQ_MEM` / `REQ_PC` | Pide el valor de un registro, memoria o el PC |

**Cómo se sabe que el programa terminó.** No hay una instrucción "HALT".
Cuando el procesador se topa con una palabra en **cero**, eso no
corresponde a ninguna instrucción válida: el hardware lo detecta y frena.
Como la memoria arranca llena de ceros, **todo programa termina solo** al
pasar su última instrucción.

**Qué se limpia y qué no al cargar un programa nuevo:**

| | ¿Se limpia? | Por qué |
|---|---|---|
| Pipeline | **Sí** | No puede quedar nada del programa anterior en vuelo |
| Registros | **Sí** | Si no, los resultados no serían reproducibles |
| Memoria de datos | No | Un programa correcto escribe antes de leer |
| Memoria de programa | No | Sólo se sobrescriben las palabras que se envían |

---

## Parte 9 — Preguntas probables, con la respuesta

**"¿Qué es una arquitectura load-store?"**
Que las operaciones aritméticas trabajan **sólo con registros**. Para
operar con un dato de memoria hay que traerlo con un `load`, operar, y
guardarlo con un `store`. No existe "sumá estas dos posiciones de
memoria".

**"¿Para qué sirve `x0`?"**
Vale cero siempre, por hardware. Permite cargar constantes
(`addi t0, x0, 42`), descartar resultados, y comparar contra cero.

**"¿Por qué el pipeline no acelera una instrucción?"**
Porque sigue atravesando las cinco etapas. Lo que mejora es cuántas
instrucciones terminan por unidad de tiempo, no cuánto tarda cada una.

**"¿Por qué dos memorias separadas?"**
Para eliminar el riesgo estructural entre IF y MEM. Con una sola,
habría que frenar el pipeline en cada carga o almacenamiento.

**"¿Cuándo no alcanza el adelantamiento?"**
En el *load-use*: cuando una carga es seguida inmediatamente por una
instrucción que usa lo cargado. El dato no existe todavía, y hay que
frenar un ciclo.

**"¿Por qué resolvés el salto en EX y no más tarde?"**
Porque cuanto antes se decida, menos instrucciones equivocadas entraron
al pipeline. Cada etapa que se demora es un ciclo más de penalidad.

**"¿Por qué la ALU resta en los saltos?"**
Porque ya sabe restar, y su señal `zero` indica si el resultado dio cero,
o sea si los operandos eran iguales. Sale gratis. `funct3` elige la
polaridad: `beq` salta con `zero=1`, `bne` con `zero=0`.

**"¿Cómo saben que funciona?"** *(la más importante)*
Tres niveles de verificación:
1. Un **modelo del pipeline ciclo a ciclo** en Python, comparado contra
   un simulador RV32I independiente: 24 casos dirigidos y **400 programas
   aleatorios, cero diferencias**.
2. **Testbenches exhaustivos** de las unidades de riesgos, recorriendo
   todo el espacio de entradas posible.
3. **Ejecución en la placa real**, paso a paso y libre, comparando trazas
   ciclo a ciclo contra el modelo.

> El argumento fuerte: *"no verificamos mirando si los números parecían
> razonables; comparamos contra una referencia independiente."*

**"¿Qué es `lui` y por qué hace falta?"**
Las constantes en las instrucciones tipo I tienen 12 bits: llegan hasta
2047. `lui` carga 20 bits en la parte alta del registro, y junto con un
`addi` arman cualquier número de 32 bits.

**"¿Qué diferencia hay entre `lb` y `lbu`?"**
Ambas traen un byte. `lb` lo interpreta **con signo** y completa el
registro con el bit de signo; `lbu` lo interpreta **sin signo** y
completa con ceros. El mismo byte `0xFF` da −1 con `lb` y 255 con `lbu`.

---

## Parte 10 — Guion para la demostración

1. **`demo_1_alu`** con **Run** → las 10 operaciones. Señalar
   `s7 = −8` (sra) contra `s6 = 4` (srl): mismo desplazamiento, distinto
   relleno. Y `s8 = 1` (slt) contra `s9 = 0` (sltu): mismo número, una
   comparación con signo y otra sin.

2. **`demo_2_memoria`** → mostrar `s5 = 0x0000FF00`: se escribió **un
   solo byte** en el medio de una palabra y los otros tres quedaron
   intactos. Y `s3 = −1` contra `s4 = 255`, el mismo byte leído con y sin
   signo.

3. **`demo_3_saltos`** con **Step**, con el panel de latches abierto →
   se ve la instrucción bajando etapa por etapa. Cuando el salto se toma,
   IF/ID se pone en cero: **es el vaciado en vivo**. Después señalar que
   `t2`, `t3` y `s5` quedaron en **cero**: esas instrucciones se
   buscaron y se descartaron.

4. **`demo_4_riesgos`** → `a3 = 50`. Explicar que ahí el adelantamiento
   no alcanzaba y el pipeline tuvo que frenar un ciclo.

5. **`demo_5_suma`** con **Run** → un algoritmo de verdad: guarda cinco
   números en memoria, los recorre con un puntero y los suma.
   `a0 = 150`.
