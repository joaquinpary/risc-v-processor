`timescale 1ns / 1ps

// =============================================================================
// write_back
//
// Picks what gets written to the register file and, for the loads, extracts
// the right byte or half word.
//
// The extraction goes here and not in memory.v because the BRAM only delivers
// the data during the WB cycle. Everything needed arrives through the MEM/WB
// latch: funct3_i tells the size and whether to sign extend, and result_i is
// the effective address, so result_i[1:0] gives the byte inside the word.
// =============================================================================

module write_back(
    input wire  [2:0]   control_i,
    input wire  [2:0]   funct3_i,
    input wire  [31:0]  read_data_i,
    input wire  [31:0]  result_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [4:0]   rd_i,

    output wire         reg_write_o,
    output wire [31:0]  write_data_o,
    output wire [4:0]   rd_o
    );

    reg     [31:0]  write_data;
    wire    [1:0]   mem_to_reg = control_i[1:0];

    // ---------------------------------------------------------------
    // Sub-word extraction of the loaded data
    // ---------------------------------------------------------------
    wire    [1:0]   byte_off = result_i[1:0];

    // Shift the word so the requested data ends up in the low part
    wire    [31:0]  aligned  = read_data_i >> (8 * byte_off);

    wire    [7:0]   byte_sel = aligned[7:0];
    wire    [15:0]  half_sel = aligned[15:0];

    reg     [31:0]  load_data;

    always @(*) begin
        case (funct3_i)
            // lb and lh sign extend; lbu and lhu pad with zeros
            3'b000:  load_data = {{24{byte_sel[7]}},  byte_sel};   // lb
            3'b001:  load_data = {{16{half_sel[15]}}, half_sel};   // lh
            3'b010:  load_data = read_data_i;                      // lw
            3'b100:  load_data = {24'b0, byte_sel};                // lbu
            3'b101:  load_data = {16'b0, half_sel};                // lhu
            default: load_data = read_data_i;
        endcase
    end

    // ---------------------------------------------------------------
    // Write MUX to the register file
    // ---------------------------------------------------------------
    always @(*) begin
        case (mem_to_reg)
            2'b00:   write_data = result_i;
            2'b01:   write_data = load_data;
            2'b10:   write_data = pc_plus_4_i;
            default: write_data = 32'b0;
        endcase
    end

    assign write_data_o = write_data;
    assign reg_write_o = control_i[2];
    assign rd_o = rd_i;

endmodule
