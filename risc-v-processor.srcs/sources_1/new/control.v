`timescale 1ns / 1ps

module control(
    input wire  [6:0]   opcode,
    output wire [9:0]   control_bus
    );
    
    reg [9:0] control_bus_aux;
    
    always @(*) begin
        case (opcode)
            // ALUOp_ALUSrc_Branch_MemRead_MemWrite_Jump_RegWrite_MemtoReg
            // (2b)   (1b)    (1b)   (1b)     (1b)  (1b)   (1b)     (2b)
            // R-Type (add, sub, and, or...)
            7'b0110011: control_bus_aux = 10'b10_0_0_0_0_0_1_00;
            
            // I-Type (Aritmetic: addi, andi...)
            7'b0010011: control_bus_aux = 10'b11_1_0_0_0_0_1_00;
            
            // Loads (lw, lb, lh...)
            7'b0000011: control_bus_aux = 10'b00_1_0_1_0_0_1_01;
            
            // Stores (sw, sb, sh)
            7'b0100011: control_bus_aux = 10'b00_1_0_0_1_0_0_00;
            
            // Branches (beq, bne...)
            7'b1100011: control_bus_aux = 10'b01_0_1_0_0_0_0_00;
            
            // U-Type (lui)
            7'b0110111: control_bus_aux = 10'b00_1_0_0_0_0_1_00;
            
            // J-Type (jal)
            7'b1101111: control_bus_aux = 10'b00_0_0_0_0_1_1_10;
            
            // I-Type Jump (jalr)
            7'b1100111: control_bus_aux = 10'b00_1_0_0_0_1_1_10;
            
            // HALT
            7'b1111111: control_bus_aux = 10'b00_0_0_0_0_0_0_00;
            
            // Default
            default:    control_bus_aux = 10'b00_0_0_0_0_0_0_00;
        endcase
    end
    
    assign control_bus = control_bus_aux;            
endmodule
