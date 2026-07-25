`timescale 1ns / 1ps

module tb_top;

    reg          clk;
    reg          reset;
    reg  [31:0]  instruction_i;
    reg          ins_write_en_i;
    reg  [31:0]  ins_addr_i;
    reg  [5:0]   debug_reg_addr_i;
    reg  [9:0]   debug_mem_addr_i;

    wire [31:0]  debug_reg_data_o;
    wire [31:0]  debug_mem_data_o;
    wire [31:0]  pc_o;

    top uut (
        .clk              (clk),
        .reset            (reset),
        .instruction_i    (instruction_i),
        .ins_write_en_i   (ins_write_en_i),
        .ins_addr_i       (ins_addr_i),
        .debug_reg_addr_i (debug_reg_addr_i),
        .debug_mem_addr_i (debug_mem_addr_i),
        .debug_reg_data_o (debug_reg_data_o),
        .debug_mem_data_o (debug_mem_data_o),
        .pc_o             (pc_o)
    );

    always #5 clk = ~clk;

    task load_instr(input [9:0] word_addr, input [31:0] data);
        begin
            ins_addr_i = {22'b0, word_addr[9:0]};
            instruction_i = data;
            ins_write_en_i = 1'b1;
            @(posedge clk);
            #1;
            ins_write_en_i = 1'b0;
        end
    endtask

    integer i;

    initial begin
        $display("=== Top-Level Pipeline Testbench ===");

        clk = 0;
        reset = 1;
        instruction_i = 0;
        ins_write_en_i = 0;
        ins_addr_i = 0;
        debug_reg_addr_i = 0;
        debug_mem_addr_i = 0;

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

        $display("--- Pipeline run: 20 cycles (debug x1 each cycle to catch WB) ---");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk); #1;
            $display("Cyc %2d | pc_o=%h | x1=%h (WB saw addi? when x1=0x2A)",
                i, pc_o, debug_reg_data_o);
        end

        $display("--- Inspect x1 via debug (should be 42 = 0x2A) ---");
        debug_reg_addr_i = 6'd1; #1;
        $display("  x1 = %h (exp 0x0000002A) %s",
            debug_reg_data_o, (debug_reg_data_o === 32'h0000_002A) ? "OK" : "FAIL");

        $display("--- Inspect x2 via debug (should be 100 = 0x64) ---");
        debug_reg_addr_i = 6'd2; #1;
        $display("  x2 = %h (exp 0x00000064) %s",
            debug_reg_data_o, (debug_reg_data_o === 32'h0000_0064) ? "OK" : "FAIL");

        $display("--- Inspect x3 via debug (lw: should be whatever data_mem[2] has) ---");
        debug_reg_addr_i = 6'd3; #1;
        $display("  x3 = %h", debug_reg_data_o);

        $display("--- Inspect x4 via debug (add x1+x2: should be 0x96 if forwarding works) ---");
        debug_reg_addr_i = 6'd4; #1;
        $display("  x4 = %h (exp 0x00000096 if forwarding; got %s)",
            debug_reg_data_o,
            (debug_reg_data_o === 32'h0000_0096) ? "OK (forwarding works)" :
            (debug_reg_data_o === 32'h0000_0000) ? "NO forward (stale x0)" : "other");

        $display("--- Cycle-by-cycle WB observation (read x4 each cycle) ---");
        debug_reg_addr_i = 6'd4;
        for (i = 0; i < 15; i = i + 1) begin
            @(posedge clk); #1;
            $display("  Cyc %2d | x4=%h | pc_o=%h", i, debug_reg_data_o, pc_o);
        end

        $display("--- End of top test ---");
        $finish;

        $display("--- End of top test ---");
        $finish;
    end

endmodule
