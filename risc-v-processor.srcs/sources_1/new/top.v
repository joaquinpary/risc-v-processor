`timescale 1ns / 1ps

module top(
    input wire          clk,
    input wire          reset,
    input wire  [31:0]  instruction_i,      // Instruction
    input wire          ins_write_en_i,     // Enable Write Instruction
    input wire  [31:0]  ins_addr_i,         // Address Instruction
    input wire  [5:0]   debug_reg_addr_i,   // Register Address
    input wire  [9:0]   debug_mem_addr_i,   // Memory Address

    output wire [31:0]  debug_reg_data_o,   // Register Data
    output wire [31:0]  debug_mem_data_o,   // Memory Data
    output wire [31:0]  pc_o
    );

    // IF stage wires (outputs of instruction_fetch)
    wire    [31:0]  pc_if;
    wire    [31:0]  pc_plus_4_if;
    wire    [31:0]  instruction_if;
    wire    [31:0]  pc_branch_mem;
    wire            pc_src_mem;

    // IF/ID latch registers
    reg     [31:0]  pc_id;
    reg     [31:0]  pc_plus_4_id;
    reg     [31:0]  instruction_id;

    // ID stage wires (outputs of instruction_decode)
    wire    [4:0]   reg_d_wb;
    wire    [31:0]  reg_data_wb;
    wire            reg_write_wb;
    wire    [31:0]  pc_o_id;
    wire    [31:0]  pc_plus_4_o_id;
    wire    [9:0]   control_bus_o_id;
    wire    [31:0]  read_data_1_o_id;
    wire    [31:0]  read_data_2_o_id;
    wire    [31:0]  imm_gen_o_id;
    wire    [2:0]   funct3_o_id;
    wire            bit30_o_id;
    wire    [4:0]   rd_o_id;

    // ID/EX latch registers
    reg     [31:0]  pc_ex;
    reg     [31:0]  pc_plus_4_ex;
    reg     [31:0]  pc_branch_ex;
    reg     [9:0]   control_bus_ex;
    reg     [31:0]  read_data_1_ex;
    reg     [31:0]  read_data_2_ex;
    reg     [31:0]  imm_gen_ex;
    reg     [2:0]   funct3_ex;
    reg             bit30_ex;
    reg     [4:0]   rd_ex;

    // EX stage wires (outputs of execute)
    wire    [6:0]   control_o_ex;
    wire    [31:0]  pc_plus_4_o_ex;
    wire    [31:0]  pc_branch_o_ex;
    wire            zero_o_ex;
    wire    [31:0]  result_o_ex;
    wire    [31:0]  rs2_data_o_ex;
    wire    [2:0]   funct3_o_ex;
    wire    [4:0]   rd_o_ex;

    // EX/MEM latch registers
    reg     [31:0]  pc_plus_4_mem;
    reg     [31:0]  pc_branch_mem_latch;
    reg     [6:0]   control_mem;
    reg             zero_mem;
    reg     [31:0]  result_mem;
    reg     [31:0]  rs2_data_mem;
    reg     [2:0]   funct3_mem;
    reg     [4:0]   rd_mem;

    // MEM stage wires (outputs of memory)
    wire    [2:0]   control_o_mem;
    wire    [31:0]  pc_plus_4_o_mem;
    wire    [31:0]  result_o_mem;
    wire    [31:0]  read_data_o_mem;
    wire    [31:0]  mem_addr_o_mem;
    wire    [4:0]   rd_o_mem;

    // MEM/WB latch registers
    reg     [2:0]   control_wb;
    reg     [31:0]  read_data_wb_latch;
    reg     [31:0]  result_wb;
    reg     [31:0]  pc_plus_4_wb;
    reg     [4:0]   rd_wb;

    // ===== IF stage =====
    instruction_fetch u_if (
        .clk            (clk),
        .reset          (reset),
        .pc_write_en_i  (1'b1),
        .pc_src_i       (pc_src_mem),
        .branch_target_i(pc_branch_mem),
        .ins_write_en_i (ins_write_en_i),
        .instruction_i  (instruction_i),
        .mem_addr_i     (ins_addr_i),
        .pc_o           (pc_if),
        .pc_plus_4_o    (pc_plus_4_if),
        .instruction_o  (instruction_if)
    );

    assign pc_o = pc_if;

    // ===== IF/ID latch =====
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            pc_id          <= 32'b0;
            pc_plus_4_id   <= 32'b0;
            instruction_id <= 32'b0;
        end else begin
            pc_id          <= pc_if;
            pc_plus_4_id   <= pc_plus_4_if;
            instruction_id <= instruction_if;
        end
    end

    // ===== ID stage =====
    instruction_decode u_id (
        .clk             (clk),
        .reset           (reset),
        .pc_i            (pc_id),
        .pc_plus_4_i     (pc_plus_4_id),
        .instruction_i   (instruction_id),
        .rd_i            (rd_wb),
        .reg_data_i      (reg_data_wb),
        .reg_write_i     (reg_write_wb),
        .debug_reg_addr_i(debug_reg_addr_i),
        .debug_reg_data_o(debug_reg_data_o),
        .pc_o            (pc_o_id),
        .pc_plus_4_o     (pc_plus_4_o_id),
        .control_bus_o   (control_bus_o_id),
        .read_data_1_o   (read_data_1_o_id),
        .read_data_2_o   (read_data_2_o_id),
        .imm_gen_o       (imm_gen_o_id),
        .funct3_o        (funct3_o_id),
        .bit30_o         (bit30_o_id),
        .rd_o            (rd_o_id)
    );

    // ===== ID/EX latch =====
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            pc_ex          <= 32'b0;
            pc_plus_4_ex   <= 32'b0;
            pc_branch_ex   <= 32'b0;
            control_bus_ex <= 10'b0;
            read_data_1_ex <= 32'b0;
            read_data_2_ex <= 32'b0;
            imm_gen_ex     <= 32'b0;
            funct3_ex      <= 3'b0;
            bit30_ex       <= 1'b0;
            rd_ex          <= 5'b0;
        end else begin
            pc_ex          <= pc_o_id;
            pc_plus_4_ex   <= pc_plus_4_o_id;
            pc_branch_ex   <= pc_branch_o_ex;
            control_bus_ex <= control_bus_o_id;
            read_data_1_ex <= read_data_1_o_id;
            read_data_2_ex <= read_data_2_o_id;
            imm_gen_ex     <= imm_gen_o_id;
            funct3_ex      <= funct3_o_id;
            bit30_ex       <= bit30_o_id;
            rd_ex          <= rd_o_id;
        end
    end

    // ===== EX stage =====
    execute u_ex (
        .control_i      (control_bus_ex),
        .pc_i           (pc_ex),
        .pc_plus_4_i    (pc_plus_4_ex),
        .imm_gen_i      (imm_gen_ex),
        .rs1_data_i     (read_data_1_ex),
        .rs2_data_i     (read_data_2_ex),
        .funct3_i       (funct3_ex),
        .bit30_i        (bit30_ex),
        .rd_i           (rd_ex),
        .control_o      (control_o_ex),
        .pc_plus_4_o    (pc_plus_4_o_ex),
        .pc_branch_o    (pc_branch_o_ex),
        .zero_o         (zero_o_ex),
        .result_o       (result_o_ex),
        .rs2_data_o     (rs2_data_o_ex),
        .funct3_o       (funct3_o_ex),
        .rd_o           (rd_o_ex)
    );

    // ===== EX/MEM latch =====
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            pc_plus_4_mem       <= 32'b0;
            pc_branch_mem_latch <= 32'b0;
            control_mem         <= 7'b0;
            zero_mem            <= 1'b0;
            result_mem          <= 32'b0;
            rs2_data_mem        <= 32'b0;
            funct3_mem          <= 3'b0;
            rd_mem              <= 5'b0;
        end else begin
            pc_plus_4_mem       <= pc_plus_4_o_ex;
            pc_branch_mem_latch <= pc_branch_o_ex;
            control_mem         <= control_o_ex;
            zero_mem            <= zero_o_ex;
            result_mem          <= result_o_ex;
            rs2_data_mem        <= rs2_data_o_ex;
            funct3_mem          <= funct3_o_ex;
            rd_mem              <= rd_o_ex;
        end
    end

    // ===== MEM stage =====
    memory u_mem (
        .clk           (clk),
        .reset         (reset),
        .debug_addr_i  (debug_mem_addr_i),
        .control_i     (control_mem),
        .pc_plus_4_i   (pc_plus_4_mem),
        .pc_branch_i   (pc_branch_mem_latch),
        .zero_i        (zero_mem),
        .result_i      (result_mem),
        .data2_i       (rs2_data_mem),
        .funct3_i      (funct3_mem),
        .rd_i          (rd_mem),
        .control_o     (control_o_mem),
        .pc_plus_4_o   (pc_plus_4_o_mem),
        .pc_src_o      (pc_src_mem),
        .pc_branch_o   (pc_branch_mem),
        .result_o      (result_o_mem),
        .read_data_o   (read_data_o_mem),
        .mem_addr_o    (mem_addr_o_mem),
        .debug_data_o  (debug_mem_data_o),
        .rd_o          (rd_o_mem)
    );

    // ===== MEM/WB latch =====
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            control_wb         <= 3'b0;
            read_data_wb_latch <= 32'b0;
            result_wb          <= 32'b0;
            pc_plus_4_wb       <= 32'b0;
            rd_wb              <= 5'b0;
        end else begin
            control_wb         <= control_o_mem;
            read_data_wb_latch <= read_data_o_mem;
            result_wb          <= result_o_mem;
            pc_plus_4_wb       <= pc_plus_4_o_mem;
            rd_wb              <= rd_o_mem;
        end
    end

    // ===== WB stage =====
    write_back u_wb (
        .control_i      (control_wb),
        .read_data_i    (read_data_wb_latch),
        .result_i       (result_wb),
        .pc_plus_4_i    (pc_plus_4_wb),
        .rd_i           (rd_wb),
        .reg_write_o    (reg_write_wb),
        .write_data_o   (reg_data_wb),
        .rd_o           (reg_d_wb)
    );

endmodule
