`timescale 1ns / 1ps

module tb_register;

    reg         clk;
    reg         reset;
    reg         reg_write;
    reg  [4:0]  rs1;
    reg  [4:0]  rs2;
    reg  [4:0]  rd;
    reg  [31:0] write_data;
    reg  [4:0]  debug_reg_addr;
    wire [31:0] read_data1;
    wire [31:0] read_data2;
    wire [31:0] debug_reg_data;

    register uut (
        .clk(clk),
        .reset(reset),
        .reg_write(reg_write),
        .rs1(rs1),
        .rs2(rs2),
        .rd(rd),
        .write_data(write_data),
        .debug_reg_addr_i(debug_reg_addr),
        .debug_reg_data_o(debug_reg_data),
        .read_data1(read_data1),
        .read_data2(read_data2)
    );

    always #5 clk = ~clk;

    integer i;

    initial begin
        clk = 0;
        reset = 1;
        reg_write = 0;
        rs1 = 0; rs2 = 0; rd = 0; write_data = 0;
        debug_reg_addr = 0;

        $display("Time | rst | we | rs1 | rs2 | rd  | wdata  | rdata1 | rdata2");
        $display("-----------------------------------------------------------");

        #12 reset = 0;

        rd = 5'd1; write_data = 32'hAAAA_5555; reg_write = 1; rs1 = 5'd1; rs2 = 5'd1;
        @(posedge clk); #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | %2d  | %h | %h | %h",
            $time, reset, reg_write, rs1, rs2, rd, write_data, read_data1, read_data2);

        rd = 5'd2; write_data = 32'h1234_5678; reg_write = 1; rs1 = 5'd2; rs2 = 5'd1;
        @(posedge clk); #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | %2d  | %h | %h | %h",
            $time, reset, reg_write, rs1, rs2, rd, write_data, read_data1, read_data2);

        rd = 5'd31; write_data = 32'hDEAD_BEEF; reg_write = 1; rs1 = 5'd31; rs2 = 5'd2;
        @(posedge clk); #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | %2d  | %h | %h | %h",
            $time, reset, reg_write, rs1, rs2, rd, write_data, read_data1, read_data2);

        reg_write = 0; rs1 = 5'd1; rs2 = 5'd31;
        #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | --  | ------  | %h | %h",
            $time, reset, reg_write, rs1, rs2, read_data1, read_data2);

        rd = 5'd0; write_data = 32'hFFFF_FFFF; reg_write = 1; rs1 = 5'd0; rs2 = 5'd0;
        @(posedge clk); #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | %2d  | %h | %h | %h  (x0 write ignored)",
            $time, reset, reg_write, rs1, rs2, rd, write_data, read_data1, read_data2);

        reg_write = 0; rs1 = 5'd0; rs2 = 5'd0;
        #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | --  | ------  | %h | %h  (x0 read = 0)",
            $time, reset, reg_write, rs1, rs2, read_data1, read_data2);

        $display("");
        $display("--- All registers (via read ports, after writes) ---");
        for (i = 0; i < 32; i = i + 1) begin
            rd = i; reg_write = 0; rs1 = i; #1;
            $display("x%2d = %h", i, read_data1);
        end

        $display("");
        $display("--- All registers (via debug port, after writes) ---");
        for (i = 0; i < 32; i = i + 1) begin
            debug_reg_addr = i[4:0]; #1;
            $display("x%2d (debug) = %h", i, debug_reg_data);
        end

        reset = 1; #12;
        $display("%4t | %b   | --  | --  | --  | --  | ------  | --   | --   (reset)", $time, reset);
        reg_write = 0; rs1 = 5'd1; rs2 = 5'd2; #1;
        $display("%4t | %b   | %b  | %2d  | %2d  | --  | ------  | %h | %h  (after reset)",
            $time, reset, reg_write, rs1, rs2, read_data1, read_data2);

        $finish;
    end

endmodule
