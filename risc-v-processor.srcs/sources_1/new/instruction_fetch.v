`timescale 1ns / 1ps

// =====================================================================
// IF stage - it takes TWO clock cycles
//
// instruction_memory is a block RAM with a registered output, so its read
// latency is 1: the word comes out of doutb one cycle after the address is
// presented on addrb. That splits the fetch in two:
//
//   IF1: pc_reg presents the address to the BRAM
//   IF2: the instruction is available on doutb (= instruction_o)
//
// and only on the next cycle does the IF/ID latch in top.v capture it. In
// register levels the pipeline has six, not five. The logical stages are
// still the classic five.
//
// Consequences (full analysis in docs/pipeline-depth.md):
//   - the penalty of a taken branch is 3 cycles, not 2
//   - pc_fetched is needed to align the PC with its instruction (see below)
//   - the skid buffer in top.v is needed, because port B was generated
//     without an ENB pin and its output register cannot be frozen on a stall
//
// Throughput is NOT affected: in steady state one instruction comes out per
// cycle.
// =====================================================================

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
    // PC aligned with its instruction
    //
    // The instruction BRAM has a read latency of 1: the word comes out one
    // cycle after the address is presented, and by then pc_reg has already
    // moved on. Without fixing this, the IF/ID latch stores the instruction of
    // address P together with the PC P+4, and since a branch target is
    // computed as pc + imm, EVERY branch was off by 4 bytes (and so was the
    // link value of jal).
    //
    // pc_fetched runs one cycle behind pc_reg, so it travels together with the
    // instruction coming out of doutb. It shares the enable with pc_reg, so
    // during a stall both freeze together and the alignment is kept.
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
        
        .addrb  (pc_reg[11:2]),         // address being fetched
        .clkb   (clk),
        .doutb  (instruction_o)
    );

    // pc_o and pc_plus_4_o go with instruction_o, not with the fetch in flight
    assign pc_o = pc_fetched;
    assign pc_plus_4_o = pc_fetched + 32'd4;
    
endmodule
