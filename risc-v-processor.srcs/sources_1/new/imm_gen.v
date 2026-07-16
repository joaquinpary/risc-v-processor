`timescale 1ns / 1ps

module imm_gen (
    input  wire [31:0] instruction,
    output wire [31:0] imm_out
);

    wire [6:0] opcode = instruction[6:0];
    reg [31:0] imm_out_aux;
    
    always @(*) begin
        case (opcode)
            7'b0000011, 7'b0010011, 7'b1100111: begin
                imm_out_aux = {{20{instruction[31]}}, instruction[31:20]};
            end

            7'b0100011: begin
                imm_out_aux = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};
            end

            7'b1100011: begin
                imm_out_aux = {{20{instruction[31]}}, instruction[7], instruction[30:25], instruction[11:8], 1'b0};
            end

            7'b0110111: begin
                imm_out_aux = {instruction[31:12], 12'b0};
            end

            7'b1101111: begin
                imm_out_aux = {{12{instruction[31]}}, instruction[19:12], instruction[20], instruction[30:21], 1'b0};
            end

            default: begin
                imm_out_aux = 32'b0;
            end
        endcase
    end
    
    assign imm_out = imm_out_aux;

endmodule
