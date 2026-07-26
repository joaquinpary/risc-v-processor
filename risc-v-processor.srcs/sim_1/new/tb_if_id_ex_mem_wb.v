`timescale 1ns / 1ps

module tb_if_id_ex_mem_wb;

    reg          clk;
    reg          reset;

    // IF inputs
    reg          pc_write_en_i;
    reg          pc_src_i;
    reg  [31:0]  pc_branch_i;
    reg          ins_write_en_i;
    reg  [31:0]  instruction_i;
    reg  [31:0]  mem_addr_i;

    // IF outputs
    wire [31:0]  pc_o;
    wire [31:0]  pc_plus_4_o;
    wire [31:0]  if_instr_o;

    // ID inputs
    reg  [4:0]   id_rd_i;
    reg  [31:0]  id_reg_data_i;
    reg          id_reg_write_i;
    reg  [5:0]   id_debug_reg_addr;

    // ID outputs
    wire [31:0]  id_pc_o;
    wire [31:0]  id_pc_plus_4_o;
    wire [9:0]   control_bus_o;
    wire [31:0]  read_data_1_o;
    wire [31:0]  read_data_2_o;
    wire [31:0]  id_debug_reg_data;
    wire [31:0]  imm_gen_o;
    wire [2:0]   funct3_o;
    wire         bit30_o;
    wire [4:0]   rd_o;

    // EX outputs
    wire [6:0]   ex_control_o;
    wire [31:0]  ex_pc_plus_4_o;
    wire [31:0]  ex_pc_branch_o;
    wire         ex_zero_o;
    wire [31:0]  ex_result_o;
    wire [31:0]  ex_rs2_data_o;
    wire [2:0]   ex_funct3_o;
    wire [4:0]   ex_rd_o;

    // MEM outputs
    wire [2:0]   mem_control_o;
    wire [31:0]  mem_pc_plus_4_o;
    wire         mem_pc_src_o;
    wire [31:0]  mem_result_o;
    wire [31:0]  mem_read_data_o;
    wire [31:0]  mem_addr_o;
    wire [4:0]   mem_rd_o;

    // WB outputs
    wire         wb_reg_write_o;
    wire [31:0]  wb_reg_data_write_o;
    wire [4:0]   wb_rd_o;

    // Stage instances
    instruction_fetch u_if (
        .clk(clk),
        .reset(reset),
        .pc_write_en_i(pc_write_en_i),
        .pc_src_i(pc_src_i),
        .pc_branch_i(pc_branch_i),
        .ins_write_en_i(ins_write_en_i),
        .instruction_i(instruction_i),
        .mem_addr_i(mem_addr_i),
        .pc_o(pc_o),
        .pc_plus_4_o(pc_plus_4_o),
        .instruction_o(if_instr_o)
    );

    instruction_decode u_id (
        .clk           (clk),
        .reset         (reset),
        .pc_i          (pc_o),
        .pc_plus_4_i   (pc_plus_4_o),
        .instruction_i (if_instr_o),
        .rd_i          (id_rd_i),
        .reg_data_i      (id_reg_data_i),
        .reg_write_i   (id_reg_write_i),
        .debug_reg_addr_i(id_debug_reg_addr),
        .debug_reg_data_o(id_debug_reg_data),
        .pc_o          (id_pc_o),
        .pc_plus_4_o   (id_pc_plus_4_o),
        .control_bus_o (control_bus_o),
        .read_data_1_o (read_data_1_o),
        .read_data_2_o (read_data_2_o),
        .imm_gen_o     (imm_gen_o),
        .funct3_o      (funct3_o),
        .bit30_o       (bit30_o),
        .rd_o          (rd_o)
    );

    execute u_ex (
        .control_i     (control_bus_o),
        .pc_i          (id_pc_o),
        .pc_plus_4_i   (id_pc_plus_4_o),
        .imm_gen_i     (imm_gen_o),
        .rs1_data_i    (read_data_1_o),
        .rs2_data_i    (read_data_2_o),
        .funct3_i      (funct3_o),
        .bit30_i       (bit30_o),
        .rd_i          (rd_o),
        .control_o     (ex_control_o),
        .pc_plus_4_o   (ex_pc_plus_4_o),
        .pc_branch_o   (ex_pc_branch_o),
        .zero_o        (ex_zero_o),
        .result_o      (ex_result_o),
        .rs2_data_o    (ex_rs2_data_o),
        .funct3_o      (ex_funct3_o),
        .rd_o          (ex_rd_o)
    );

    memory u_mem (
        .clk           (clk),
        .reset         (reset),
        .control_i     (ex_control_o),
        .pc_plus_4_i   (ex_pc_plus_4_o),
        .zero_i        (ex_zero_o),
        .result_i      (ex_result_o),
        .data2_i       (ex_rs2_data_o),
        .funct3_i      (ex_funct3_o),
        .rd_i          (ex_rd_o),
        .control_o     (mem_control_o),
        .pc_plus_4_o   (mem_pc_plus_4_o),
        .pc_src_o      (mem_pc_src_o),
        .result_o      (mem_result_o),
        .read_data_o   (mem_read_data_o),
        .mem_addr_o    (mem_addr_o),
        .rd_o          (mem_rd_o)
    );

    write_back u_wb (
        .control_i       (mem_control_o),
        .read_data_i     (mem_read_data_o),
        .result_i        (mem_result_o),
        .pc_plus_4_i     (mem_pc_plus_4_o),
        .rd_i            (mem_rd_o),
        .reg_write_o     (wb_reg_write_o),
        .write_data_o(wb_reg_data_write_o),
        .rd_o            (wb_rd_o)
    );

    always #5 clk = ~clk;

    task load_instr(input [9:0] word_addr, input [31:0] data);
        begin
            mem_addr_i = {22'b0, word_addr[9:0]};
            instruction_i = data;
            ins_write_en_i = 1'b1;
            @(posedge clk);
            #1;
            ins_write_en_i = 1'b0;
        end
    endtask

    integer i;

    initial begin
        $display("=== IF/ID/EX/MEM/WB Integration Testbench ===");

        clk = 0;
        reset = 1;
        pc_write_en_i = 0;
        pc_src_i = 0;
        pc_branch_i = 0;
        ins_write_en_i = 0;
        instruction_i = 0;
        mem_addr_i = 0;
        id_rd_i = 0;
        id_reg_data_i = 0;
        id_reg_write_i = 0;
        id_debug_reg_addr = 6'd0;

        $display("--- Loading 6 instructions ---");
        #10 reset = 0;

        // addi x1,x0,42   addi x2,x0,100  lw x3, 8(x0)
        // sw x0, 0(x0)    add x4,x1,x2    beq x0,x0,+8
        load_instr(10'd0,  32'h02A00093);  // addi x1,x0,42
        load_instr(10'd1,  32'h06400113);  // addi x2,x0,100
        load_instr(10'd2,  32'h0080_2183);  // lw x3, 8(x0)
        load_instr(10'd3,  32'h00002023);  // sw x0, 0(x0)
        load_instr(10'd4,  32'h0020_8233);  // add x4,x1,x2
        load_instr(10'd5,  32'h0000_0463);  // beq x0,x0,+8
        for (i = 6; i < 17; i = i + 1)
            load_instr(i[9:0], 32'h00000013);

        $display("--- Pipeline run: 6 cycles ---");
        pc_write_en_i = 1'b1;
        pc_src_i = 1'b0;
        id_reg_write_i = 1'b0;

        for (i = 0; i < 6; i = i + 1) begin
            @(posedge clk); #1;
            $display("Cyc %0d | IF pc=%h | ID rd=%2d | EX result=%h | MEM ctl=%b rdata=%h | WB reg_we=%b rd=%2d wdata=%h",
                i, pc_o, rd_o, ex_result_o, mem_control_o, mem_read_data_o,
                wb_reg_write_o, wb_rd_o, wb_reg_data_write_o);
        end

        $display("--- Branch decision: beq x0,x0 ---");
        pc_src_i = 1'b1;
        pc_branch_i = 32'h0000_0040;
        @(posedge clk); #1;
        $display("Cyc %0d | IF pc=%h | ID rd=%2d | EX zero=%b | MEM pc_src=%b | WB reg_we=%b rd=%2d wdata=%h",
            6, pc_o, rd_o, ex_zero_o, mem_pc_src_o, wb_reg_write_o, wb_rd_o, wb_reg_data_write_o);
        pc_src_i = 1'b0;

        $display("--- End of IF/ID/EX/MEM/WB test ---");
        $finish;
    end

endmodule
