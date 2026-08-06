`timescale 1ns / 1ps

module tb_uart_interface;

    // Parámetros
    localparam BAUD_RATE = 9600;
    localparam FREQ = 10000000;      // Frecuencia de 10 MHz
    localparam DATA_BIT = 8;
    localparam STOP_BIT_TICK = 16;

    // Señales de reloj y reset
    reg clk;
    reg reset;
    
    // Pines UART físicos simulados
    reg  rx_pin;
    wire tx_pin;
    
    // Interfaz ALU/Memoria (Lado RX)
    wire [39:0] rx_data_40b;
    wire        rx_done_40b;
    
    // Interfaz ALU/Memoria (Lado TX)
    reg  [39:0] tx_data_40b;
    reg         tx_start_40b;
    wire        tx_busy;

    // Reloj (10MHz -> Periodo de 100ns -> Toggle cada 50ns)
    always #50 clk = ~clk;

    // ==========================================
    // 1. Instancia del DUT (Device Under Test)
    // ==========================================
    uart_interface #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ),
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) uut (
        .clk(clk),
        .reset(reset),
        .rx_pin_i(rx_pin),
        .tx_pin_o(tx_pin),
        .rx_data_40b_o(rx_data_40b),
        .rx_done_40b_o(rx_done_40b),
        .tx_data_40b_i(tx_data_40b),
        .tx_start_40b_i(tx_start_40b),
        .tx_busy_o(tx_busy)
    );

    // ==========================================
    // 2. Herramientas del Testbench (Monitor y Reloj Baudios)
    // ==========================================
    wire tb_s_tick;
    wire mon_rx_done;
    wire [7:0] mon_rx_byte;

    // Generador de baudios exclusivo para que el TB sepa cuándo inyectar bits
    baud_rate_generator #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) tb_baud_gen (
        .clk(clk),
        .tick_o(tb_s_tick)
    );

    // Receptor "Monitor" para verificar lo que el UUT transmite por tx_pin
    uart_rx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) tb_monitor_rx (
        .clk(clk),
        .reset(reset),
        .rx(tx_pin),
        .s_tick(tb_s_tick),
        .rx_done_tick(mon_rx_done),
        .o_data(mon_rx_byte)
    );

    // ==========================================
    // 3. Tareas de Emulación
    // ==========================================
    
// Tarea base: enviar 1 byte al uut (bit-banging por rx_pin)
    task send_byte_to_dut(input [7:0] byte);
        integer i, j;
        begin
            // Start bit (bajo)
            for (j = 0; j < 16; j = j + 1) begin
                rx_pin = 0;
                @(posedge tb_s_tick);
            end
            
            // Data bits (LSB primero)
            for (i = 0; i < DATA_BIT; i = i + 1) begin
                for (j = 0; j < 16; j = j + 1) begin
                    rx_pin = byte[i];
                    @(posedge tb_s_tick);
                end
            end   
            
            // Stop bit (alto)
            for (j = 0; j < 16; j = j + 1) begin
                rx_pin = 1;
                @(posedge tb_s_tick);
            end
            
            // ====== SOLUCIÓN 1: TIEMPO DE GUARDA ======
            // Añadimos un pequeño reposo de 4 ticks entre bytes.
            // Esto asegura que la máquina de estados del RX tenga ciclos
            // suficientes para transicionar de 'stop' a 'idle' sin errores.
            for (j = 0; j < 4; j = j + 1) begin
                rx_pin = 1;
                @(posedge tb_s_tick);
            end
        end
    endtask

    // Tarea de alto nivel: Enviar 40 bits simulando al PC (MSB primero)
    task send_40b_to_dut(input [39:0] data);
        begin
            $display("  [RX Test] Inyectando 5 bytes al RX: 0x%010h", data);
            
            // ====== SOLUCIÓN 2: FORK-JOIN ======
            // Ejecutamos hilos en paralelo. Un hilo inyecta los datos y 
            // el otro vigila el 'rx_done_40b' desde el instante cero.
            fork
                begin : inyectar_datos
                    send_byte_to_dut(data[39:32]);
                    send_byte_to_dut(data[31:24]);
                    send_byte_to_dut(data[23:16]);
                    send_byte_to_dut(data[15:8]);
                    send_byte_to_dut(data[7:0]);
                end
                begin : vigilar_done
                    @(posedge rx_done_40b);
                end
            join
            
            // Cuando ambos hilos terminan, verificamos el resultado
            $display("  [RX Test] DUT agrupo correctamente: 0x%010h", rx_data_40b);
            if (rx_data_40b === data)
                $display("  [RX Test] RESULTADO: EXITO");
            else
                $display("  [RX Test] RESULTADO: FALLA");
        end
    endtask

    // Tarea de alto nivel: Disparar transmisión y recolectar usando el monitor
    task check_tx_40b(input [39:0] expected_data);
        reg [39:0] captured_data;
        integer k;
        begin
            $display("  [TX Test] Iniciando transmision del DUT: 0x%010h", expected_data);
            tx_data_40b = expected_data;
            
            // Pulso de inicio
            tx_start_40b = 1;
            @(posedge clk);
            tx_start_40b = 0;

            // Recolectar los 5 bytes desde el monitor RX
            captured_data = 40'h0;
            for (k = 0; k < 5; k = k + 1) begin
                @(posedge mon_rx_done);
                // Ir desplazando el registro a medida que llegan (MSB primero)
                captured_data = {captured_data[31:0], mon_rx_byte};
            end
            
            // Esperar a que el DUT baje su señal de busy
            wait(tx_busy == 0);
            
            $display("  [TX Test] Monitor recolecto: 0x%010h", captured_data);
            if (expected_data === captured_data)
                $display("  [TX Test] RESULTADO: EXITO");
            else
                $display("  [TX Test] RESULTADO: FALLA");
        end
    endtask

    // ==========================================
    // 4. Secuencia Principal de Simulación
    // ==========================================
    initial begin
        $display("=== Iniciando Testbench UART 5 Bytes ===");
        
        // Condiciones iniciales
        clk = 0;
        reset = 1;
        rx_pin = 1; // Reposo UART
        tx_start_40b = 0;
        tx_data_40b = 0;
        
        #150 reset = 0;
        #1000;

        // --- PRUEBA RX ---
        // Se probará enviando una instrucción RISC-V simulada (por ejemplo)
        send_40b_to_dut(40'h01_A5_B4_C3_D2);
        #5000;
        
        send_40b_to_dut(40'hFF_EE_DD_CC_BB);
        #5000;

        // --- PRUEBA TX ---
        // Se probará enviando resultados simulados de la ALU hacia el exterior
        check_tx_40b(40'h12_34_56_78_9A);
        #5000;
        
        check_tx_40b(40'hAA_55_AA_55_00);
        #5000;

        $display("=== Simulacion Completada ===");
        $finish;
    end

endmodule