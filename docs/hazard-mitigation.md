# Riesgos de Datos (Data Hazards) — Forwarding + Load-Use Stall

**Branch:** `feat/hazard-mitigation`
**Alcance:** solo riesgos de datos. Los riesgos de control (branches/jumps/flush) quedan para la próxima fase.

Archivos nuevos en esta branch:

| Archivo | Qué es |
|---|---|
| `risc-v-processor.srcs/sources_1/new/forwarding_unit.v` | Unidad de adelantamiento (combinacional) |
| `risc-v-processor.srcs/sources_1/new/hazard_detection_unit.v` | Detección de load-use hazard (combinacional) |
| `risc-v-processor.srcs/sim_1/new/tb_forwarding_unit.v` | TB autoverificante, barrido exhaustivo (4.194.304 vectores) |
| `risc-v-processor.srcs/sim_1/new/tb_hazard_detection_unit.v` | TB autoverificante, barrido exhaustivo (65.536 vectores) |

---

## 1. forwarding_unit

Compara los registros fuente de la instrucción en EX contra los destinos de las
instrucciones en MEM (latch EX/MEM) y WB (latch MEM/WB), y elige el valor más
fresco para cada operando de la ALU.

Codificación de `forward_a` / `forward_b` (selección de los MUX 3-a-1):

| Código | Origen | Caso |
|---|---|---|
| `2'b00` | Banco de registros (ID/EX) | Sin riesgo |
| `2'b10` | Latch EX/MEM | EX hazard — prioridad **alta** |
| `2'b01` | Latch MEM/WB | MEM hazard — prioridad baja |

Decisiones de diseño:

- La prioridad del `if/else` implementa la regla del **double data hazard**: si
  EX/MEM y MEM/WB escriben el mismo registro (`add x1,…; add x1,…; add x2,x1,x1`),
  gana el resultado más nuevo (EX/MEM). La rama MEM/WB solo se alcanza si EX/MEM
  no está ya adelantando ese registro.
- **x0 nunca se adelanta** (guarda `rd != 0`): está cableado a cero.
- No hace falta un tercer atajo "a 3 instrucciones": `register.v` escribe en
  `negedge` (write-first), así que ese caso ya lo resuelve el banco de registros.

## 2. hazard_detection_unit

Detecta el riesgo **load-use**: un load produce su dato recién al final de MEM,
así que una instrucción dependiente que está en ID no se salva solo con
forwarding — hay que frenar el pipeline exactamente 1 ciclo y después adelantar
desde MEM/WB.

Condición: la instrucción en EX es load (`mem_read_id_ex=1`) **y** su `rd` (≠ x0)
coincide con `rs1` o `rs2` de la instrucción en ID.

Salidas ante un hazard:

| Señal | Valor | Polaridad | Efecto |
|---|---|---|---|
| `pc_write` | 0 | activa en **bajo** | Congela el PC |
| `if_id_write` | 0 | activa en **bajo** | Retiene la instrucción en IF/ID |
| `control_mux` | 1 | activa en **alto** | Inyecta burbuja (bus de control = 0) en ID/EX |

El stall se auto-limpia: la burbuja pone `MemRead=0` en EX, así que al ciclo
siguiente la condición desaparece sola. Nota: la unidad compara los *campos*
rs1/rs2 sin decodificar si la instrucción los usa (en `lui`/`jal` son bits de
inmediato); un falso match cuesta 1 ciclo de stall innecesario, nunca
corrección. Se puede refinar con un decode de opcode más adelante.

## 3. Verificación

- Sin simulador local, se hizo revisión adversarial multi-agente (6 revisores
  independientes) con trazas ciclo a ciclo contra `top.v`, `execute.v`,
  `control.v`, `memory.v`, `write_back.v`, `instruction_fetch.v` y los `.xci`
  de los IPs. Ambos módulos: aprobados (combinacionales puros, sin latches
  inferidos, sintetizables Verilog-2001).
- Los dos TB son **exhaustivos** (todo el espacio de entradas) contra un modelo
  de referencia recalculado por registro fuente; matan los mutantes de prioridad
  invertida, codificación invertida y guarda de x0 faltante.
- Falta el cierre formal: correr ambos TB en xsim (comandos al final).

---

## 4. Integración en top.v (paso a paso)

El mapa de bits del bus de control (de `control.v`, verificado también contra
los consumidores en `execute.v`/`memory.v`):

