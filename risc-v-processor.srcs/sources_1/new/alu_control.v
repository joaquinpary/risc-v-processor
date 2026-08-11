`timescale 1ns / 1ps

// =============================================================================
// alu_control
//
// Translates the ALUOp from the control bus (2 bits) plus funct3 and bit 30 of
// the instruction into the 4-bit code the ALU understands.
//
//   ALUOp = 00 -> ADD  (lw, sw, lui, jalr: address computation)
//   ALUOp = 01 -> SUB  (branches: zero_o tells whether rs1 == rs2)
//   ALUOp = 10 -> R-type, decoded with funct3 + bit30
//   ALUOp = 11 -> arithmetic I-type, decoded with funct3
//
// CAREFUL with bit 30 when ALUOp = 11: for addi that bit is part of the
// immediate (addi with a negative number has it set), so it CANNOT be used to
// pick between add and subtract. It is only a real variant in srli/srai, where
// it belongs to the funct7 field of the immediate shift format.
// =============================================================================

module alu_control(
    input wire  [1:0]   alu_op_i,
    input wire  [2:0]   funct3_i,
    input wire          bit30_i,

    output wire [3:0]   alu_ctrl_o
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

    reg [3:0]   alu_ctrl_aux;

    always @(*) begin
        // Default value: every path assigns, but making it explicit avoids any
        // risk of an inferred latch.
        alu_ctrl_aux = ALU_ADD;

        case (alu_op_i)
            // ---- Memory addresses, lui and jalr ----
            2'b00: alu_ctrl_aux = ALU_ADD;

            // ---- Branches: the subtraction leaves zero_o at 1 if equal ----
            2'b01: alu_ctrl_aux = ALU_SUB;

            // ---- R-type ----
            2'b10: begin
                case (funct3_i)
                    3'b000: alu_ctrl_aux = bit30_i ? ALU_SUB : ALU_ADD; // add/sub
                    3'b001: alu_ctrl_aux = ALU_SLL;                     // sll
                    3'b010: alu_ctrl_aux = ALU_SLT;                     // slt
                    3'b011: alu_ctrl_aux = ALU_SLTU;                    // sltu
                    3'b100: alu_ctrl_aux = ALU_XOR;                     // xor
                    3'b101: alu_ctrl_aux = bit30_i ? ALU_SRA : ALU_SRL; // srl/sra
                    3'b110: alu_ctrl_aux = ALU_OR;                      // or
                    3'b111: alu_ctrl_aux = ALU_AND;                     // and
                endcase
            end

            // ---- Arithmetic I-type ----
            2'b11: begin
                case (funct3_i)
                    // addi: bit30 is part of the immediate, it is ignored
                    3'b000: alu_ctrl_aux = ALU_ADD;                     // addi
                    3'b001: alu_ctrl_aux = ALU_SLL;                     // slli
                    3'b010: alu_ctrl_aux = ALU_SLT;                     // slti
                    3'b011: alu_ctrl_aux = ALU_SLTU;                    // sltiu
                    3'b100: alu_ctrl_aux = ALU_XOR;                     // xori
                    // srli/srai: here bit30 DOES tell the variants apart
                    3'b101: alu_ctrl_aux = bit30_i ? ALU_SRA : ALU_SRL; // srli/srai
                    3'b110: alu_ctrl_aux = ALU_OR;                      // ori
                    3'b111: alu_ctrl_aux = ALU_AND;                     // andi
                endcase
            end
        endcase
    end

    assign alu_ctrl_o = alu_ctrl_aux;

endmodule
