# Profundidad real del pipeline — la etapa IF ocupa dos ciclos

> **Estado: analizado, no modificado.** Es una decisión de diseño consciente, no
> un bug pendiente. Este documento existe para que la profundidad real del
> pipeline esté escrita en algún lado y no haya que redescubrirla leyendo el RTL.

El procesador se describe como de **5 etapas** (IF, ID, EX, MEM, WB), y las
etapas lógicas efectivamente son cinco. Pero la etapa **IF ocupa dos ciclos**
porque la memoria de instrucciones es una block RAM con salida registrada. En
niveles de registro el pipeline tiene **seis**, no cinco.

---

## 1. La evidencia

Traza de arranque en frío con cinco `addi` consecutivas (`addi x1,x0,1` en la
dirección 0, `addi x2,x0,2` en la 4, etc.), generada con el modelo ciclo a ciclo
de `tools/test_pipeline.py`:

```
ciclo | pc_reg | pc_fetched | doutb (BRAM) | IF/ID.ins | ID/EX.rd | EX/MEM.rd | MEM/WB.rd
------|--------|------------|--------------|-----------|----------|-----------|----------
   0  | 0x0000 |   0x0000   | --           | --        |    x0    |    x0     |   x0
   1  | 0x0004 |   0x0000   | addi x1      | --        |    x0    |    x0     |   x0
   2  | 0x0008 |   0x0004   | addi x2      | addi x1   |    x0    |    x0     |   x0
   3  | 0x000C |   0x0008   | addi x3      | addi x2   |    x1    |    x0     |   x0
   4  | 0x0010 |   0x000C   | addi x4      | addi x3   |    x2    |    x1     |   x0
   5  | 0x0014 |   0x0010   | addi x5      | addi x4   |    x3    |    x2     |   x1
   6  | 0x0018 |   0x0014   | nop          | addi x5   |    x4    |    x3     |   x2
```

Seguí la primera instrucción (`addi x1`) por la diagonal:

| Ciclo | Dónde está | Etapa |
|---|---|---|
| 0 | `pc_reg = 0x0000` presenta la dirección a la BRAM | **IF1** |
| 1 | salió por `doutb` | **IF2** |
| 2 | está en el latch IF/ID, lista para decodificar | **ID** |
| 3 | está en ID/EX (`rd = x1`) | **EX** |
| 4 | está en EX/MEM | **MEM** |
| 5 | está en MEM/WB | **WB** |

Se pide en el ciclo 0 y se retira en el 5: **seis ciclos de latencia**. En un
pipeline de 5 etapas de libro serían cinco.

---

## 2. Por qué pasa

La instrucción atraviesa **dos registros** antes de llegar a ID:

1. **El registro de salida de la BRAM** (`doutb` de `instruction_memory`). Una
   block RAM síncrona tiene latencia de lectura 1 por construcción: la palabra
   aparece un ciclo *después* de presentar la dirección. No se puede leer de
   forma combinacional.
2. **El latch IF/ID** (`instruction_id` en `top.v`).

Un pipeline de 5 etapas debería tener uno solo entre el fetch y la
decodificación. Acá hay dos, y el de la BRAM no es opcional: viene con la
primitiva.

### El camino de datos NO tiene este problema

Vale aclararlo porque es el mismo tipo de estructura y podría confundirse. En
`memory.v` la dirección `addra` se presenta durante MEM y `douta` aparece en WB;
`write_back` lee `read_data_o_mem` (= `douta`) directamente, sin registro
intermedio. O sea que **el registro de salida de la BRAM de datos *es* el latch
MEM/WB** para el dato leído: un solo registro, como corresponde.

Ese lado estuvo doble-registrado en su momento (existía un `read_data_wb` además
de `douta`) y se corrigió. El lado de instrucciones sigue doble-registrado, con
el atenuante de que ahí el segundo registro **sí hace trabajo útil** (ver §4).

---

## 3. Qué cuesta

### 3.1 La penalidad de salto es 3 ciclos, no 2

