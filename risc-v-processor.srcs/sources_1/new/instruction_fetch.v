`timescale 1ns / 1ps

module instruction_fetch(
    input wire          clk,
    input wire          reset,
    
    input wire          pc_write_en_i,      // Flag to Enable PC Write (DEBUG MODE)
    input wire          pc_src_i,           // Branch flag
    input wire  [31:0]  pc_branch_i,    // Branch 
    input wire          ins_write_en_i,     // Flag for Instruction Load
    input wire  [31:0]  instruction_i,      // Intruction Load (UART)
    input wire  [31:0]  mem_addr_i,         // Address for Instruction Load
    output wire [31:0]  pc_o,               // Program Counter
    output wire [31:0]  pc_plus_4_o,        // Program Counter Plus 4
    output wire [31:0]  instruction_o       // Intruction Fetch
    );
    
    
    // PC register

    reg [31:0] pc_reg;
    
    always @(posedge clk) begin
        if (reset) begin
            pc_reg <= 32'h0000_0000;
        end else if (pc_write_en_i) begin
    // MUX2
            if (pc_src_i) begin
                pc_reg <= pc_branch_i;
            end else begin
                pc_reg <= pc_reg + 32'd4;
            end
        end
    end
    
    // Intruction memory
    
    instruction_memory instruction_memory (
        .addra  (mem_addr_i[11:2]),
        .clka   (clk),
        .dina   (instruction_i),
        .ena    (ins_write_en_i),
        .wea    (1'b1),
        
        .addrb  (pc_o[11:2]),           // PC+4
        .clkb   (clk),
        .doutb  (instruction_o)
    );
    
    assign pc_o = pc_reg;
    assign pc_plus_4_o = pc_reg + 32'd4;
    
endmodule
