# Tablas de control

Estado actual del `control.v` y del `alu_control.v` después de completar el set
de instrucciones. Las 32 instrucciones que pide la consigna están cubiertas.

---

## 1. Unidad de control

Bus de control de 10 bits: `ALUOp[9:8] ALUSrc[7] Branch[6] MemRead[5] MemWrite[4] Jump[3] RegWrite[2] MemtoReg[1:0]`

| Tipo de instrucción | Opcode | ALUOp | ALUSrc | Branch | MemRead | MemWrite | Jump | RegWrite | MemtoReg |
|---|---|---|---|---|---|---|---|---|---|
| R-Type (add, sub, sll, srl, sra, and, or, xor, slt, sltu) | `0110011` | `10` | 0 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| I-Type aritmética (addi, andi, ori, xori, slti, sltiu, slli, srli, srai) | `0010011` | `11` | 1 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| I-Type carga (lb, lh, lw, lbu, lhu) | `0000011` | `00` | 1 | 0 | 1 | 0 | 0 | 1 | `01` (Mem) |
| S-Type almacenamiento (sb, sh, sw) | `0100011` | `00` | 1 | 0 | 0 | 1 | 0 | 0 | `00` |
| B-Type salto condicional (beq, bne) | `1100011` | `01` | 0 | 1 | 0 | 0 | 0 | 0 | `00` |
| U-Type (lui) | `0110111` | `00` | 1 | 0 | 0 | 0 | 0 | 1 | `00` (ALU) |
| J-Type (jal) | `1101111` | `00` | **0** | 0 | 0 | 0 | 1 | 1 | `10` (PC+4) |
| I-Type salto (jalr) | `1100111` | `00` | **1** | 0 | 0 | 0 | 1 | 1 | `10` (PC+4) |

Esta tabla **no cambió** respecto de la original: `control.v` ya estaba bien. Lo
que cambió son dos casillas que antes figuraban como "no importa":

- **`ALUSrc` de `jal` y `jalr` ya no es indiferente.** La resolución del salto en
  EX distingue una de otra con esa señal: `jalr_ex = Jump & ALUSrc`. `jal` salta
  a `pc+imm` y `jalr` a `rs1+imm` (el resultado de la ALU), así que `jal` tiene
  que valer 0 y `jalr` 1.
- **`ALUOp` de `lui` y `jal` es `00`, no `XX`.** `lui` necesita que la ALU sume
  para dejar pasar el inmediato (ver la nota de abajo).

### Registros fuente efectivos (nuevo, en `instruction_decode.v`)

No todos los formatos usan los campos `rs1`/`rs2` como registro: en varios son
bits del inmediato. Si se los tratara como registros, `lui` leería un registro
cualquiera y lo sumaría, y la unidad de forwarding podría adelantar un valor
sobre esos bits. Por eso se fuerzan a `x0`:

| Formato | ¿rs1 es registro? | ¿rs2 es registro? |
|---|---|---|
| R-Type | sí | sí |
| S-Type, B-Type | sí | sí |
| I-Type (aritmética, cargas, jalr) | sí | **no → x0** |
| U-Type (lui) | **no → x0** | **no → x0** |
| J-Type (jal) | **no → x0** | **no → x0** |

Con `rs1 = x0`, `lui` calcula `0 + inmediato = inmediato`, que es lo que
corresponde.

---

## 2. Control de la ALU

`alu_control` y `alu` son dos bloques separados y conviene documentarlos por
separado: **qué** código de operación existe y qué hace cada uno (`alu`), y
**cómo se elige** ese código a partir de `ALUOp`/`funct3`/`I[30]` (`alu_control`).
La versión anterior de este documento mezclaba las dos cosas en una tabla
indexada por instrucción — el problema es que a `alu_control` no le importa
qué instrucción es, solo mira esos tres campos de control. Queda reordenado
así.

### 2.1 Códigos de operación (bus interno `alu_control` → `alu`)

Los mismos diez códigos están declarados como `localparam` en los dos módulos
(`alu_control.v` y `alu.v`), para que el bus de 4 bits que los conecta tenga
un único significado:

| Código | Valor | Qué calcula `alu.v` |
|---|---|---|
| `ALU_AND` | `0000` | `data_a & data_b` |
| `ALU_OR` | `0001` | `data_a \| data_b` |
| `ALU_ADD` | `0010` | `data_a + data_b` |
| `ALU_XOR` | `0011` | `data_a ^ data_b` |
| `ALU_SLL` | `0100` | `data_a << shamt` |
| `ALU_SRL` | `0101` | `data_a >> shamt` (lógico) |
| `ALU_SUB` | `0110` | `data_a − data_b` |
| `ALU_SLT` | `0111` | `1` si `data_a < data_b` con signo, si no `0` |
| `ALU_SRA` | `1000` | `data_a >>> shamt` (aritmético, con signo) |
| `ALU_SLTU` | `1001` | `1` si `data_a < data_b` sin signo, si no `0` |

