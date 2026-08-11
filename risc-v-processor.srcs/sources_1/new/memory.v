`timescale 1ns / 1ps

module memory(
    input wire          clk,
    input wire          reset,
    input wire          enable_i,
    
    input wire  [9:0]   debug_addr_i,
    input wire  [6:0]   control_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [31:0]  pc_branch_i,
    input wire          zero_i,
    input wire  [31:0]  result_i,
    input wire  [31:0]  data2_i,
    input wire  [2:0]   funct3_i,
    input wire  [4:0]   rd_i,
    
    output wire [2:0]   control_o,
    output wire [31:0]  pc_plus_4_o,
    output wire         pc_src_o,
    output wire [31:0]  pc_branch_o,
    output wire [31:0]  result_o,
    output wire [31:0]  read_data_o,
    output wire [31:0]  mem_addr_o,
    output wire [31:0]  debug_data_o,
    output wire [4:0]   rd_o
    );
    
    // -------------------------------------------------------------------
    // Addressing
    //
    // The BRAM has 1024 words of 32 bits and addra is a WORD index, but
    // result_i is a BYTE address. It has to be split: bits [11:2] pick the
    // word and bits [1:0] the byte inside it.
    //
    // (Before, result_i[9:0] was used directly as a word index. For full word
    // accesses it was consistent with itself, but it jumped 4 positions at a
    // time and made it impossible to address a single byte.)
    // -------------------------------------------------------------------
    wire    [9:0]   mem_addr   = result_i[11:2];
    wire    [1:0]   byte_off   = result_i[1:0];

    wire            mem_write = control_i[4];
    wire            mem_read = control_i[5];
    // control_i[6] (Branch), control_i[3] (Jump), zero_i and pc_branch_i are no
    // longer used here: the branch decision is taken in EX.

    reg     [3:0]   size_mask;      // which bytes the instruction touches, unshifted
    reg     [3:0]   byte_write_en;
    reg     [31:0]  write_data;

    always @(*) begin
        case (funct3_i)
            3'b000:  size_mask = 4'b0001;   // sb
            3'b001:  size_mask = 4'b0011;   // sh
            3'b010:  size_mask = 4'b1111;   // sw
            default: size_mask = 4'b1111;
        endcase

        // The mask and the data are shifted to the lane the address points to:
        // without this an sb always wrote byte 0 no matter the offset.
        byte_write_en = mem_write ? (size_mask << byte_off) : 4'b0000;
        write_data    = data2_i << (8 * byte_off);
    end
    
    // PCSrc
    //
    // Branch resolution moved to the EX stage (see top.v): there it is decided
    // with funct3, which allows supporting bne besides beq and lowers the
    // penalty from 4 cycles to 3. (It is 3 and not 2 because the IF stage
    // takes two cycles due to the instruction BRAM latency: see
    // docs/pipeline-depth.md.) Leaving this output active would cause a second
    // PC redirection, so it is tied to zero.
    assign pc_src_o = 1'b0;
    
    // Data Memory
    
    data_memory data_memory(
        .addra(mem_addr),
        .clka(clk),
        .dina(write_data),
        .douta(read_data_o),
        .ena((mem_write | mem_read) & enable_i),
        .wea(byte_write_en),
        
        .addrb(debug_addr_i),
        .clkb(clk),
        .dinb(32'b0),
        .doutb(debug_data_o),
        .enb(1'b1),
        .web(4'b0000)
    );
    
    
    assign mem_addr_o = result_i;
    assign control_o = control_i[2:0];
    assign pc_plus_4_o = pc_plus_4_i;
    assign result_o = result_i;
    assign rd_o = rd_i;
    assign pc_branch_o = pc_branch_i;
    
endmodule
