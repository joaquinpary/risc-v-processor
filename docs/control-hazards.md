# Riesgos de Control — Flush estático (Predict Not Taken)

> **Estado: implementado.** Este documento describe el diseño y las trampas que
> aparecieron al aplicarlo. La verificación está en `tools/test_pipeline.py`.

Predicción estática **"siempre no salta"**: el pipeline sigue buscando en secuencia
y, si el salto resulta tomado, se vacían (flush) las instrucciones equivocadas.

Resolución del salto en **EX**, no en MEM: cuanto antes se decida, menos
instrucciones equivocadas entran.

## ⚠️ Son TRES instrucciones en vuelo, no dos

El modelo clásico de 5 etapas dice que resolver en EX cuesta 2 ciclos. **Acá
cuesta 3**, porque la BRAM de instrucciones agrega una etapa que ese modelo no
contempla. En el momento en que el salto se confirma hay tres instrucciones del
camino equivocado dando vueltas:

1. la que está en ID,
2. la que ya salió de la BRAM y espera en `doutb`,
3. **la que se está buscando en ese mismo ciclo**, que va a aparecer en `doutb`
   al ciclo siguiente — el redireccionamiento del PC llega tarde para evitarla.

Vaciar IF/ID un solo ciclo mata (1) y (2) pero **deja pasar (3)**. Esto no es
teórico: se detectó con `jalr`, que ejecutaba la instrucción ubicada tres
lugares después del salto. Por eso el vaciado del frente dura dos ciclos
(`flush_if = flush | flush_d1`).

> Requiere tener aplicada la etapa de riesgos de datos
> ([hazard-mitigation.md](hazard-mitigation.md)): el flush interactúa con el
> stall de load-use y con el skid buffer del fetch.

---

## 0. Prerrequisitos: tres bugs que rompen TODO salto

Sin estos tres arreglos el flush funciona pero salta a la dirección equivocada.

### 0.1 Desplazamiento doble del inmediato (`execute.v`)

`imm_gen.v` **ya entrega el offset en bytes**: para B-type
(línea 22) e J-type (línea 30) el inmediato termina en `1'b0`, o sea que el
desplazamiento ×2 ya está hecho. Pero `execute.v` lo vuelve a desplazar:

```verilog
// MAL — duplica el offset
wire [31:0] imm_shifted = {imm_gen_i[30:0], 1'b0};
assign pc_branch_o = pc_i + imm_shifted;
```

Todos los saltos caen al **doble** de la distancia pedida. Fix:

```verilog
// BIEN — el inmediato ya viene en bytes desde imm_gen
assign pc_branch_o = pc_i + imm_gen_i;
```

### 0.2 Desalineación de +4 entre el PC y su instrucción (`instruction_fetch.v`)

La BRAM de instrucciones tiene latencia 1, así que la instrucción sale un ciclo
después de presentar la dirección — pero el PC ya avanzó. Resultado: `pc_id`
apunta a la instrucción **siguiente** a `instruction_id`.

| Ciclo | `pc_reg` | `doutb` (instrucción) | Latcheado en IF/ID |
|---|---|---|---|
| N | P | — | — |
| N+1 | P+4 | `mem[P]` | `instruction_id = mem[P]` pero `pc_id = P+4` ✗ |

Como el destino se calcula `pc + imm`, **todo salto queda +4 corrido**, y el
valor de enlace de `jal` (`pc+4`) queda en realidad en `pc+8`. Fix: un registro
que retrase el PC un ciclo para que viaje junto a su instrucción.

```verilog
    // pc_reg direcciona la BRAM; pc_fetched va un ciclo atrás, alineado con
    // la instruccion que sale por doutb
    reg [31:0] pc_fetched;

    always @(posedge clk) begin
        if (reset)
            pc_fetched <= 32'h0000_0000;
        else if (pc_write_en_i)
            pc_fetched <= pc_reg;
    end

    instruction_memory instruction_memory (
        ...
        .addrb  (pc_reg[11:2]),        // antes: pc_o[11:2]
        ...
    );

    assign pc_o        = pc_fetched;            // antes: pc_reg
    assign pc_plus_4_o = pc_fetched + 32'd4;    // antes: pc_reg + 4
```

