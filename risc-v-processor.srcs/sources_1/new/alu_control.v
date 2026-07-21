`timescale 1ns / 1ps

module alu_control(
    input wire  [1:0]   alu_op_i,
    input wire  [2:0]   funct3_i,
    input wire          bit30_i,
    
    output wire [3:0]   alu_ctrl_o
    );
    
    reg [3:0]   alu_ctrl_aux;
    
    always @(*) begin
        case (alu_op_i)
            2'b00: begin
                alu_ctrl_aux = 4'b0010;
            end
            2'b01: begin
                alu_ctrl_aux = 4'b0110;
            end
            2'b10: begin
                case (funct3_i)
                    3'b000: begin
                        if (bit30_i == 1'b1)
                            alu_ctrl_aux = 4'b0110;
                        else
                            alu_ctrl_aux = 4'b0010;
                    end
                    3'b111: alu_ctrl_aux = 4'b0000;
                    3'b110: alu_ctrl_aux = 4'b0001;
                    default: alu_ctrl_aux = 4'b0000;
                endcase
            end
            2'b11: begin
                case (funct3_i)
                    3'b000: alu_ctrl_aux = 4'b0010;
                    3'b111: alu_ctrl_aux = 4'b0000; 
                    3'b110: alu_ctrl_aux = 4'b0001;
                    default: alu_ctrl_aux = 4'b0000;
                endcase
            end
            default: alu_ctrl_aux = 4'b0000;
        endcase
    end
    
    assign alu_ctrl_o = alu_ctrl_aux;
    
endmodule
