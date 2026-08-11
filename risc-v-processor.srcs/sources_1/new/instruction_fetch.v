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

    // -------------------------------------------------------------------
    // PC alineado con su instruccion
    //
    // La BRAM de instrucciones tiene latencia de lectura 1: la palabra sale un
    // ciclo despues de presentar la direccion, y para entonces pc_reg ya
    // avanzo. Sin corregirlo, el latch IF/ID guarda la instruccion de la
    // direccion P junto con el PC P+4, y como el destino de un salto se calcula
    // pc + imm, TODOS los saltos quedaban corridos 4 bytes (y el valor de
    // enlace de jal tambien).
    //
    // pc_fetched va un ciclo atras de pc_reg, o sea que viaja junto a la
    // instruccion que sale por doutb. Comparte el enable con pc_reg, asi que
    // durante un stall los dos se congelan juntos y la alineacion se mantiene.
    // -------------------------------------------------------------------
    reg [31:0] pc_fetched;

    always @(posedge clk) begin
        if (reset)
            pc_fetched <= 32'h0000_0000;
        else if (pc_write_en_i)
            pc_fetched <= pc_reg;
    end
    
    // Intruction memory
    
    instruction_memory instruction_memory (
        .addra  (mem_addr_i[11:2]),
        .clka   (clk),
        .dina   (instruction_i),
        .ena    (ins_write_en_i),
        .wea    (1'b1),
        
        .addrb  (pc_reg[11:2]),         // direccion en curso
        .clkb   (clk),
        .doutb  (instruction_o)
    );

    // pc_o y pc_plus_4_o acompanan a instruction_o, no a la busqueda en curso
    assign pc_o = pc_fetched;
    assign pc_plus_4_o = pc_fetched + 32'd4;
    
endmodule
