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

### Códigos de operación

| Código | Operación | | Código | Operación |
|---|---|---|---|---|
| `0000` | AND | | `0101` | SRL (desplaza der. lógico) |
| `0001` | OR | | `0110` | SUB |
| `0010` | ADD | | `0111` | SLT (menor, con signo) |
| `0011` | XOR | | `1000` | SRA (desplaza der. aritmético) |
| `0100` | SLL (desplaza izq.) | | `1001` | SLTU (menor, sin signo) |

Los cuatro originales (`0000`, `0001`, `0010`, `0110`) mantienen su valor para no
romper lo que ya andaba.

### Tabla de decodificación

| ALUOp1 | ALUOp0 | I[30] | I[14] | I[13] | I[12] | Operación | Instrucción |
|---|---|---|---|---|---|---|---|
| 0 | 0 | X | X | X | X | `0010` ADD | cargas, stores, lui, jalr |
| 0 | 1 | X | X | X | X | `0110` SUB | beq, bne |
| 1 | 0 | 0 | 0 | 0 | 0 | `0010` ADD | add |
| 1 | 0 | 1 | 0 | 0 | 0 | `0110` SUB | sub |
| 1 | 0 | X | 0 | 0 | 1 | `0100` SLL | sll |
| 1 | 0 | X | 0 | 1 | 0 | `0111` SLT | slt |
| 1 | 0 | X | 0 | 1 | 1 | `1001` SLTU | sltu |
| 1 | 0 | X | 1 | 0 | 0 | `0011` XOR | xor |
| 1 | 0 | 0 | 1 | 0 | 1 | `0101` SRL | srl |
| 1 | 0 | 1 | 1 | 0 | 1 | `1000` SRA | sra |
| 1 | 0 | X | 1 | 1 | 0 | `0001` OR | or |
| 1 | 0 | X | 1 | 1 | 1 | `0000` AND | and |
| 1 | 1 | **X** | 0 | 0 | 0 | `0010` ADD | addi |
| 1 | 1 | X | 0 | 0 | 1 | `0100` SLL | slli |
| 1 | 1 | X | 0 | 1 | 0 | `0111` SLT | slti |
| 1 | 1 | X | 0 | 1 | 1 | `1001` SLTU | sltiu |
| 1 | 1 | X | 1 | 0 | 0 | `0011` XOR | xori |
| 1 | 1 | 0 | 1 | 0 | 1 | `0101` SRL | srli |
| 1 | 1 | 1 | 1 | 0 | 1 | `1000` SRA | srai |
| 1 | 1 | X | 1 | 1 | 0 | `0001` OR | ori |
| 1 | 1 | X | 1 | 1 | 1 | `0000` AND | andi |

### ⚠️ El bit I[30] no se usa igual en ALUOp `10` que en `11`

Es la trampa de esta tabla:

- Con **ALUOp = 10** (tipo R) el bit 30 es el `funct7` de verdad, y distingue
  `add`/`sub` y `srl`/`sra`.
- Con **ALUOp = 11** (tipo I) ese bit **es parte del inmediato**. Un
  `addi x1, x0, -1` tiene el bit 30 en 1, así que usarlo para elegir entre suma
  y resta convertiría toda suma con número negativo en una resta.
- La única excepción son `srli`/`srai`, donde el inmediato sí lleva el `funct7`
  en su parte alta porque el desplazamiento sólo usa 5 bits.

Por eso la fila de `addi` lleva **X** en I[30] y la de `srli`/`srai` no.

### Nota sobre la tabla anterior

La tabla vieja tenía la fila `X 1 X XXX → 0110 SUB`, que con ALUOp1 en "no
importa" abarca tanto `01` como `11`. O sea que, leída literalmente, decía que
`addi` resta. El código nunca hizo eso (tenía un caso `2'b11` aparte), así que
era un error de la documentación y no del diseño — pero conviene corregirlo en
el informe.