```
ALUOp[9:8]  ALUSrc[7]  Branch[6]  MemRead[5]  MemWrite[4]  Jump[3]  RegWrite[2]  MemtoReg[1:0]
```

- En EX: MemRead = `control_bus_ex[5]`
- En MEM: RegWrite = `control_mem[2]`, Jump = `control_mem[3]` (los slices `[6:0]` y `[2:0]` están anclados al LSB, los índices no se corren)
- En WB: RegWrite = `control_wb[2]`

### 4.1 Declaraciones nuevas

```verilog
// --- Hazard mitigation ---
wire [1:0]  forward_a, forward_b;
wire        pc_write, if_id_write, control_mux;
wire        stall = ~pc_write;                        // alias activo-alto

wire [4:0]  rs1_addr_id = instruction_id[19:15];      // campos rs de la instr. en ID
wire [4:0]  rs2_addr_id = instruction_id[24:20];

reg  [4:0]  rs1_ex, rs2_ex;                           // nuevos registros del latch ID/EX
```

### 4.2 Instancia de hazard_detection_unit (etapa ID)

```verilog
hazard_detection_unit u_hazard (
    .rs1_if_id      (rs1_addr_id),
    .rs2_if_id      (rs2_addr_id),
    .rd_id_ex       (rd_ex),
    .mem_read_id_ex (control_bus_ex[5]),   // bit MemRead de la instruccion en EX
    .pc_write       (pc_write),
    .if_id_write    (if_id_write),
    .control_mux    (control_mux)
);
```

### 4.3 Instancia de forwarding_unit (etapa EX)

```verilog
forwarding_unit u_forward (
    .rs1_id_ex        (rs1_ex),
    .rs2_id_ex        (rs2_ex),
    .rd_ex_mem        (rd_mem),
    .reg_write_ex_mem (control_mem[2]),    // RegWrite de la instruccion en MEM
    .rd_mem_wb        (rd_wb),
    .reg_write_mem_wb (control_wb[2]),     // RegWrite de la instruccion en WB
    .forward_a        (forward_a),
    .forward_b        (forward_b)
);
```

### 4.4 Los dos MUX 3-a-1 antes de la ALU

Van en `top.v` alimentando las entradas de `execute`: así el mux B queda
**antes** del mux ALUSrc interno (orden correcto), y el rs2 adelantado también
sale por `rs2_data_o` hacia los stores — `sw` con dato dependiente funciona
gratis.

```verilog
// Valor adelantado desde EX/MEM: para jal/jalr (Jump = control_mem[3]) lo que
// se escribe en el registro es pc+4, no el resultado de la ALU
wire [31:0] ex_mem_fwd_value = control_mem[3] ? pc_plus_4_mem : result_mem;

reg [31:0] alu_in_a_ex, alu_in_b_ex;
always @(*) begin
    case (forward_a)
        2'b10:   alu_in_a_ex = ex_mem_fwd_value;   // EX hazard (desde EX/MEM)
        2'b01:   alu_in_a_ex = reg_data_wb;        // MEM hazard (mux de WB: cubre loads)
        default: alu_in_a_ex = read_data_1_ex;     // sin riesgo: banco de registros
    endcase
    case (forward_b)
        2'b10:   alu_in_b_ex = ex_mem_fwd_value;
        2'b01:   alu_in_b_ex = reg_data_wb;
        default: alu_in_b_ex = read_data_2_ex;
    endcase
end
```

Y en la instancia `execute u_ex` cambian solo dos líneas:

```verilog
        .rs1_data_i     (alu_in_a_ex),      // antes: read_data_1_ex
        .rs2_data_i     (alu_in_b_ex),      // antes: read_data_2_ex
```

### 4.5 Congelar el PC (instancia instruction_fetch)

```verilog
        .pc_write_en_i  (cpu_enable & pc_write),   // antes: cpu_enable
```

### 4.6 Latch IF/ID: freeze + skid buffer (CRÍTICO)

`instruction_memory` es una BRAM con latencia de lectura 1 y **sin enable en el
puerto B** (`C_HAS_ENB=0` en el `.xci`): aunque se congelen PC e IF/ID, su
registro de salida (`doutb`) avanza un paso más durante el stall. Sin
corrección, cada stall **salta una instrucción y duplica la siguiente**
(traza verificada: la secuencia `I1,I2,I3,I4,I5` se convierte en
`I1,I2,I4,I4,I5`). El skid buffer captura la palabra en vuelo durante el ciclo
de stall y la restaura al liberar:

