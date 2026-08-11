`timescale 1ns / 1ps

module tb_uart_interface;

    // Parameters
    localparam BAUD_RATE = 9600;
    localparam FREQ = 10000000;      // 10 MHz frequency
    localparam DATA_BIT = 8;
    localparam STOP_BIT_TICK = 16;

    // Clock and reset signals
    reg clk;
    reg reset;

    // Simulated physical UART pins
    reg  rx_pin;
    wire tx_pin;

    // ALU/Memory interface (RX side)
    wire [39:0] rx_data_40b;
    wire        rx_done_40b;

    // ALU/Memory interface (TX side)
    reg  [39:0] tx_data_40b;
    reg         tx_start_40b;
    wire        tx_busy;

    // Clock (10MHz -> 100ns period -> toggle every 50ns)
    always #50 clk = ~clk;

    // ==========================================
    // 1. DUT instance (Device Under Test)
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
    // 2. Testbench tools (monitor and baud clock)
    // ==========================================
    wire tb_s_tick;
    wire mon_rx_done;
    wire [7:0] mon_rx_byte;

    // Dedicated baud generator so the TB knows when to inject bits
    baud_rate_generator #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) tb_baud_gen (
        .clk(clk),
        .tick_o(tb_s_tick)
    );

    // "Monitor" receiver to check what the UUT sends over tx_pin
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
    // 3. Emulation tasks
    // ==========================================

// Base task: send 1 byte to the uut (bit-banging over rx_pin)
    task send_byte_to_dut(input [7:0] byte);
        integer i, j;
        begin
            // Start bit (low)
            for (j = 0; j < 16; j = j + 1) begin
                rx_pin = 0;
                @(posedge tb_s_tick);
            end

            // Data bits (LSB first)
            for (i = 0; i < DATA_BIT; i = i + 1) begin
                for (j = 0; j < 16; j = j + 1) begin
                    rx_pin = byte[i];
                    @(posedge tb_s_tick);
                end
            end

            // Stop bit (high)
            for (j = 0; j < 16; j = j + 1) begin
                rx_pin = 1;
                @(posedge tb_s_tick);
            end

            // ====== FIX 1: GUARD TIME ======
            // We add a small rest of 4 ticks between bytes.
            // This makes sure the RX state machine has enough cycles to move
            // from 'stop' to 'idle' without errors.
            for (j = 0; j < 4; j = j + 1) begin
                rx_pin = 1;
                @(posedge tb_s_tick);
            end
        end
    endtask

    // High level task: send 40 bits emulating the PC (MSB first)
    task send_40b_to_dut(input [39:0] data);
        begin
            $display("  [RX Test] Inyectando 5 bytes al RX: 0x%010h", data);

            // ====== FIX 2: FORK-JOIN ======
            // We run threads in parallel. One thread injects the data and the
            // other watches 'rx_done_40b' from time zero.
            fork
                begin : inject_data
                    send_byte_to_dut(data[39:32]);
                    send_byte_to_dut(data[31:24]);
                    send_byte_to_dut(data[23:16]);
                    send_byte_to_dut(data[15:8]);
                    send_byte_to_dut(data[7:0]);
                end
                begin : watch_done
                    @(posedge rx_done_40b);
                end
            join

            // When both threads are done, we check the result
            $display("  [RX Test] DUT agrupo correctamente: 0x%010h", rx_data_40b);
            if (rx_data_40b === data)
                $display("  [RX Test] RESULTADO: EXITO");
            else
                $display("  [RX Test] RESULTADO: FALLA");
        end
    endtask

    // High level task: trigger the transmission and collect it with the monitor
    task check_tx_40b(input [39:0] expected_data);
        reg [39:0] captured_data;
        integer k;
        begin
            $display("  [TX Test] Iniciando transmision del DUT: 0x%010h", expected_data);
            tx_data_40b = expected_data;

            // Start pulse
            tx_start_40b = 1;
            @(posedge clk);
            tx_start_40b = 0;

            // Collect the 5 bytes from the RX monitor
            captured_data = 40'h0;
            for (k = 0; k < 5; k = k + 1) begin
                @(posedge mon_rx_done);
                // Shift the register as they arrive (MSB first)
                captured_data = {captured_data[31:0], mon_rx_byte};
            end

            // Wait for the DUT to lower its busy signal
            wait(tx_busy == 0);

            $display("  [TX Test] Monitor recolecto: 0x%010h", captured_data);
            if (expected_data === captured_data)
                $display("  [TX Test] RESULTADO: EXITO");
            else
                $display("  [TX Test] RESULTADO: FALLA");
        end
    endtask

    // ==========================================
    // 4. Main simulation sequence
    // ==========================================
    initial begin
        $display("=== Iniciando Testbench UART 5 Bytes ===");

        // Initial conditions
        clk = 0;
        reset = 1;
        rx_pin = 1; // UART idle
        tx_start_40b = 0;
        tx_data_40b = 0;

        #150 reset = 0;
        #1000;

        // --- RX TEST ---
        // Tested by sending a simulated RISC-V instruction (for example)
        send_40b_to_dut(40'h01_A5_B4_C3_D2);
        #5000;

        send_40b_to_dut(40'hFF_EE_DD_CC_BB);
        #5000;

        // --- TX TEST ---
        // Tested by sending simulated ALU results to the outside
        check_tx_40b(40'h12_34_56_78_9A);
        #5000;

        check_tx_40b(40'hAA_55_AA_55_00);
        #5000;

        $display("=== Simulacion Completada ===");
        $finish;
    end

endmodule
