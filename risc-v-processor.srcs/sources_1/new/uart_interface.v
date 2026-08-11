`timescale 1ns / 1ps

module uart_interface #(
    parameter BAUD_RATE     = 9600,
    parameter FREQ          = 10000000,
    parameter DATA_BIT      = 8,
    parameter STOP_BIT_TICK = 16
)(
    input  wire        clk,
    input  wire        reset,

    input  wire        rx_pin_i,
    output wire        tx_pin_o,

    output wire [39:0] rx_data_40b_o,
    output wire        rx_done_40b_o,

    input  wire [39:0] tx_data_40b_i,
    input  wire        tx_start_40b_i,
    output wire        tx_busy_o
);

    // Internal signals
    wire            s_tick;
    wire            rx_done_tick;
    wire    [7:0]   rx_byte;
    wire            tx_done_tick;
    reg             tx_start_1b;
    reg     [7:0]   tx_byte;

    // Internal registers for output signals
    reg     [39:0]  rx_data_40b_reg;
    reg             rx_done_40b_reg;
    reg             tx_busy_reg;

    assign rx_data_40b_o = rx_data_40b_reg;
    assign rx_done_40b_o = rx_done_40b_reg;
    assign tx_busy_o     = tx_busy_reg;

    // Baud rate generator
    baud_rate_gen #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) baud_gen_inst (
        .clk(clk),
        .tick_o(s_tick)
    );

    // UART Receiver
    uart_rx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) rx_inst (
        .clk(clk),
        .reset(reset),
        .rx(rx_pin_i),
        .s_tick(s_tick),
        .rx_done_tick(rx_done_tick),
        .o_data(rx_byte)
    );

    // UART Transmitter
    uart_tx #(
        .DATA_BIT(DATA_BIT),
        .STOP_BIT_TICK(STOP_BIT_TICK)
    ) tx_inst (
        .clk(clk),
        .reset(reset),
        .s_tick(s_tick),
        .tx_start(tx_start_1b),
        .i_data(tx_byte),
        .tx_done_tick(tx_done_tick),
        .tx(tx_pin_o)
    );

    // Receive logic (group 5 bytes)
    reg [2:0]  rx_count;
    reg [39:0] rx_buffer;

    // -----------------------------------------------------------------
    // Frame resync on idle line
    //
    // Bytes are grouped in fives by counting, without any start of frame
    // marker. If a byte is ever lost or slipped in, rx_count is left shifted
    // and EVERY following frame is misread forever (worse: a shift of 4 makes
    // a REQ_REG x2 read as the RUN command, which leaves debug_unit deaf until
    // the CPU stops).
    //
    // Fix: if IDLE_TICKS go by without receiving a byte, the partial frame is
    // dropped and the count restarts from zero. Since the PC always pauses
    // between frames, any desync heals by itself.
    //
    // The threshold has to be LARGER than one byte time (160 ticks), because
    // inside the same frame the bytes arrive back to back and rx_done_tick
    // only shows up every 160 ticks. We use 4 byte times: it resyncs in ~4 ms
    // at 9600 baud and leaves 4x of margin against a false positive in the
    // middle of a valid frame.
    // -----------------------------------------------------------------
    localparam integer IDLE_TICKS = 16 * 10 * 4;   // 4 bytes = 640 ticks

    reg [9:0] idle_count;

    always @(posedge clk) begin
        if (reset || rx_done_tick)
            idle_count <= 10'd0;
        else if (s_tick && idle_count != IDLE_TICKS)
            idle_count <= idle_count + 1'b1;
    end

    wire frame_timeout = (idle_count == IDLE_TICKS);

    always @(posedge clk) begin
        if (reset) begin
            rx_count        <= 0;
            rx_buffer       <= 0;
            rx_data_40b_reg <= 0;
            rx_done_40b_reg <= 0;
        end else begin
            rx_done_40b_reg <= 0;

            if (frame_timeout && rx_count != 0) begin
                // Long silence with a half built frame: drop it
                rx_count <= 0;
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

    // Transmit logic (unpack 5 bytes)
    localparam TX_IDLE = 2'd0;
    localparam TX_SEND = 2'd1;
    localparam TX_WAIT = 2'd2;

    reg [2:0]  tx_count;
    reg [39:0] tx_buffer;
    reg [1:0]  tx_state;

    always @(posedge clk) begin
        if (reset) begin
            tx_state    <= TX_IDLE;
            tx_count    <= 0;
            tx_start_1b <= 0;
            tx_busy_reg <= 0;
            tx_byte     <= 0;
        end else begin
            tx_start_1b <= 0;

            case (tx_state)
                TX_IDLE: begin
                    if (tx_start_40b_i) begin
                        tx_buffer   <= tx_data_40b_i;
                        tx_count    <= 0;
                        tx_busy_reg <= 1;
                        tx_state    <= TX_SEND;
                    end
                end

                TX_SEND: begin
                    tx_byte     <= tx_buffer[39:32];
                    tx_start_1b <= 1;
                    tx_state    <= TX_WAIT;
                end

                TX_WAIT: begin
                    if (tx_done_tick) begin
                        if (tx_count == 4) begin
                            tx_busy_reg <= 0;
                            tx_state    <= TX_IDLE;
                        end else begin
                            tx_buffer <= {tx_buffer[31:0], 8'h00};
                            tx_count  <= tx_count + 1;
                            tx_state  <= TX_SEND;
                        end
                    end
                end
            endcase
        end
    end

endmodule