`shamt` es `data_b[4:0]` — mismo campo para R-type (`shamt` está en `rs2`) y
para I-type (`shamt` está en `imm[4:0]`), así que no hace falta distinguir el
formato acá tampoco. Los cuatro códigos originales (`AND`, `OR`, `ADD`, `SUB`)
mantienen su valor de antes para no romper nada que ya funcionaba; el resto se
agregó para completar las 32 instrucciones.

### 2.2 Cómo `alu_control` elige el código — generalizado, no por instrucción

`alu_control.v` es una función de tres entradas — `ALUOp[1:0]`, `funct3` e
`I[30]` — y nada más. No necesita saber si la instrucción es `add` o `sll`:
esa información ya está codificada en esos tres campos por `control.v` y por
el propio formato de la instrucción.

Con `ALUOp = 00` y `ALUOp = 01` la salida es fija, sin mirar `funct3` ni
`I[30]`:

| ALUOp | Código | Para qué |
|---|---|---|
| `00` | `ALU_ADD` | direcciones de memoria (`lw`/`sw`), `lui`, `jalr` |
| `01` | `ALU_SUB` | ramas (`beq`/`bne`) — `zero_o` dice si `rs1 == rs2` |

Con `ALUOp = 10` (R-type) y `ALUOp = 11` (I-type aritmético), la salida es
**la misma función de `funct3`** en los dos casos, con una sola excepción:

| `funct3` | Código | ¿`I[30]` importa? |
|---|---|---|
| `000` | `ALU_ADD`, o `ALU_SUB` si `I[30]=1` **solo cuando `ALUOp=10`** — con `ALUOp=11` siempre `ALU_ADD` | Sí, pero únicamente en R-type |
| `001` | `ALU_SLL` | No |
| `010` | `ALU_SLT` | No |
| `011` | `ALU_SLTU` | No |
| `100` | `ALU_XOR` | No |
| `101` | `ALU_SRL`, o `ALU_SRA` si `I[30]=1` | Sí, en los dos casos |
| `110` | `ALU_OR` | No |
| `111` | `ALU_AND` | No |

La única fila que se comporta distinto según `ALUOp` es `funct3 = 000`: en
R-type (`add`/`sub`) el bit 30 es el `funct7` real de la instrucción y decide
entre sumar y restar; en I-type (`addi`) ese mismo bit es parte del
inmediato — un `addi x1, x0, -1` lo tiene en 1 — así que usarlo ahí
convertiría cualquier suma con un negativo en una resta, y por eso se ignora:
`addi` siempre suma, sin importar `I[30]`.

`funct3 = 101` (desplazamiento a la derecha) sí depende de `I[30]` en los dos
casos (`srl`/`sra` y `srli`/`srai`), porque el formato de desplazamiento
inmediato también lleva el bit real de `funct7` en esa posición — ahí no hay
ambigüedad ni excepción.

Es la misma información que tenía la tabla anterior (20 filas separadas para
R-type e I-type), pero reducida a lo que la lógica realmente decide: una
función de `funct3` con una única excepción puntual, en vez de dos tablas
casi idénticas. También corrige, de paso, un error de una versión todavía más
vieja de esta tabla, que tenía una fila `ALUOp1=1, X, X → SUB` que —leída
literalmente, con `ALUOp0` en "no importa"— decía que `addi` resta. El código
nunca hizo eso; era un error de documentación, ya resuelto acá.

### 2.3 Referencia: qué instrucción dispara cada combinación

Por si hace falta cruzarlo con el informe, la relación instrucción → entradas
de `alu_control` (no es lógica nueva, es la misma tabla de 2.2 leída con el
mnemónico al lado):

| Instrucción | ALUOp | `funct3` | `I[30]` | Código resultante |
|---|---|---|---|---|
| `add` | `10` | `000` | `0` | `ALU_ADD` |
| `sub` | `10` | `000` | `1` | `ALU_SUB` |
| `sll` | `10` | `001` | — | `ALU_SLL` |
| `slt` | `10` | `010` | — | `ALU_SLT` |
| `sltu` | `10` | `011` | — | `ALU_SLTU` |
| `xor` | `10` | `100` | — | `ALU_XOR` |
| `srl` | `10` | `101` | `0` | `ALU_SRL` |
| `sra` | `10` | `101` | `1` | `ALU_SRA` |
| `or` | `10` | `110` | — | `ALU_OR` |
| `and` | `10` | `111` | — | `ALU_AND` |
| `addi` | `11` | `000` | ignorado | `ALU_ADD` |
| `slli` | `11` | `001` | — | `ALU_SLL` |
| `slti` | `11` | `010` | — | `ALU_SLT` |
| `sltiu` | `11` | `011` | — | `ALU_SLTU` |
| `xori` | `11` | `100` | — | `ALU_XOR` |
| `srli` | `11` | `101` | `0` | `ALU_SRL` |
| `srai` | `11` | `101` | `1` | `ALU_SRA` |
| `ori` | `11` | `110` | — | `ALU_OR` |
| `andi` | `11` | `111` | — | `ALU_AND` |
| `lw`/`sw`/`lui`/`jalr` | `00` | — | — | `ALU_ADD` |
| `beq`/`bne` | `01` | — | — | `ALU_SUB` |