Verificación en reset: ciclo 1 `pc_reg=0`, `pc_fetched=0`; ciclo 2 `pc_reg=4`,
`pc_fetched=0` y `doutb=mem[0]` → la instrucción en la dirección 0 viaja con
`pc=0`. Correcto. Durante un stall ambos registros se congelan juntos
(comparten `pc_write_en_i`), así que la alineación se mantiene.

> Nota: `debug_pc` en `top.v` pasa a mostrar el PC de la instrucción que está en
> ID (antes mostraba el del fetch en curso). Es más útil para depurar, pero
> tenelo en cuenta al leer el dashboard.

### 0.3 BNE no está implementado (`memory.v` → se reemplaza)

La condición actual es `pc_src_o = (branch & zero_i) | jump`, que solo sirve para
**BEQ**. Un `BNE` salta cuando los operandos son **distintos**, o sea con
`zero = 0`. Se resuelve con `funct3`, que ya viaja por el pipeline. La lógica
nueva va en EX (sección 1) y la de `memory.v` se elimina (sección 4).

---

## 1. Lógica de decisión del salto en EX

Va en `top.v`. Todas las señales ya existen: `control_bus_ex` (bus de control en
EX), `zero_o_ex` y `pc_branch_o_ex` (salidas de `execute`), y `funct3_ex`.

```verilog
// =========================================================================
// RESOLUCION DE SALTOS EN EX (Predict Not Taken)
// =========================================================================
wire branch_ex = control_bus_ex[6];    // Branch
wire jump_ex   = control_bus_ex[3];    // Jump (jal / jalr)

// La ALU resta para branches (ALUOp=01 -> alu_ctrl=0110), asi que
// zero_o_ex = (rs1 == rs2). funct3 elige la polaridad.
reg branch_cond_ok;
always @(*) begin
    case (funct3_ex)
        3'b000:  branch_cond_ok =  zero_o_ex;   // BEQ: salta si son iguales
        3'b001:  branch_cond_ok = ~zero_o_ex;   // BNE: salta si son distintos
        default: branch_cond_ok =  zero_o_ex;
    endcase
end

wire branch_taken_ex = (branch_ex & branch_cond_ok) | jump_ex;

// Destino: pc+imm para beq/bne/jal. (jalr usaria result_o_ex = rs1+imm)
wire [31:0] branch_target_ex = pc_branch_o_ex;

// Señal global de vaciado
wire flush = branch_taken_ex;
```

Para soportar también **JALR** (fuera del alcance pedido, pero es una línea):

```verilog
wire jalr_ex = jump_ex & control_bus_ex[7];   // ALUSrc=1 solo en jalr, no en jal
wire [31:0] branch_target_ex = jalr_ex ? result_o_ex : pc_branch_o_ex;
```

---

## 2. Latch IF/ID con flush

Cuando el salto se resuelve en EX, la instrucción que está en ID pertenece al
camino equivocado → se convierte en burbuja.

**El flush tiene prioridad sobre el freeze del stall** (`if_id_write`). En la
práctica no pueden coexistir —una instrucción en EX no puede ser load y branch a
la vez— pero el orden correcto lo deja a prueba de futuros cambios.

```verilog
    // ===== IF/ID latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            pc_id           <= 32'b0;
            pc_plus_4_id    <= 32'b0;
            instruction_id  <= 32'b0;
            if_id_valid     <= 1'b0;
        end else if (cpu_enable) begin
            if (flush) begin
                // Burbuja: instruccion del camino no tomado
                pc_id           <= 32'b0;
                pc_plus_4_id    <= 32'b0;
                instruction_id  <= 32'b0;
                if_id_valid     <= 1'b0;
            end else if (if_id_write) begin
                pc_id           <= pc_if;
                pc_plus_4_id    <= pc_plus_4_if;
                instruction_id  <= instruction_if_eff;
                if_id_valid     <= 1'b1;
            end
        end
    end
```

