`timescale 1ns / 1ps

module register (
    input wire          clk,
    input wire          reset,
    input wire          reg_write,
    input wire  [4:0]   rs1,
    input wire  [4:0]   rs2,
    input wire  [4:0]   rd,
    input wire  [31:0]  write_data,
    input wire  [4:0]   debug_reg_addr_i,
    output wire [31:0]  debug_reg_data_o,
    output wire [31:0]  read_data1,
    output wire [31:0]  read_data2
);

    reg [31:0] regs [0:31];

    integer i;
    always @(negedge clk) begin
        if (reset) begin
            for (i = 0; i < 32; i = i + 1)
                regs[i] <= 32'b0;
        end else if (reg_write && rd != 5'b00000) begin
            regs[rd] <= write_data;
        end
    end

    assign read_data1 = (rs1 == 5'b00000) ? 32'b0 : regs[rs1];
    assign read_data2 = (rs2 == 5'b00000) ? 32'b0 : regs[rs2];
    
    assign debug_reg_data_o = (debug_reg_addr_i == 5'b00000) ? 32'b0: regs[debug_reg_addr_i];

endmodule
