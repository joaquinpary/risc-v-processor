`timescale 1ns / 1ps

module baud_rate_gen
    #(
    parameter BAUD_RATE = 9600,
    parameter FREQ = 50E6
    )
    (
    input wire      clk,
    output wire     tick_o
    );
    
    localparam integer CLOCK_TICK = FREQ / (BAUD_RATE * 16);
    
    integer count = 0;
    reg tick;
    
    always @(posedge clk) begin
        if (count == (CLOCK_TICK-1)) begin
            count = 0;
            tick = 1;
        end
        else
            tick = 0;
        count = count + 1;
    end       
    
    assign tick_o = tick; 
    
endmodule