`timescale 1ns / 1ps

// =============================================================================
// alu
//
// 32-bit arithmetic and logic unit.
//
// The codes 0000/0001/0010/0110 are the original ones (AND/OR/ADD/SUB) and are
// kept unchanged so nothing that already worked breaks; the rest were added to
// complete the instructions required by the TP.
//
// For the shifts the amount comes from data_b_i[4:0], which works for both
// R-type (shamt in rs2) and I-type (shamt in imm[4:0]).
// =============================================================================

module alu (
    input wire  [31:0] data_a_i,
    input wire  [31:0] data_b_i,
    input wire  [3:0]  alu_control_i,
    output wire [31:0] result_o,
    output wire        zero_o
);

    localparam [3:0] ALU_AND  = 4'b0000;
    localparam [3:0] ALU_OR   = 4'b0001;
    localparam [3:0] ALU_ADD  = 4'b0010;
    localparam [3:0] ALU_XOR  = 4'b0011;
    localparam [3:0] ALU_SLL  = 4'b0100;
    localparam [3:0] ALU_SRL  = 4'b0101;
    localparam [3:0] ALU_SUB  = 4'b0110;
    localparam [3:0] ALU_SLT  = 4'b0111;
    localparam [3:0] ALU_SRA  = 4'b1000;
    localparam [3:0] ALU_SLTU = 4'b1001;

    reg [31:0]  result_aux;

    wire [4:0]  shamt = data_b_i[4:0];

    always @(*) begin
        case (alu_control_i)
            ALU_AND:  result_aux = data_a_i & data_b_i;
            ALU_OR:   result_aux = data_a_i | data_b_i;
            ALU_ADD:  result_aux = data_a_i + data_b_i;
            ALU_XOR:  result_aux = data_a_i ^ data_b_i;
            ALU_SLL:  result_aux = data_a_i << shamt;
            ALU_SRL:  result_aux = data_a_i >> shamt;
            ALU_SUB:  result_aux = data_a_i - data_b_i;
            // SLT compares signed, SLTU unsigned: 1 or 0 in the least
            // significant bit, the rest zero.
            ALU_SLT:  result_aux = ($signed(data_a_i) < $signed(data_b_i))
                                   ? 32'd1 : 32'd0;
            ALU_SRA:  result_aux = $signed(data_a_i) >>> shamt;
            ALU_SLTU: result_aux = (data_a_i < data_b_i) ? 32'd1 : 32'd0;
            default:  result_aux = 32'b0;
        endcase
    end

    assign result_o = result_aux;

    // zero_o is used by the branches: for beq/bne the ALU subtracts, so
    // zero_o = (rs1 == rs2).
    assign zero_o = (result_aux == 32'b0);

endmodule
