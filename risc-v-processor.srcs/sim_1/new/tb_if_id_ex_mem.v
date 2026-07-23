`timescale 1ns / 1ps

module tb_if_id_ex_mem;

    reg          clk;
    reg          reset;

    // IF inputs
    reg          pc_write_en_i;
    reg          branch_sel_i;
    reg  [31:0]  branch_target_i;
    reg          ins_write_en_i;
    reg  [31:0]  instruction_i;
    reg  [31:0]  mem_addr_i;

    // IF outputs
    wire [31:0]  pc_o;
    wire [31:0]  pc_plus_4_o;
    wire [31:0]  if_instr_o;

    // ID inputs
    reg  [4:0]   id_rd_i;
    reg  [31:0]  id_write_data_i;
    reg          id_reg_write_i;

    // ID outputs
    wire [31:0]  id_pc_o;
    wire [31:0]  id_pc_plus_4_o;
    wire [9:0]   control_bus_o;
    wire [31:0]  read_data_1_o;
    wire [31:0]  read_data_2_o;
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

    // MEM inputs/outputs
    wire [2:0]   mem_control_o;
    wire [31:0]  mem_pc_plus_4_o;
    wire         mem_pc_src_o;
    wire [31:0]  mem_read_data_o;
    wire [31:0]  mem_addr_o;

    // Stage instances
    instruction_fetch u_if (
        .clk(clk),
        .reset(reset),
        .pc_write_en_i(pc_write_en_i),
        .branch_sel_i(branch_sel_i),
        .branch_target_i(branch_target_i),
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
        .write_data_i  (id_write_data_i),
        .reg_write_i   (id_reg_write_i),
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
        .control_o     (ex_control_o),
        .pc_plus_4_o   (ex_pc_plus_4_o),
        .pc_branch_o   (ex_pc_branch_o),
        .zero_o        (ex_zero_o),
        .result_o      (ex_result_o),
        .rs2_data_o    (ex_rs2_data_o),
        .funct3_o      (ex_funct3_o)
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
        .control_o     (mem_control_o),
        .pc_plus_4_o   (mem_pc_plus_4_o),
        .pc_src_o      (mem_pc_src_o),
        .read_data_o   (mem_read_data_o),
        .mem_addr_o    (mem_addr_o)
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
        $display("=== IF/ID/EX/MEM Integration Testbench ===");

        clk = 0;
        reset = 1;
        pc_write_en_i = 0;
        branch_sel_i = 0;
        branch_target_i = 0;
        ins_write_en_i = 0;
        instruction_i = 0;
        mem_addr_i = 0;
        id_rd_i = 0;
        id_write_data_i = 0;
        id_reg_write_i = 0;

        $display("--- Loading 6 instructions ---");
        #10 reset = 0;

        // addi x1,x0,42   addi x2,x0,100  lw x3, 8(x0) (read 8)
        // sw x2, 8(x0)    add x4,x1,x2    beq x0,x0,+8
        load_instr(10'd0,  32'h02A00093);  // addi x1,x0,42
        load_instr(10'd1,  32'h06400113);  // addi x2,x0,100
        load_instr(10'd2,  32'h0080_2183);  // lw x3, 8(x0)
        load_instr(10'd3,  32'h0080_2023);  // sw x2, 8(x0)
        load_instr(10'd4,  32'h0020_8233);  // add x4,x1,x2
        load_instr(10'd5,  32'h0000_0463);  // beq x0,x0,+8
        for (i = 6; i < 17; i = i + 1)
            load_instr(i[9:0], 32'h00000013);

        $display("--- Pipeline run: 6 cycles ---");
        pc_write_en_i = 1'b1;
        branch_sel_i = 1'b0;
        id_reg_write_i = 1'b0;

        for (i = 0; i < 6; i = i + 1) begin
            @(posedge clk); #1;
            $display("Cyc %0d | IF pc=%h instr=%h | ID rd=%2d imm=%h ctl=%b | EX result=%h zero=%b rs2=%h | MEM ctl=%b addr=%h rdata=%h pc_src=%b",
                i, pc_o, if_instr_o, rd_o, imm_gen_o, control_bus_o,
                ex_result_o, ex_zero_o, ex_rs2_data_o,
                mem_control_o, mem_addr_o, mem_read_data_o, mem_pc_src_o);
        end

        $display("--- Branch decision: beq x0,x0,+8 (should set pc_src=1) ---");
        branch_sel_i = 1'b1;
        branch_target_i = 32'h0000_0040;
        @(posedge clk); #1;
        $display("Cyc %0d | IF pc=%h instr=%h | ID rd=%2d imm=%h ctl=%b | EX zero=%b br_pc=%h | MEM pc_src=%b  (branch decision)",
            6, pc_o, if_instr_o, rd_o, imm_gen_o, control_bus_o, ex_zero_o, ex_pc_branch_o, mem_pc_src_o);
        branch_sel_i = 1'b0;

        $display("--- End of IF/ID/EX/MEM test ---");
        $finish;
    end

endmodule
