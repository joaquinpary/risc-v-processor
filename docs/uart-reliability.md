# UART: por qué el enlace se muere y no vuelve

Diagnóstico a partir de cuatro capturas de `uart_doctor` (2026-08-11), todas con
la placa recién programada.

## Los síntomas

| Log | Modo | Falla |
|---|---|---|
| `uart_doctor.log` | diagnose | 13 intercambios OK; pedimos `x1` (payload `0x01`) y contesta código `0x02`; el siguiente pedido muere para siempre |
| `uart_doctor(1).log` | trace-dashboard | RESET + 17 LOAD + RUN OK; primer `REQ_REG x1` contesta `0x02`; todo lo demás timeout |
| `uart_doctor(3).log` | trace-tui | 17 intercambios **perfectos** (x1=42, x9=8, x10=50…); el nº 18 pide `x16` (payload `0x10`) y contesta código `0x41` con el valor de `x1`; muerte permanente |

El patrón es siempre el mismo: **funciona bien, una respuesta sale corrupta, y a
partir de ahí silencio absoluto que ni el RESET revierte.**

La respuesta corrupta es la pista clave. En el log (3):

```
TX  20 00 00 00 10   | REQ_REG x16
RX  41 00 00 00 2A   | código 0x41, dato 42
```

El firmware hace `resp_cmd_aux <= payload[7:0]` y `debug_reg_addr_o = payload[4:0]`.
Con `payload[7:0] = 0x41` sale código `0x41` y lee `regs[0x41 & 0x1F] = regs[1] = 42`.
Las dos cosas cuadran: **la FPGA recibió `0x41` donde mandamos `0x10`**. O sea, un
byte se corrompió en el receptor.

## La cadena de fallas

### 1. `rx` entra sin sincronizador → corrupción aleatoria

`uart_rx.v` usa el pin `rx` **crudo**, asincrónico, directamente en la lógica
combinacional de próximo estado (línea 54, `if (~rx)`) y lo muestrea directo al
registro de datos (línea 76, `b_next[7] = rx;`).

Una señal de otro dominio de reloj sin un sincronizador de dos flops
**eventualmente** hace metaestable al flip-flop que la captura. Es exactamente
este perfil: anda bien decenas de tramas y de golpe un byte sale mal, sin
periodicidad. Es la causa raíz.

Agravantes que reducen el margen:

- `s_tick` es libre y **nunca se realinea** con el bit de arranque, así que el
  punto de muestreo tiene hasta ±1 tick de jitter (±6,25% de un bit).
- `baud_rate_gen.v` usa asignaciones **bloqueantes** y su período real termina
  siendo `CLOCK_TICK-1` = 650 ciclos en vez de 651 → 9615 baudios contra 9600
  (+0,16%). Poco, pero se suma.

### 2. Sin reencuadre → la corrupción se vuelve permanente

`uart_interface.v` (líneas 89-99) agrupa los bytes de a 5 con `rx_count` y **no
tiene ninguna detección de silencio entre tramas**. Si por la corrupción se
pierde o se inventa un byte, el contador queda corrido y no hay forma de
recuperarlo salvo por `reset`.

### 3. El desfasaje dispara un RUN fantasma → cuelgue definitivo

Acá está el remate. Con el stream desfasado, nuestras tramas `20 00 00 00 0N`
se reagrupan. Para un corrimiento de 4 bytes queda `0N 20 00 00 00`, o sea que
**el número de registro pasa a ser el comando**:

| Registro pedido | Comando que entiende la FPGA |
|---|---|
| `x1` | `0x01` = **STEP** |
| `x2` | `0x02` = **RUN** |
| `x3` | `0x03` = RESET |
| resto | `0x00` → `default` → silencio |

Si le entra un `RUN` fantasma, el `debug_unit` pasa a `RUNNING`, donde **ignora
la UART por completo** y solo sale si se activa `cpu_halted`. Con basura
ejecutándose (y con los saltos todavía rotos: inmediato desplazado dos veces y
PC corrido +4), `cpu_halted = (instruction_id == 0 && pc_if > 0x10)` puede no
cumplirse nunca.

**Eso explica lo que parecía inexplicable**: por qué reencuadrar no lo revive.
Para cuando intentamos realinear, la FSM ya no está escuchando. Solo se sale
reprogramando o con el reset físico.

## Los parches

### A. Sincronizador en `rx` (uart_rx.v) — el más importante

Declarar junto a los demás registros:

```verilog
    // Sincronizador de 2 flops: rx viene del pin, es asincronico al reloj.
    // Sin esto el flip-flop que lo captura se vuelve metaestable cada tanto
    // y corrompe un byte al azar.
    reg rx_meta, rx_sync;

    always @(posedge clk) begin
        if (reset) begin
            rx_meta <= 1'b1;    // linea en reposo = 1
            rx_sync <= 1'b1;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
        end
    end
```

