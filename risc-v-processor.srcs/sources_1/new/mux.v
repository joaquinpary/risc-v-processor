`timescale 1ns / 1ps

module mux2 #(parameter N = 32) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         sel,
    output wire [N-1:0] y
);

    assign y = sel ? b : a;

endmodule
