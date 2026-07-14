`timescale 1ns / 1ps

module tb_alu;

    reg  [31:0] a;
    reg  [31:0] b;
    reg  [3:0]  alu_control;
    wire [31:0] result;
    wire        zero;

    alu uut (
        .a(a),
        .b(b),
        .alu_control(alu_control),
        .result(result),
        .zero(zero)
    );

    initial begin
        $display("Time | a       | b       | ctrl | result  | zero");
        $display("-----------------------------------------------");

        a = 32'h0000_000F; b = 32'h0000_00F0; alu_control = 4'b0000;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'h0000_000F; b = 32'h0000_00F0; alu_control = 4'b0001;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'h0000_0005; b = 32'h0000_0003; alu_control = 4'b0010;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'h0000_0005; b = 32'h0000_0003; alu_control = 4'b0110;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'h0000_0003; b = 32'h0000_0003; alu_control = 4'b0110;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'hFFFF_FFFF; b = 32'h0000_0001; alu_control = 4'b0010;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        a = 32'h0000_0000; b = 32'h0000_0000; alu_control = 4'b0010;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b", $time, a, b, alu_control, result, zero);

        alu_control = 4'b1111;
        #10;
        $display("%4t | %h | %h | %b    | %h | %b (default)", $time, a, b, alu_control, result, zero);

        $finish;
    end

endmodule
