`timescale 1ns / 1ps

module uart_tx
    #(
    parameter DATA_BIT = 8,
    parameter STOP_BIT_TICK = 16
    )
    (
    input wire          clk,
    input wire          reset,
    input wire          s_tick,
    input wire          tx_start,
    input wire [7:0]    i_data,
    output wire         tx_done_tick,
    output wire         tx
);
    
    localparam [1:0]
        idle    = 2'b00,
        start   = 2'b01,
        data    = 2'b10,
        stop    = 2'b11;
    
    reg [1:0] state_current, state_next; 
    reg [3:0] s_current, s_next;
    reg [2:0] n_current, n_next;
    reg [7:0] b_current, b_next;
    reg tx_current, tx_next;
    reg tx_done_reg;
    
    // FSMD state & data registers
    always @(posedge clk) begin
        if (reset) begin
            state_current <= idle;
            s_current <= 0;
            n_current <= 0;
            b_current <= 0;
            tx_current <= 1'b1;
        end
        else begin
            state_current <= state_next;
            s_current <= s_next;
            n_current <= n_next;
            b_current <= b_next;
            tx_current <= tx_next;
        end
    end
    
    // FSMD next-stage logic
    always @(*) begin
        state_next = state_current;
        tx_done_reg = 1'b0;
        s_next = s_current;
        n_next = n_current;
        b_next = b_current;
        tx_next = tx_current;
        case (state_current)
            idle: begin
                tx_next = 1'b1;
                if (tx_start) begin
                    state_next = start;
                    s_next = 0;
                    b_next = i_data;
                end
            end
            start: begin
                tx_next = 1'b0;
                if (s_tick) begin
                    if (s_current == 15) begin
                        state_next = data;
                        s_next = 0;
                        n_next = 0;
                    end
                    else
                        s_next = s_current + 1;
                end
            end
            data: begin
                tx_next = b_current[0];
                if (s_tick) begin
                    if (s_current == 15) begin
                        s_next = 0;
                        b_next = b_current >> 1;                      
                        if (n_current == (DATA_BIT-1))
                            state_next = stop;
                        else
                            n_next = n_current + 1;
                    end
                    else
                        s_next = s_current + 1;
                end
            end
            stop: begin
                tx_next = 1'b1;
                if (s_tick) begin
                    if (s_current == (STOP_BIT_TICK - 1)) begin
                        state_next = idle;
                        tx_done_reg = 1'b1;
                    end
                    else
                        s_next = s_current + 1;
                end
            end
        endcase
    end

    assign tx_done_tick = tx_done_reg;
    assign tx = tx_current; 

endmodule