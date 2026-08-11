`timescale 1ns / 1ps

// =============================================================================
// alu_control
//
// Traduce el ALUOp del bus de control (2 bits) mas funct3 y el bit 30 de la
// instruccion al codigo de 4 bits que entiende la ALU.
//
//   ALUOp = 00 -> ADD  (lw, sw, lui, jalr: calculo de direccion)
//   ALUOp = 01 -> SUB  (branches: zero_o dice si rs1 == rs2)
//   ALUOp = 10 -> tipo R, se decodifica con funct3 + bit30
//   ALUOp = 11 -> tipo I aritmetico, se decodifica con funct3
//
// OJO con el bit 30 en ALUOp = 11: para addi ese bit es parte del inmediato
// (addi con un numero negativo lo tiene en 1), asi que NO se puede usar para
// elegir entre suma y resta. Solo es una variante real en srli/srai, donde
// pertenece al campo funct7 del formato de desplazamiento inmediato.
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
        // Valor por defecto: todos los caminos asignan, pero dejarlo explicito
        // evita cualquier riesgo de latch inferido.
        alu_ctrl_aux = ALU_ADD;

        case (alu_op_i)
            // ---- Direcciones de memoria, lui y jalr ----
            2'b00: alu_ctrl_aux = ALU_ADD;

            // ---- Branches: la resta deja zero_o en 1 si son iguales ----
            2'b01: alu_ctrl_aux = ALU_SUB;

            // ---- Tipo R ----
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

            // ---- Tipo I aritmetico ----
            2'b11: begin
                case (funct3_i)
                    // addi: bit30 es parte del inmediato, se ignora
                    3'b000: alu_ctrl_aux = ALU_ADD;                     // addi
                    3'b001: alu_ctrl_aux = ALU_SLL;                     // slli
                    3'b010: alu_ctrl_aux = ALU_SLT;                     // slti
                    3'b011: alu_ctrl_aux = ALU_SLTU;                    // sltiu
                    3'b100: alu_ctrl_aux = ALU_XOR;                     // xori
                    // srli/srai: aca el bit30 SI distingue la variante
                    3'b101: alu_ctrl_aux = bit30_i ? ALU_SRA : ALU_SRL; // srli/srai
                    3'b110: alu_ctrl_aux = ALU_OR;                      // ori
                    3'b111: alu_ctrl_aux = ALU_AND;                     // andi
                endcase
            end
        endcase
    end

    assign alu_ctrl_o = alu_ctrl_aux;

endmodule
