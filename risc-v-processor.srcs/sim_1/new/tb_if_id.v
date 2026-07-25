`timescale 1ns / 1ps

module tb_if_id;

    reg          clk;
    reg          reset;

    // IF inputs
    reg          pc_write_en_i;
    reg          pc_src_i;
    reg  [31:0]  branch_target_i;
    reg          ins_write_en_i;
    reg  [31:0]  instruction_i;
    reg  [31:0]  mem_addr_i;

    // IF outputs
    wire [31:0]  pc_o;
    wire [31:0]  pc_plus_4_o;
    wire [31:0]  if_instruction_o;

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

    instruction_fetch u_if (
        .clk(clk),
        .reset(reset),
        .pc_write_en_i(pc_write_en_i),
        .pc_src_i(pc_src_i),
        .branch_target_i(branch_target_i),
        .ins_write_en_i(ins_write_en_i),
        .instruction_i(instruction_i),
        .mem_addr_i(mem_addr_i),
        .pc_o(pc_o),
        .pc_plus_4_o(pc_plus_4_o),
        .instruction_o(if_instruction_o)
    );

    instruction_decode u_id (
        .clk           (clk),
        .reset         (reset),
        .pc_i          (pc_o),
        .pc_plus_4_i   (pc_plus_4_o),
        .instruction_i (if_instruction_o),
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
        $display("=== IF/ID Integration Testbench ===");

        clk = 0;
        reset = 1;
        pc_write_en_i = 0;
        pc_src_i = 0;
        branch_target_i = 0;
        ins_write_en_i = 0;
        instruction_i = 0;
        mem_addr_i = 0;
        id_rd_i = 0;
        id_reg_data_i = 0;
        id_reg_write_i = 0;
        id_debug_reg_addr = 6'd0;

        $display("--- Loading 8 instructions into instruction memory ---");
        #10 reset = 0;

        // addi x1,x0,1   addi x2,x0,2   addi x3,x0,3   addi x4,x0,4
        // add x5,x1,x2   lw x6,8(x0)    sw x7,12(x0)   jal x1,+16
        load_instr(10'd0,  32'h00100093);
        load_instr(10'd1,  32'h00200113);
        load_instr(10'd2,  32'h00300193);
        load_instr(10'd3,  32'h00400213);
        load_instr(10'd4,  32'h0020_82B3);  // add x5,x1,x2
        load_instr(10'd5,  32'h0080_2303);  // lw x6,8(x0)  -- approximate, opcode=0000011
        load_instr(10'd6,  32'h00C0_2023);  // sw x7,12(x0) -- approximate, opcode=0100011
        load_instr(10'd7,  32'h00C0_00EF);  // jal x1,+16
        // Word 16 for the jump target (NOP)
        for (i = 8; i < 17; i = i + 1)
            load_instr(i[9:0], 32'h00000013);

        $display("--- Pipeline run: 8 cycles ---");
        pc_write_en_i = 1'b1;
        pc_src_i = 1'b0;
        id_reg_write_i = 1'b0;

        for (i = 0; i < 8; i = i + 1) begin
            @(posedge clk); #1;
            $display("Cyc %0d | IF: pc=%h if_instr=%h || ID: rd_o=%2d rdata1=%h rdata2=%h imm=%h ctl=%b",
                i, pc_o, if_instruction_o, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o);
        end

        $display("--- JAL fetched: enable branch_sel to jump to word 16 ---");
        // Cycle 8: the JAL was already fetched at cycle 7 (pc=0x20).
        // Activate branch_sel right after that edge so PC_REG takes branch_target
        // on the next edge.
        pc_src_i = 1'b1;
        branch_target_i = 32'h0000_0040;  // word 16

        @(posedge clk); #1;
        $display("Cyc %2d | IF: pc=%h if_instr=%h || ID: rd_o=%2d rdata1=%h rdata2=%h imm=%h ctl=%b  (branch taken)",
            8, pc_o, if_instruction_o, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o);
        pc_src_i = 1'b0;

        @(posedge clk); #1;
        $display("Cyc %2d | IF: pc=%h if_instr=%h || ID: rd_o=%2d rdata1=%h rdata2=%h imm=%h ctl=%b  (post-branch, NOP from word 16)",
            9, pc_o, if_instruction_o, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o);

        @(posedge clk); #1;
        $display("Cyc %2d | IF: pc=%h if_instr=%h || ID: rd_o=%2d rdata1=%h rdata2=%h imm=%h ctl=%b  (continue after branch)",
            10, pc_o, if_instruction_o, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o);

        $display("--- End of IF/ID test ---");
        $finish;
    end

endmodule