`instruction_id = 0` decodifica a opcode `0000000`, que cae en el `default` de
`control.v` y pone todo el bus de control en cero: la burbuja es inofensiva.

### ⚠️ `if_id_valid` es obligatorio, no decorativo

`top.v` detecta el fin del programa así:

```verilog
assign cpu_halted = (instruction_id == 32'b0 && pc_if > 32'h00000010);
```

Al vaciar IF/ID ponemos `instruction_id = 0`, que es **exactamente** el patrón
que dispara el halt. Sin protección, **cada salto tomado más allá de la
dirección 0x10 frenaría el procesador** en modo RUN. Por eso se agrega un bit de
validez:

```verilog
reg if_id_valid;    // declarar junto a los demas registros del latch

assign cpu_halted = (instruction_id == 32'b0) && if_id_valid
                                              && (pc_if > 32'h00000010);
```

Una burbuja tiene `if_id_valid = 0` y ya no se confunde con el fin del programa.

---

## 3. Latch ID/EX con flush

La instrucción que estaba en ID no debe llegar a ejecutarse: se anula su bus de
control. Se combina con la burbuja del stall de load-use por OR.

```verilog
    // ===== ID/EX latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            ...
            control_bus_ex  <= 10'b0;
            rs1_ex          <= 5'b0;
            rs2_ex          <= 5'b0;
        end else if (cpu_enable) begin
            pc_ex           <= pc_o_id;
            pc_plus_4_ex    <= pc_plus_4_o_id;
            read_data_1_ex  <= read_data_1_o_id;
            read_data_2_ex  <= read_data_2_o_id;
            imm_gen_ex      <= imm_gen_o_id;
            funct3_ex       <= funct3_o_id;
            bit30_ex        <= bit30_o_id;
            rd_ex           <= rd_o_id;
            rs1_ex          <= rs1_addr_id;
            rs2_ex          <= rs2_addr_id;

            // Burbuja por stall (control_mux) O por flush de salto tomado
            control_bus_ex  <= (control_mux | flush) ? 10'b0 : control_bus_o_id;
        end
    end
```

Alcanza con anular el bus de control: con `RegWrite`, `MemWrite`, `Branch` y
`Jump` en cero, los datos que arrastre la burbuja no tienen ningún efecto.

---

## 4. Multiplexor del PC

El redireccionamiento pasa de MEM a EX. En la instancia de `instruction_fetch`
en `top.v`:

```verilog
    instruction_fetch u_if (
        ...
        .pc_write_en_i  (cpu_enable & (pc_write | branch_taken_ex)),
        .pc_src_i       (branch_taken_ex),      // antes: pc_src_mem
        .pc_branch_i    (branch_target_ex),     // antes: pc_branch_o_mem
        ...
    );
```

El `| branch_taken_ex` le da prioridad al salto sobre el freeze del stall.

El MUX interno de `instruction_fetch` **no cambia** — ya está bien escrito:

```verilog
    always @(posedge clk) begin
        if (reset) begin
            pc_reg <= 32'h0000_0000;
        end else if (pc_write_en_i) begin
            if (pc_src_i) begin
                pc_reg <= pc_branch_i;      // destino del salto
            end else begin
                pc_reg <= pc_reg + 32'd4;   // secuencial (prediccion)
            end
        end
    end
```

### Desconectar el redireccionamiento viejo de MEM

**Crítico**: si `memory.v` sigue manejando el PC vas a tener un doble salto.
En `memory.v`:

```verilog
    assign pc_src_o = 1'b0;   // resolucion movida a EX (control hazards)
```

En `top.v` quedan sin uso `pc_src_mem` y `pc_branch_o_mem`; también dejan de
tener sentido `zero_mem`, `pc_branch_mem` y el `pc_branch_ex <= pc_branch_o_ex`
del latch ID/EX (que además siempre fue un lazo raro: una salida de EX
realimentada al latch de entrada). Se pueden borrar en una limpieza aparte.

---

## 5. Interacción con el skid buffer

