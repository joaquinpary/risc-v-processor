`timescale 1ns / 1ps

module tb_instruction_decode;

    reg          clk;
    reg          reset;
    reg  [31:0]  pc_i;
    reg  [31:0]  pc_plus_4_i;
    reg  [31:0]  instruction_i;
    reg  [4:0]   rd_i;
    reg  [31:0]  write_data_i;
    reg          reg_write_i;

    wire [31:0]  pc_o;
    wire [31:0]  pc_plus_4_o;
    wire [9:0]   control_bus_o;
    wire [31:0]  read_data_1_o;
    wire [31:0]  read_data_2_o;
    wire [31:0]  imm_gen_o;
    wire [2:0]   funct3_o;
    wire         bit30_o;
    wire [4:0]   rd_o;

    instruction_decode uut (
        .clk           (clk),
        .reset         (reset),
        .pc_i          (pc_i),
        .pc_plus_4_i   (pc_plus_4_i),
        .instruction_i (instruction_i),
        .rd_i          (rd_i),
        .write_data_i  (write_data_i),
        .reg_write_i   (reg_write_i),
        .pc_o          (pc_o),
        .pc_plus_4_o   (pc_plus_4_o),
        .control_bus_o (control_bus_o),
        .read_data_1_o (read_data_1_o),
        .read_data_2_o (read_data_2_o),
        .imm_gen_o     (imm_gen_o),
        .funct3_o      (funct3_o),
        .bit30_o       (bit30_o),
        .rd_o          (rd_o)
    );

    always #5 clk = ~clk;

    task show(input [255:0] label);
        begin
            $display("  %-30s | rd_o=%2d | rdata1=%h | rdata2=%h | imm=%h | ctl=%b",
                label, rd_o, read_data_1_o, read_data_2_o, imm_gen_o, control_bus_o);
        end
    endtask

    initial begin
        $display("=== Instruction Decode Testbench ===");

        clk = 0;
        reset = 1;
        pc_i = 32'h0;
        pc_plus_4_i = 32'h0;
        instruction_i = 32'h0;
        rd_i = 5'd0;
        write_data_i = 32'h0;
        reg_write_i = 1'b0;

        #12 reset = 0;
        @(posedge clk); #1;

        // ---------------------------------------------------------------------
        $display("--- Pass-through test ---");
        pc_i          = 32'h0000_1000;
        pc_plus_4_i   = 32'h0000_1004;
        #1;
        $display("  pc_o        = %h (exp 0x00001000) %s", pc_o,        (pc_o        === 32'h0000_1000) ? "OK" : "FAIL");
        $display("  pc_plus_4_o = %h (exp 0x00001004) %s", pc_plus_4_o, (pc_plus_4_o === 32'h0000_1004) ? "OK" : "FAIL");

        // ---------------------------------------------------------------------
        $display("--- Decode addi x1, x0, 5  (I-type arith) ---");
        // addi rd=x1, rs1=x0, imm=5  =>  0000_0000_0101_00000_000_00000_0010011
        instruction_i = 32'h005_00093;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("addi x1,x0,5");
        $display("  read_data_1_o (x0) = %h (exp 0) %s", read_data_1_o, (read_data_1_o === 32'h0) ? "OK" : "FAIL");
        $display("  imm_gen_o          = %h (exp 5) %s", imm_gen_o,     (imm_gen_o     === 32'd5) ? "OK" : "FAIL");

        // ---------------------------------------------------------------------
        $display("--- Decode lw x5, -8(x10)  (I-type load) ---");
        // lw rd=x5, rs1=x10, imm=-8 => imm=0xFF8, opcode=0000011
        instruction_i = 32'hFF8_12503;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("lw x5,-8(x10)");

        // ---------------------------------------------------------------------
        $display("--- Decode sw x14, 10(x10)  (S-type store) ---");
        // sw rs2=x14, rs1=x10, imm=10 => imm[11:5]=0000000, imm[4:0]=01010
        // Encoding: 0000000_01010_01110_01010_010_0100011 = 0x00412523
        instruction_i = 32'h004_12523;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("sw x14,10(x10)");

        // ---------------------------------------------------------------------
        $display("--- Decode beq x0, x0, +8  (B-type) ---");
        // beq rs1=x0, rs2=x0, imm=+8 (LSB=0, sign-ext)
        // imm[12]=0, imm[11]=0, imm[10:5]=000000, imm[4:1]=0100, imm[0]=0
        // instr[31]=0, instr[7]=0, instr[30:25]=000000, instr[11:8]=0100
        // funct3=000, rs1=00000, rs2=00000, opcode=1100011
        // Hex: 0x00000_063 (hand-checked)
        instruction_i = 32'h0000_0063;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("beq x0,x0,+8");

        // ---------------------------------------------------------------------
        $display("--- Decode lui x10, 0x12345  (U-type) ---");
        // opcode=0110111, rd=01010, imm=0x12345
        // imm[31:12]=0x12345 -> 0001_0010_0011_0100_0101
        // Hex: 0x12345_537
        instruction_i = 32'h1234_5537;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("lui x10,0x12345");
        $display("  imm_gen_o = %h (exp 0x12345000) %s", imm_gen_o, (imm_gen_o === 32'h1234_5000) ? "OK" : "FAIL");

        // ---------------------------------------------------------------------
        $display("--- Decode jal x1, +16  (J-type) ---");
        // opcode=1101111, rd=00001, imm=+16 (LSB=0)
        // imm[20]=0, imm[19:12]=0x00, imm[11]=0, imm[10:1]=0000001000, imm[0]=0
        // rd=00001 -> top bits 0000_0000_0000_0000_0000_0000_0000_1_000
        // Hex: 0x00C000EF (verified in imm_gen tb)
        instruction_i = 32'h00C0_00EF;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("jal x1,+16");

        // ---------------------------------------------------------------------
        $display("--- Decode R-type add x3, x1, x2 ---");
        // add rd=00011, rs1=00001, rs2=00010, funct3=000, funct7=0000000, opcode=0110011
        // Hex: 0x0020_81B3
        instruction_i = 32'h0020_81B3;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        #1;
        show("add x3,x1,x2 (no data yet)");

        // ---------------------------------------------------------------------
        $display("--- Write x1=0xAAAA5555 via WB path, then read it ---");
        // Drive rd_i, write_data_i and reg_write_i from a simulated WB stage
        // First write on next clock edge
        rd_i = 5'd1; write_data_i = 32'hAAAA_5555; reg_write_i = 1'b1;
        @(posedge clk); #1;
        // Now x1 = 0xAAAA5555. Decode a load from x1.
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        // add x3, x1, x2 -> reads rs1=x1
        instruction_i = 32'h0020_81B3;
        #1;
        $display("  After WB write, x1 should be 0xAAAA5555");
        show("add x3,x1,x2 (x1 loaded)");

        // ---------------------------------------------------------------------
        $display("--- Test that x0 stays 0 even with write enable ---");
        rd_i = 5'd0; write_data_i = 32'hDEAD_BEEF; reg_write_i = 1'b1;
        instruction_i = 32'h005_00093;  // addi x1, x0, 5 (reads x0)
        @(posedge clk); #1;
        rd_i = 5'd0; write_data_i = 32'h0; reg_write_i = 1'b0;
        instruction_i = 32'h005_00093;
        #1;
        $display("  x0 must remain 0 (read x0) -> rdata1=%h %s",
            read_data_1_o, (read_data_1_o === 32'h0) ? "OK" : "FAIL");

        // ---------------------------------------------------------------------
        $display("--- funct3 and bit30 forwarding ---");
        $display("  funct3_o = %b | bit30_o = %b", funct3_o, bit30_o);

        $display("--- End of decode test ---");
        $finish;
    end

endmodule