Es la consecuencia importante. Al resolver el salto en EX hay **tres**
instrucciones del camino equivocado en vuelo, no dos: la que está en ID, la que
espera en `doutb`, y la que se está buscando en ese mismo ciclo. Está
desarrollado en [control-hazards.md](control-hazards.md#-son-tres-instrucciones-en-vuelo-no-dos);
se detectó con `jalr`, que ejecutaba la instrucción ubicada tres lugares después
del salto, y se resolvió con un vaciado del frente de dos ciclos
(`flush_if = flush | flush_d1`).

### 3.2 El registro `pc_fetched` existe por esto

En `instruction_fetch.v`, `pc_fetched` va un ciclo atrás de `pc_reg` para que el
PC viaje junto a *su* instrucción. Sin él, el latch IF/ID guardaría la
instrucción de la dirección P junto con el PC P+4 y todos los saltos quedarían
corridos 4 bytes. Es puro costo de la latencia de la BRAM.

### 3.3 El skid buffer existe por esto

El puerto B de `instruction_memory` está generado **sin pin `ENB`**, así que su
registro de salida no se puede congelar: durante un stall de load-use la BRAM
sigue avanzando y la palabra en vuelo se perdería. El skid buffer
(`instr_skid` / `instr_skid_valid` en `top.v`) está ahí sólo para atajarla.

### 3.4 Lo que NO cuesta: productividad

En régimen permanente sigue saliendo **una instrucción por ciclo**. Un pipeline
más profundo no baja el throughput; sólo aumenta la latencia individual y el
costo de los saltos tomados. El CPI ideal sigue siendo 1.

---

## 4. ¿Se puede sacar el registro de más?

Sí, pero no es gratis y no es sólo borrar una línea.

El registro que sobra es `instruction_id`, no el de la BRAM (ese es
inevitable). La idea sería que **el registro de salida de la BRAM *sea* el latch
IF/ID**, igual que se hizo del lado de datos. El problema es que hoy
`instruction_id` hace dos cosas que `doutb` no puede hacer:

| Función | `instruction_id` | `doutb` (como está generado) |
|---|---|---|
| Congelarse durante un stall | sí (`if_id_write`) | **no** — falta el pin `ENB` |
| Vaciarse a NOP durante un flush | sí | **no** — una BRAM no se "limpia" |

O sea que con el IP actual el registro de más **no es redundante**: está
haciendo trabajo real. Para eliminarlo haría falta:

1. **Regenerar `instruction_memory` con `C_HAS_ENB = 1`** para poder congelar la
   lectura durante un stall.
2. **Muxear un NOP a la salida** para el flush, porque la BRAM no se puede
   vaciar: un registro de un bit `flush_pending` que fuerce `32'b0` en el camino
   de la instrucción durante los ciclos correspondientes.
3. `pc_fetched` pasa a cumplir el rol de `pc_id`.
4. Rehacer la lógica de stall/flush de `top.v` y volver a verificar todo.

A cambio se obtiene:

- desaparece `instruction_id`,
- **desaparece el skid buffer entero** (con `ENB` ya no hay palabra en vuelo que
  perder),
- la penalidad de salto baja de 3 a 2 ciclos,
- queda un pipeline de 5 niveles de registro, coincidente con la descripción
  clásica.

### Alternativa descartada: memoria de instrucciones asíncrona

Usar RAM distribuida (LUTRAM) daría lectura combinacional y un IF de un solo
ciclo sin ninguna de las complicaciones de arriba. Se descarta porque 1024
palabras × 32 bits = 32 Kbit implementados en LUTs consumirían una porción
importante del Artix-7 35T para reemplazar un recurso (block RAM) que está
sobrando.

---

## 5. Decisión

**Se deja como está.** El diseño funciona y está verificado (`tools/test_pipeline.py`:
24 casos dirigidos + 400 programas aleatorios contra una referencia secuencial,
0 diferencias) y validado en placa. La refactorización de §4 toca el IP, la
lógica de stall y la de flush a la vez, con riesgo real de romper algo que hoy
anda, y el beneficio es un ciclo menos por salto tomado.

Queda anotada como mejora posible si sobra tiempo después de sintetizar y probar
el set de instrucciones completo.

### Cómo se explica en el informe

Tener la salida de la memoria de instrucciones registrada **es lo normal en un
diseño sobre FPGA**: es una consecuencia de usar block RAM, no un descuido. La
formulación correcta es:

> El procesador implementa las cinco etapas clásicas (IF, ID, EX, MEM, WB). La
> etapa IF ocupa dos ciclos de reloj porque la memoria de instrucciones es una
> block RAM con salida registrada, cuya latencia de lectura es de un ciclo. Esto
> no afecta la productividad —se retira una instrucción por ciclo en régimen
> permanente— pero sí eleva la penalidad de un salto tomado de 2 a 3 ciclos, lo
> que se contempla en la lógica de vaciado.

Lo que no conviene es afirmar "5 etapas" a secas: si alguien traza el datapath
se va a encontrar con seis niveles de registro y va a parecer un error.