El skid buffer del fetch guarda la palabra en vuelo de la BRAM durante un stall.
Si se vacía el pipeline con el skid cargado, esa palabra pertenece al camino
equivocado y se inyectaría después del salto. **El flush tiene que invalidarlo:**

```verilog
    always @(posedge clk) begin
        if (pipeline_reset) begin
            instr_skid       <= 32'b0;
            instr_skid_valid <= 1'b0;
        end else if (cpu_enable) begin
            if (flush) begin
                instr_skid_valid <= 1'b0;   // descartar: camino no tomado
            end else if (stall) begin
                if (!instr_skid_valid) begin
                    instr_skid       <= instruction_if;
                    instr_skid_valid <= 1'b1;
                end
            end else begin
                instr_skid_valid <= 1'b0;
            end
        end
    end
```

Con la lógica actual el caso es inalcanzable (stall y flush se excluyen, y el
skid solo vive un ciclo), pero el razonamiento es lo bastante delicado como para
no depender de él.

---

## 6. Timeline del flush

Programa: `beq x1,x2,DEST` en `0x10`, `I2` en `0x14`, `I3` en `0x18`, `DEST` en `0x40`.

```
ciclo N   : beq en EX; I2 en ID; I3 esperando en doutb; se busca I4
            branch_cond_ok=1 -> branch_taken_ex=1 -> flush=1
            branch_target_ex = 0x10 + imm = 0x40
flanco N  : PC <- 0x40                    (redireccion)
            IF/ID <- burbuja              (I3 descartada)
            ID/EX <- burbuja              (I2 descartada)
            flush_d1 <- 1
            beq -> MEM (sigue normal, no escribe nada)
ciclo N+1 : flush_if sigue en 1 por flush_d1; doutb trae I4 (camino equivocado)
flanco N+1: IF/ID <- burbuja              (I4 descartada)
ciclo N+2 : doutb trae DEST (0x40)
flanco N+2: IF/ID <- DEST
ciclo N+3 : DEST en ID
```

Penalidad: **3 ciclos** por salto tomado. Los saltos no tomados no cuestan nada
(de ahí lo de "predict not taken"). Para `jal`, `jump_ex=1` siempre, así que
siempre paga los 2 ciclos.

---

## 7. Checklist de aplicación

| # | Archivo | Cambio |
|---|---|---|
| 1 | `execute.v` | Sacar `imm_shifted`, usar `pc_i + imm_gen_i` |
| 2 | `instruction_fetch.v` | Registro `pc_fetched`, `addrb` desde `pc_reg` |
| 3 | `top.v` | Bloque de resolución en EX (`branch_taken_ex`, `flush`) |
| 4 | `top.v` | Flush en latch IF/ID (2 ciclos: `flush_if`) + `if_id_valid` |
| 5 | `top.v` | Flush en latch ID/EX (`control_mux \| flush_if`) |
| 6 | `top.v` | `pc_src_i` / `pc_branch_i` desde EX, `pc_write_en_i` con prioridad |
| 7 | `top.v` | `cpu_halted` con `if_id_valid` |
| 8 | `top.v` | Flush invalida el skid buffer |
| 9 | `memory.v` | `pc_src_o = 1'b0` |

### Programa mínimo de prueba

```asm
        addi x1, x0, 5
        addi x2, x0, 5
        beq  x1, x2, DEST     # tomado -> 2 burbujas
        addi x3, x0, 99       # NO debe ejecutarse  (x3 = 0)
        addi x4, x0, 88       # NO debe ejecutarse  (x4 = 0)
DEST:   addi x5, x0, 7        # x5 = 7
        bne  x1, x2, FIN      # NO tomado -> sigue derecho
        addi x6, x0, 1        # x6 = 1
FIN:    jal  x7, END          # x7 = pc+4, 2 burbujas
        addi x8, x0, 77       # NO debe ejecutarse  (x8 = 0)
END:    ...
```

Esperado: `x3=0`, `x4=0`, `x5=7`, `x6=1`, `x8=0`. Si `x3`/`x4` quedan cargados,
el flush no está vaciando; si el salto cae en otra dirección, revisá los
prerrequisitos 0.1 y 0.2.
