`timescale 1ns / 1ps

module tb_uart;
    localparam DATA_BIT = 8;
    localparam BAUD_RATE = 9600;
    localparam FREQ = 10E6;          // 10 MHz frequency
    localparam STOP_BIT_TICK = 16;

    reg clk;
    reg reset;
    
    // Signals for the DUT RX (Input emulation)
    reg rx_serial;
    wire rx_done_tick;
    wire [7:0] rx_data_out;
    
    // Signals for the DUT TX
    reg tx_start;
    reg [7:0] tx_data_in;
    wire tx_serial;
    wire tx_done_tick;
    
    wire s_tick;

    // Clock generation (Period of 100ns -> 10MHz frequency)
    always #50 clk = ~clk;  

    // Baud rate generator instance
    baud_rate_gen #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) baud_gen_inst (
        .clk(clk),
        .tick_o(s_tick)
    );

    // UART Receiver instance (Module under test)
    uart_rx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) rx_inst (
        .clk(clk),
        .reset(reset),
        .rx(rx_serial),
        .s_tick(s_tick),
        .rx_done_tick(rx_done_tick),
        .o_data(rx_data_out)
    );

    // UART Transmitter instance (Module under test)
    uart_tx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) tx_inst (
        .clk(clk),
        .reset(reset),
        .s_tick(s_tick),
        .tx_start(tx_start),
        .i_data(tx_data_in),
        .tx_done_tick(tx_done_tick),
        .tx(tx_serial)
    );

    // Instance of a "Monitor" Receiver to verify the TX output
    wire monitor_rx_done;
    wire [7:0] monitor_rx_data;
    uart_rx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) rx_monitor_inst (
        .clk(clk),
        .reset(reset),
        .rx(tx_serial), // Connected directly to the TX output
        .s_tick(s_tick),
        .rx_done_tick(monitor_rx_done),
        .o_data(monitor_rx_data)
    );

    // Task to emulate sending a byte to the RX (Bit-banging synchronized with s_tick)
    task uart_send_byte(input [7:0] byte);
        integer i, j;
        begin
            // Send start bit (low)
            for (j = 0; j < 16; j = j + 1) begin
                rx_serial = 0;
                @(posedge s_tick);
            end
            
            // Send 8 data bits (LSB first)
            for (i = 0; i < DATA_BIT; i = i + 1) begin
                for (j = 0; j < 16; j = j + 1) begin
                    rx_serial = byte[i];
                    @(posedge s_tick);
                end
            end   
            
            // Send stop bit (high)
            for (j = 0; j < 16; j = j + 1) begin
                rx_serial = 1;
                @(posedge s_tick);
            end
        end
    endtask

    // Task to trigger the TX module and wait for it to finish
    task uart_trigger_tx(input [7:0] byte);
        begin
            tx_data_in = byte;
            tx_start = 1;
            @(posedge clk);
            tx_start = 0;
            
            // Wait for the TRANSMITTER to finish the frame completely
            // (We know that when the TX finishes, the RX already finished reading long ago)
            @(posedge tx_done_tick);
            
            // Small delay to ensure the monitor output register is stable
            #10;
            $display("  [TX Test] TX envió: 0x%h | Monitor recibió: 0x%h", byte, monitor_rx_data);
        end
    endtask

    // Main simulation block
    initial begin
        // 1. Signal initialization
        clk = 0;
        reset = 1;
        rx_serial = 1;   // The UART line at idle is always HIGH (1)
        tx_start = 0;
        tx_data_in = 0;
        
        #150;
        reset = 0;
        #200;

        // 2. Test the RX module by emulating an external send
        $display("=== Starting UART RX module test ===");
        
        uart_send_byte(8'hA5); // Send 1010_0101
        $display("  [RX Test] RX recibió: 0x%h", rx_data_out);
        #1000;
        
        uart_send_byte(8'h3C); // Send 0011_1100
        $display("  [RX Test] RX recibió: 0x%h", rx_data_out);
        #1000;

        // 3. Test the TX module by verifying it through the RX monitor
        $display("=== Starting UART TX module test ===");
        
        uart_trigger_tx(8'h55); // Send 0101_0101
        #1000;
        
        uart_trigger_tx(8'hFF); // Send 1111_1111
        #1000;

        $display("=== Simulation finished successfully ===");
        $finish;
    end
endmodule