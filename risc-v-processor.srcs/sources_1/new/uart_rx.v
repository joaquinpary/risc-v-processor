`timescale 1ns / 1ps

module uart_rx
    #(
    parameter DATA_BIT = 8,
    parameter STOP_BIT_TICK = 16
    )
    (
    input wire          clk,
    input wire          reset,
    input wire          rx,
    input wire          s_tick,
    output wire         rx_done_tick,
    output wire [7:0]   o_data
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
    reg rx_done_reg;

    // Sincronizador de 2 flops para rx.
    // rx viene directo del pin y es asincronico al reloj: muestrearlo sin
    // sincronizar vuelve metaestable al flip-flop que lo captura cada tanto,
    // corrompiendo un byte al azar. Un byte corrupto desalinea el protocolo
    // de 5 bytes de forma permanente, asi que esto no es opcional.
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

    // FSMD state & data registers
    always @(posedge clk) begin
        if (reset) begin
            state_current <= idle;
            s_current <= 0;
            n_current <= 0;
            b_current <= 0;
        end
        else begin
            state_current <= state_next;
            s_current <= s_next;
            n_current <= n_next;
            b_current <= b_next;
        end         
    end
    
    // FSMD next-stage logic
    always @(*) begin
        state_next = state_current;
        rx_done_reg = 1'b0;
        s_next = s_current;
        n_next = n_current;
        b_next = b_current;
        case (state_current)
            idle: begin
                if (~rx_sync) begin
                    state_next = start;
                    s_next = 0;
                end
            end
            start: begin
                if (s_tick) begin
                    if (s_current == 7) begin
                        state_next = data;
                        s_next = 0;
                        n_next = 0;
                    end
                    else
                        s_next = s_current + 1;
                end
            end
            data: begin
                if (s_tick) begin
                    if (s_current == 15) begin
                        s_next = 0;
                        
                        b_next = b_current >> 1;
                        b_next[7] = rx_sync;
                        
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
                if (s_tick) begin
                    if (s_current == (STOP_BIT_TICK - 1)) begin
                        state_next = idle;
                        rx_done_reg = 1'b1;
                    end
                    else
                        s_next = s_current + 1;
                end
            end
        endcase
    end

    assign rx_done_tick = rx_done_reg;
    assign o_data = b_current;

endmodule