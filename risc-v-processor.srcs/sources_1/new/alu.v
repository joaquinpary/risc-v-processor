`timescale 1ns / 1ps

// =============================================================================
// alu
//
// Unidad aritmetico-logica de 32 bits.
//
// Los codigos 0000/0001/0010/0110 son los originales (AND/OR/ADD/SUB) y se
// mantienen sin cambios para no romper lo que ya andaba; el resto se agrego
// para completar las instrucciones que pide el TP.
//
// Para los desplazamientos la cantidad sale de data_b_i[4:0], que sirve tanto
// para tipo R (shamt en rs2) como para tipo I (shamt en imm[4:0]).
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
            // SLT compara con signo, SLTU sin signo: 1 o 0 en el bit menos
            // significativo, el resto en cero.
            ALU_SLT:  result_aux = ($signed(data_a_i) < $signed(data_b_i))
                                   ? 32'd1 : 32'd0;
            ALU_SRA:  result_aux = $signed(data_a_i) >>> shamt;
            ALU_SLTU: result_aux = (data_a_i < data_b_i) ? 32'd1 : 32'd0;
            default:  result_aux = 32'b0;
        endcase
    end

    assign result_o = result_aux;

    // zero_o lo usan los branches: para beq/bne la ALU resta, asi que
    // zero_o = (rs1 == rs2).
    assign zero_o = (result_aux == 32'b0);

endmodule
