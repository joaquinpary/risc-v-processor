`timescale 1ns / 1ps

module tb_instruction_fetch;

    reg          clk;
    reg          reset;
    reg          pc_write_en_i;
    reg          pc_src_i;
    reg  [31:0]  branch_target_i;
    reg          ins_write_en_i;
    reg  [31:0]  instruction_i;
    reg  [31:0]  mem_addr_i;
    wire [31:0]  pc_o;
    wire [31:0]  pc_plus_4_o;
    wire [31:0]  instruction_o;

    instruction_fetch uut (
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
        .instruction_o(instruction_o)
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
    reg [31:0] expected_instr;

    initial begin
        clk = 0;
        reset = 1;
        pc_write_en_i = 0;
        pc_src_i = 0;
        branch_target_i = 0;
        ins_write_en_i = 0;
        instruction_i = 0;
        mem_addr_i = 0;

        $display("=== IF Stage Testbench ===");
        $display("--- Loading 10 instructions ---");

        #10 reset = 0;

        // addi x1,x0,1   addi x2,x0,2   addi x3,x0,3   addi x4,x0,4   addi x5,x0,5
        // beq x1,x0,+0   addi x6,x0,6   addi x7,x0,7   jal x1,+16     addi x8,x0,8 (skipped)
        load_instr(10'd0,  32'h00100093);
        load_instr(10'd1,  32'h00200113);
        load_instr(10'd2,  32'h00300193);
        load_instr(10'd3,  32'h00400213);
        load_instr(10'd4,  32'h00500293);
        load_instr(10'd5,  32'h00008063);  // beq (no branch)
        load_instr(10'd6,  32'h00600313);
        load_instr(10'd7,  32'h00700393);
        load_instr(10'd8,  32'h00C000EF);  // jal +16 -> word 16
        load_instr(10'd9,  32'h00800413);  // skipped by JAL
        load_instr(10'd10, 32'h00900493);
        // Words 11..16 with NOPs
        for (i = 11; i < 17; i = i + 1)
            load_instr(i[9:0], 32'h00000013);

        $display("--- Sequential fetch (8 cycles) ---");
        pc_write_en_i = 1'b1;
        pc_src_i = 1'b0;

        for (i = 0; i < 8; i = i + 1) begin
            case (i)
                0: expected_instr = 32'h00100093;
                1: expected_instr = 32'h00200113;
                2: expected_instr = 32'h00300193;
                3: expected_instr = 32'h00400213;
                4: expected_instr = 32'h00500293;
                5: expected_instr = 32'h00008063;
                6: expected_instr = 32'h00600313;
                7: expected_instr = 32'h00700393;
            endcase
            @(posedge clk); #1;
            $display("Ciclo %0d | pc=%h | pc+4=%h | instr=%h (esp %h) | %s",
                i, pc_o, pc_plus_4_o, instruction_o, expected_instr,
                (instruction_o === expected_instr) ? "OK" : "FAIL");
        end

        $display("--- Branch: JAL x1, +16 (from word 8 to word 16) ---");
        // Cycle 8: JAL is fetched. Activate branch_sel AFTER the edge to see it in the next cycle.
        expected_instr = 32'h00C000EF;
        @(posedge clk); #1;
        $display("Ciclo %0d | pc=%h | instr=%h (esp %h) | %s  (JAL fetched)",
            8, pc_o, instruction_o, expected_instr,
            (instruction_o === expected_instr) ? "OK" : "FAIL");

        pc_src_i = 1'b1;
        branch_target_i = 32'h00000040;  // 0x40 = word 16

        // Cycle 9: PC_REG updates to branch_target
        @(posedge clk); #1;
        $display("Ciclo %0d | pc=%h (esp 0x00000040) | instr=%h (esp 00800413) | %s  (branch taken - delay slot)",
            9, pc_o, instruction_o,
            (pc_o === 32'h00000040 && instruction_o === 32'h00800413) ? "OK" : "FAIL");
        pc_src_i = 1'b0;

        @(posedge clk); #1;
        $display("Ciclo %0d | pc=%h (esp 00000044) | instr=%h (esp 00000013=NOP) | %s  (Jump instruction read)",
            10, pc_o, instruction_o,
            (pc_o === 32'h00000044 && instruction_o === 32'h00000013) ? "OK" : "FAIL");
       
        $display("--- End of fetch ---");
        $finish;
    end

endmodule
