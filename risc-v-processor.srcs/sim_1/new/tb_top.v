`timescale 1ns / 1ps

module tb_top;

    // BAUD_RATE=781250 and FREQ=50MHz:
    //   CLOCK_TICK = 50M / (781250 * 16) = 4
    //   Actual tick period = (4-1) * 20ns = 60ns
    //   Actual BIT_PERIOD = 16 ticks * 60ns = 960ns
    // =========================================================================
    parameter BAUD_RATE  = 781250;
    parameter FREQ       = 50000000;
    parameter CLOCK_TICK = FREQ / (BAUD_RATE * 16);           // = 4
    parameter BIT_PERIOD = 16 * (CLOCK_TICK - 1) * 20;       // = 960 ns

    reg  clk;
    reg  reset;
    reg  rx_pin;
    wire tx_pin;

    top #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) uut (
        .clk    (clk),
        .reset  (reset),
        .rx_pin (rx_pin),
        .tx_pin (tx_pin)
    );

    always #10 clk = ~clk; // 50 MHz clock -> 20ns period

    task uart_send_byte(input [7:0] data);
        integer i;
        begin
            rx_pin = 0; // Start bit
            #BIT_PERIOD;
            for (i = 0; i < 8; i = i + 1) begin
                rx_pin = data[i];
                #BIT_PERIOD;
            end
            rx_pin = 1; // Stop bit
            #BIT_PERIOD;
        end
    endtask

    task uart_send_40b(input [39:0] data);
        begin
            uart_send_byte(data[39:32]);
            uart_send_byte(data[31:24]);
            uart_send_byte(data[23:16]);
            uart_send_byte(data[15:8]);
            uart_send_byte(data[7:0]);
            #(BIT_PERIOD * 3); // Gap between frames
        end
    endtask

    integer k;

    initial begin
        $display("=== Top-Level Pipeline + UART Debug Testbench ===");
        $display("    CLOCK_TICK=%0d, BIT_PERIOD=%0d ns", CLOCK_TICK, BIT_PERIOD);
        
        clk = 0;
        reset = 1;
        rx_pin = 1;
        
        #200;
        reset = 0;
        #200;

        $display("--- Sending RESET command (0x03) to Debug Unit ---");
        uart_send_40b({8'h03, 32'h00000000});

        $display("--- Loading instructions via UART (0x10) ---");
        // addi x1,x0,42
        uart_send_40b({8'h10, 32'h02A00093});
        // addi x2,x0,100
        uart_send_40b({8'h10, 32'h06400113});
        // lw x3, 8(x0)
        uart_send_40b({8'h10, 32'h0080_2183});
        // sw x0, 0(x0)
        uart_send_40b({8'h10, 32'h00002023});
        // add x4,x1,x2
        uart_send_40b({8'h10, 32'h0020_8233});
        // beq x0,x0,+8
        uart_send_40b({8'h10, 32'h0000_0463});

        // Load zero instructions (0x00000000) so HALT triggers
        // (halt requires instruction_id == 0 && pc_if > 0x10)
        for (k = 0; k < 10; k = k + 1) begin
            uart_send_40b({8'h10, 32'h00000000});
        end

        $display("--- Sending RUN command (0x02) ---");
        uart_send_40b({8'h02, 32'h00000000});

        $display("--- Waiting for processor to execute and HALT... ---");
        #50000;

        $display(">> [TB DIRECT SNOOP] Register file internal check:");
        $display(">> x1 = %0d", uut.u_id.register.regs[1]);
        $display(">> x2 = %0d", uut.u_id.register.regs[2]);
        $display(">> x4 = %0d", uut.u_id.register.regs[4]);

        $display("--- Querying Register x1 (0x20, expect 42 = 0x2A) ---");
        uart_send_40b({8'h20, 27'h0, 5'd1});
        #(BIT_PERIOD * 10 * 7);

        $display("--- Querying Register x2 (0x20, expect 100 = 0x64) ---");
        uart_send_40b({8'h20, 27'h0, 5'd2});
        #(BIT_PERIOD * 10 * 7);

        $display("--- Querying Register x4 (0x20, expect 142 = 0x8E) ---");
        uart_send_40b({8'h20, 27'h0, 5'd4});
        #(BIT_PERIOD * 10 * 7);

        $display("--- Querying PC (0x40) ---");
        uart_send_40b({8'h40, 32'h00000000});
        #(BIT_PERIOD * 10 * 7);

        $display("--- Querying Latch ID/EX PC (0x50, ID 4) ---");
        uart_send_40b({8'h50, 32'h00000004});
        #(BIT_PERIOD * 10 * 7);

        $display("--- End of UART test ---");
        $finish;
    end

    always @(posedge clk) begin
        if (uut.u_debug_unit.tx_start_o) begin
            $display("[TB SNOOP] FPGA TX response: CMD=0x%h | DATA=0x%h (%0d)", 
                uut.u_debug_unit.tx_data_o[39:32], 
                uut.u_debug_unit.tx_data_o[31:0],
                uut.u_debug_unit.tx_data_o[31:0]);
        end
    end

    // Debug Unit status monitor
    always @(posedge clk) begin
        if (uut.u_uart_if.rx_done_40b_o) begin
            $display("[TB MONITOR] UART RX assembled: CMD=0x%h | DATA=0x%h | DU_state=%0d",
                uut.u_uart_if.rx_data_40b_o[39:32],
                uut.u_uart_if.rx_data_40b_o[31:0],
                uut.u_debug_unit.state);
        end
    end

endmodule
