`timescale 1ns / 1ps

module execute(    
    input wire  [9:0]   control_i,
    input wire  [31:0]  pc_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [31:0]  imm_gen_i,
    input wire  [31:0]  rs1_data_i,
    input wire  [31:0]  rs2_data_i,
    input wire  [2:0]   funct3_i,
    input wire          bit30_i,
    
    output wire [6:0]   control_o,
    output wire [31:0]  pc_plus_4_o,
    output wire [31:0]  pc_branch_o,
    output wire         zero_o,
    output wire [31:0]  result_o,
    output wire [31:0]  rs2_data_o,
    output wire [2:0]   funct3_o
    );
    
    wire    [1:0]   alu_op = control_i[9:8];
    wire            alu_src = control_i[7];
    
    wire    [3:0]   alu_ctrl;
    
    // Branch ADD
    
    wire    [31:0]  imm_shifted = {imm_gen_i[30:0], 1'b0};
    assign pc_branch_o = pc_i + imm_shifted;  
    
    // MUX
    wire    [31:0]  data_2;
    assign data_2 = (alu_src == 1'b1) ? imm_gen_i : rs2_data_i;
    
    alu_control alu_control(
        .alu_op_i(alu_op),
        .funct3_i(funct3_i),
        .bit30_i(bit30_i),
    
        .alu_ctrl_o(alu_ctrl)
    );
    
    alu alu(
        .data_a_i(rs1_data_i),
        .data_b_i(data_2),
        .alu_control_i(alu_ctrl),
        .result_o(result_o),
        .zero_o(zero_o)
    );
    
    assign control_o = control_i[6:0];
    assign pc_plus_4_o = pc_plus_4_i;
    assign rs2_data_o = rs2_data_i;
    assign funct3_o = funct3_i;

endmodule