```verilog
// Skid buffer: preserva la palabra en vuelo de la BRAM durante un stall
reg  [31:0] instr_skid;
reg         instr_skid_valid;

always @(posedge clk) begin
    if (pipeline_reset) begin
        instr_skid       <= 32'b0;
        instr_skid_valid <= 1'b0;
    end else if (cpu_enable) begin
        if (stall) begin
            if (!instr_skid_valid) begin
                instr_skid       <= instruction_if;   // palabra que la BRAM va a pisar
                instr_skid_valid <= 1'b1;
            end
        end else begin
            instr_skid_valid <= 1'b0;
        end
    end
end

wire [31:0] instruction_if_eff = instr_skid_valid ? instr_skid : instruction_if;
```

```verilog
    // ===== IF/ID latch =====  (condicion + fuente de la instruccion)
    always @(posedge clk) begin
        if (pipeline_reset) begin
            pc_id           <= 32'b0;
            pc_plus_4_id    <= 32'b0;
            instruction_id  <= 32'b0;
        end else if (cpu_enable && if_id_write) begin   // antes: cpu_enable
            pc_id           <= pc_if;
            pc_plus_4_id    <= pc_plus_4_if;
            instruction_id  <= instruction_if_eff;      // antes: instruction_if
        end
    end
```

Alternativa de fondo (opcional): regenerar el IP `instruction_memory` con pin
`ENB` y manejarlo con `cpu_enable & pc_write`. Eso elimina la necesidad del skid
y de paso arregla el mismo problema que ya existe hoy en los pause/resume del
debug por UART (que también saltan/duplican una instrucción, desde siempre).

### 4.7 Latch ID/EX: burbuja + registros rs

```verilog
        if (pipeline_reset) begin
            ...
            rs1_ex          <= 5'b0;
            rs2_ex          <= 5'b0;
        end else if (cpu_enable) begin
            ...
            control_bus_ex  <= control_mux ? 10'b0 : control_bus_o_id;  // burbuja (NOP)
            rs1_ex          <= rs1_addr_id;
            rs2_ex          <= rs2_addr_id;
            ...
```

Con el bus de control en 0, RegWrite/MemWrite/Branch/Jump quedan en 0: el resto
de los campos del latch puede cargar normalmente sin efecto.

### 4.8 Timeline esperado del stall load-use

```
ciclo N   : lw x1 en EX (MemRead=1, rd=1), "add x2,x1,x3" en ID → hazard detectado
            pc_write=0, if_id_write=0, control_mux=1
flanco N  : burbuja entra a EX; lw pasa a MEM; add queda retenido en ID;
            el skid captura la palabra en vuelo de la BRAM
ciclo N+1 : burbuja en EX; lw en MEM; ya no hay hazard → todo se libera
flanco N+1: add entra a EX; instruction_id ← skid (la instrucción siguiente al add)
ciclo N+2 : add en EX, lw en WB → forwarding_unit da forward=01 y la ALU recibe
            el dato leído de memoria vía reg_data_wb
```

---

## 5. ⚠️ Bugs preexistentes que hay que arreglar ANTES de probar load-use

Los encontró la verificación al auditar el datapath. No son de esta tarea, pero
**los loads hoy no funcionan**, así que cualquier test del stall va a fallar por
la memoria, no por el hazard.

1. **`memory.v:28` — dirección incorrecta.** `mem_addr = data2_i[9:0]` usa el
   **valor de rs2** como dirección; la dirección efectiva `rs1+imm` llega en
   `result_i`. Fix:
   ```verilog
   wire [9:0] mem_addr = result_i[9:0];    // antes: data2_i[9:0]
   ...
   assign mem_addr_o = result_i;           // antes: data2_i
   ```
   (`dina` sí queda en `data2_i`: es el dato del store.)