Y usar `rx_sync` en lugar de `rx` en los dos puntos donde se lee:

```verilog
            idle: begin
                if (~rx_sync) begin        // antes: ~rx
```

```verilog
                        b_next = b_current >> 1;
                        b_next[7] = rx_sync;   // antes: rx
```

### B. Reencuadre por silencio (uart_interface.v) — contiene el daño

El umbral tiene que ser **mayor a un tiempo de byte** (160 ticks): dentro de una
misma trama los bytes llegan pegados y `rx_done_tick` aparece recién cada 160
ticks, así que un umbral más chico dispararía en medio de una trama válida. Se
usan 4 tiempos de byte (640 ticks ≈ 4,2 ms a 9600): reencuadra rápido y deja 4x
de margen, muy por debajo de los ≥10 ms que hay entre tramas reales.

```verilog
    localparam integer IDLE_TICKS = 16 * 10 * 4;   // 4 bytes = 640 ticks

    reg [9:0] idle_count;

    always @(posedge clk) begin
        if (reset || rx_done_tick)
            idle_count <= 0;
        else if (s_tick && idle_count != IDLE_TICKS)
            idle_count <= idle_count + 1'b1;
    end

    wire frame_timeout = (idle_count == IDLE_TICKS);
```

Y en el bloque de recepción, darle prioridad al timeout:

```verilog
    always @(posedge clk) begin
        if (reset) begin
            rx_count        <= 0;
            rx_buffer       <= 0;
            rx_data_40b_reg <= 0;
            rx_done_40b_reg <= 0;
        end else begin
            rx_done_40b_reg <= 0;

            if (frame_timeout && rx_count != 0) begin
                rx_count <= 0;              // descarta la trama parcial
            end else if (rx_done_tick) begin
                rx_buffer <= {rx_buffer[31:0], rx_byte};
                if (rx_count == 4) begin
                    rx_data_40b_reg <= {rx_buffer[31:0], rx_byte};
                    rx_done_40b_reg <= 1;
                    rx_count        <= 0;
                end else begin
                    rx_count <= rx_count + 1;
                end
            end
        end
    end
```

Con esto, cualquier desincronización se cura sola en cuanto la PC hace una pausa
entre tramas (que siempre la hay).

### C. `baud_rate_gen.v` — limpieza

```verilog
module baud_rate_gen #(
    parameter BAUD_RATE = 9600,
    parameter FREQ      = 50E6
)(
    input  wire clk,
    output wire tick_o
);
    localparam integer CLOCK_TICK = FREQ / (BAUD_RATE * 16);

    reg [$clog2(CLOCK_TICK) - 1 : 0] count = 0;
    reg tick = 1'b0;

    // No bloqueantes: con bloqueantes el periodo real era CLOCK_TICK-1
    always @(posedge clk) begin
        if (count == CLOCK_TICK - 1) begin
            count <= 0;
            tick  <= 1'b1;
        end else begin
            count <= count + 1'b1;
            tick  <= 1'b0;
        end
    end

    assign tick_o = tick;
endmodule
```

Confirmado que `FREQ = 100000000` es correcto: el `.xdc` declara
`create_clock -period 10.00` sobre `clk` (Arty A7, 100 MHz).

### D. Opcional: poder salir de RUNNING por UART (debug_unit.v)

Hoy un `RUN` es irreversible desde la PC. Un comando de pausa evita que un RUN
fantasma —o un programa que no termina— obligue a reprogramar:

```verilog
                RUNNING: begin
                    cpu_enable_reg <= 1'b1;
                    if (cpu_halted_i)
                        state <= IDLE;
                    else if (rx_done_i && cmd == 8'h04)   // PAUSE
                        state <= IDLE;
                end
```

(Y agregar `PAUSE = 0x04` en `tools/riscv_debug/protocol.py`.)

## Orden sugerido

**A** y **B** son los que hay que hacer sí o sí: A ataca la causa, B evita que un
error puntual sea terminal. **C** es higiene. **D** es comodidad de laboratorio,
pero se agradece mucho en la demo.

## Nota sobre la herramienta

La rutina de reencuadre de `uart_doctor` tenía un bug propio: mandaba relleno
*acumulativo* (1, después 2 más, después 3 más…), o sea totales 1, 3, 6, 10, que
módulo 5 son 1, 3, 1, 0 — **nunca probaba +2 ni +4**. Corregido para mandar un
byte por vuelta. Los veredictos de "no se recuperó con ningún relleno" anteriores
a ese arreglo no son concluyentes por sí solos; lo que sí sostiene el
diagnóstico es el RUN fantasma de la sección 3, que hace que ningún reencuadre
pueda funcionar.
