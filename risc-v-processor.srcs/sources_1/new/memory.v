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
    
    wire    [9:0]   mem_addr = result_i[9:0];
    wire            mem_write = control_i[4];
    wire            mem_read = control_i[5];
    wire            branch = control_i[6];
    wire            jump = control_i[3];
    reg     [3:0]   byte_write_en;
    
    always @(*) begin
        if (mem_write) begin
            case (funct3_i)
                3'b000: byte_write_en = 4'b0001; // SB
                3'b001: byte_write_en = 4'b0011; // SH
                3'b010: byte_write_en = 4'b1111; // SW
                default: byte_write_en = 4'b1111;
            endcase
        end else begin
            byte_write_en = 4'b0000;
        end
    end
    
    // PCSrc
    
    assign pc_src_o = (branch & zero_i) | jump;
    
    // Data Memory
    
    data_memory data_memory(
        .addra(mem_addr),
        .clka(clk),
        .dina(data2_i),
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
