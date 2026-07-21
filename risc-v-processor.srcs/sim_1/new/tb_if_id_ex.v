`timescale 1ns / 1ps

module tb_if_id_ex;

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

    // ID inputs (driven from a fake WB stage)
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
        .clk           (clk),
        .reset         (reset),
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
        .result_o      (ex_result_o)
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
        $display("=== IF/ID/EX Integration Testbench ===");

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

        $display("--- Loading 8 instructions ---");
        #10 reset = 0;

        // addi x1,x0,1   addi x2,x0,2   addi x3,x0,3   addi x4,x0,4
        // add x5,x1,x2   lw x6,8(x0)    sw x7,12(x0)   beq x0,x0,+8
        load_instr(10'd0,  32'h00100093);
        load_instr(10'd1,  32'h00200113);
        load_instr(10'd2,  32'h00300193);
        load_instr(10'd3,  32'h00400213);
        load_instr(10'd4,  32'h0020_82B3);  // add x5,x1,x2
        load_instr(10'd5,  32'h0080_2303);  // lw x6,8(x0)
        load_instr(10'd6,  32'h00C0_2023);  // sw x0,0(x0) -- NOTE: encoding uses rs2=0, rd=0, imm=0 (not x7,12)
        load_instr(10'd7,  32'h0000_0463);  // beq x0,x0,+8
        // Word 16 for branch target (NOP)
        for (i = 8; i < 17; i = i + 1)
            load_instr(i[9:0], 32'h00000013);

        $display("--- Pipeline run: 8 cycles ---");
        pc_write_en_i = 1'b1;
        branch_sel_i = 1'b0;
        id_reg_write_i = 1'b0;

        for (i = 0; i < 8; i = i + 1) begin
            @(posedge clk); #1;
            $display("Cyc %0d | IF pc=%h instr=%h | ID rd=%2d r1=%h r2=%h imm=%h ctl=%b funct3=%b bit30=%b | EX result=%h zero=%b br_pc=%h pc+4=%h ctl_o=%b",
                i, pc_o, if_instr_o, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o,
                funct3_o, bit30_o, ex_result_o, ex_zero_o, ex_pc_branch_o, ex_pc_plus_4_o, ex_control_o);
        end

        $display("--- Branch target scenario ---");
        // In cyc 8 the branch was just fetched. Activate branch_sel to land on pc=0x40.
        branch_sel_i = 1'b1;
        branch_target_i = 32'h0000_0040;

        @(posedge clk); #1;
        $display("Cyc %2d | IF pc=%h instr=%h | ID rd=%2d imm=%h ctl=%b funct3=%b bit30=%b | EX result=%h zero=%b br_pc=%h pc+4=%h  (branch taken)",
            8, pc_o, if_instr_o, rd_o, imm_gen_o, control_bus_o, funct3_o, bit30_o, ex_result_o, ex_zero_o, ex_pc_branch_o, ex_pc_plus_4_o);
        branch_sel_i = 1'b0;

        @(posedge clk); #1;
        $display("Cyc %2d | IF pc=%h instr=%h | ID rd=%2d imm=%h ctl=%b funct3=%b bit30=%b | EX result=%h zero=%b pc+4=%h  (post-branch NOP)",
            9, pc_o, if_instr_o, rd_o, imm_gen_o, control_bus_o, funct3_o, bit30_o, ex_result_o, ex_zero_o, ex_pc_plus_4_o);

        $display("");
        $display("--- Coverage notes ---");
        $display("alu_control.v only implements funct3: 000 (add/sub via bit30), 110 (or), 111 (and).");
        $display("Other funct3 values (001 sll, 010 slt, 100 xor, 101 srl/sra) -> alu_ctrl=0000 (AND), result may not match instruction semantics.");

        $display("--- End of IF/ID/EX test ---");
        $finish;
    end

endmodule