2. **`data_memory` con latencia 2 + doble registro.** El IP tiene el
   "Primitives Output Register" del puerto A activado
   (`C_HAS_MEM_OUTPUT_REGS_A=1` en el `.xci`), y encima `top.v` re-registra
   `douta` en el latch MEM/WB → el dato del load llega a WB dos generaciones
   tarde. Fix en dos partes:
   - (a) Regenerar el IP sin ese registro (Tcl en la sección 6, o GUI:
     *Re-customize IP → Port A Options → destildar "Primitives Output Register"*).
   - (b) En la instancia `write_back` de `top.v`, el registro de salida de la
     BRAM ya **es** el latch MEM/WB natural:
     ```verilog
     .read_data_i    (read_data_o_mem),   // antes: read_data_wb
     ```
   - Opcional: apuntar el caso `8'd23` del latch de debug a la misma señal para
     que el debugger muestre lo que WB realmente usa.

3. **`write_back.v:16` — truncamiento a 1 bit.**
   `wire mem_to_reg = control_i[1:0];` declara un wire de **1 bit**, así que el
   caso `2'b10` (pc+4 para jal/jalr) es inalcanzable. Fix:
   ```verilog
   wire [1:0] mem_to_reg = control_i[1:0];
   ```
   (Los loads zafan porque `2'b01` truncado a `1'b1` matchea igual.)

4. **Robustez con el debug (recomendado).** Con el fix 2b, durante un freeze del
   debug (`cpu_enable=0`) una op de memoria congelada en MEM mantiene `ena=1` y
   puede pisar `douta` mientras el regfile sigue reescribiendo en cada `negedge`.
   Gatear el enable de la BRAM con un puerto nuevo en `memory.v` conectado a
   `cpu_enable`:
   ```verilog
   .ena((mem_write | mem_read) & enable_i),
   ```

### Notas para la fase de control hazards (dejar anotado)

- El fetch tiene un **sesgo de +4** entre `pc_id` y su instrucción: la BRAM de
  instrucciones agrega una etapa de registro que el diseño no cuenta (además la
  primera instrucción entra dos veces al arrancar). No afecta los riesgos de
  datos, pero rompe targets de branch y el link de `jal`.
- Un branch tomado en MEM durante un ciclo de stall se perdería: `pc_src` queda
  gateado por `cpu_enable & pc_write`. Cuando se implemente el flush, `pc_src`
  debe tener **prioridad** sobre el stall.

---

## 6. Comandos Tcl para Vivado (consola Tcl de abajo, NO editar el .xpr a mano)

Agregar los archivos al proyecto — versión **idempotente** (se puede correr dos
veces sin que falle con "already exists"):

```tcl
set proj_dir [get_property DIRECTORY [current_project]]

foreach f [list \
    [file join $proj_dir risc-v-processor.srcs sources_1 new forwarding_unit.v] \
    [file join $proj_dir risc-v-processor.srcs sources_1 new hazard_detection_unit.v]] {
    if {[llength [get_files -quiet -of_objects [get_filesets sources_1] $f]] == 0} {
        add_files -fileset sources_1 -norecurse $f
    }
}
foreach f [list \
    [file join $proj_dir risc-v-processor.srcs sim_1 new tb_forwarding_unit.v] \
    [file join $proj_dir risc-v-processor.srcs sim_1 new tb_hazard_detection_unit.v]] {
    if {[llength [get_files -quiet -of_objects [get_filesets sim_1] $f]] == 0} {
        add_files -fileset sim_1 -norecurse $f
    }
}
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
```

Sin `-copy_to`: los archivos ya viven dentro de `risc-v-processor.srcs`, Vivado
los referencia en el lugar y reescribe el `.xpr` él solo.

Correr los testbenches (el top de simulación hoy es `tb_top`, hay que cambiarlo):

```tcl
set_property top tb_forwarding_unit [get_filesets sim_1]
launch_simulation
run all
# esperado: "PASS: tb_forwarding_unit - 4194304 vectors, 0 errors"

set_property top tb_hazard_detection_unit [get_filesets sim_1]
launch_simulation
run all
# esperado: "PASS: tb_hazard_detection_unit - 65536 vectors, 0 errors"
```

> Tip: el TB de forwarding mueve 4.2M vectores — correrlo con la ventana de
> waveforms cerrada (o en batch) para que el `.wdb` no crezca a cientos de MB.

Regenerar el IP de memoria de datos (fix 2a de la sección 5):

```tcl
set_property CONFIG.Register_PortA_Output_of_Memory_Primitives false [get_ips data_memory]
reset_target all [get_ips data_memory]
generate_target all [get_ips data_memory]
```
