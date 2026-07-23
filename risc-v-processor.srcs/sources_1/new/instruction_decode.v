`timescale 1ns / 1ps

module instruction_decode(
    input wire          clk,
    input wire          reset,
    
    input wire  [31:0]  pc_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [31:0]  instruction_i,
    input wire  [4:0]   rd_i,
    input wire  [31:0]  write_data_i,
    input wire          reg_write_i,
    
    output wire [31:0]  pc_o,
    output wire [31:0]  pc_plus_4_o,
    output wire [9:0]   control_bus_o,
    output wire [31:0]  read_data_1_o,
    output wire [31:0]  read_data_2_o,
    output wire [31:0]  imm_gen_o,
    output wire [2:0]   funct3_o,
    output wire         bit30_o,
    output wire [4:0]   rd_o
    );

    wire [4:0] rs1_addr = instruction_i[19:15];
    wire [4:0] rs2_addr = instruction_i[24:20];
    wire [6:0] opcode   = instruction_i[6:0];
    wire [2:0] funct3   = instruction_i[14:12];
    wire       bit30    = instruction_i[30];

    assign pc_o = pc_i;
    assign pc_plus_4_o = pc_plus_4_i;

    assign rd_o = instruction_i[11:7];
    assign funct3_o = funct3;
    assign bit30_o = bit30;
    
    register register (
        .clk        (clk),
        .reset      (reset),
        .reg_write  (reg_write_i),
        .rs1        (rs1_addr),
        .rs2        (rs2_addr),
        .rd         (rd_i),
        .write_data (write_data_i),
        .read_data1 (read_data_1_o),
        .read_data2 (read_data_2_o)
    );

    control control (
        .opcode     (opcode),
        .control_bus(control_bus_o)
    );

    imm_gen imm_gen (
        .instruction(instruction_i),
        .imm_out    (imm_gen_o)
    );


endmodule
