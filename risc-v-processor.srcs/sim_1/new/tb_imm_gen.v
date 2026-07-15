`timescale 1ns / 1ps

module tb_imm_gen;

    reg  [31:0] instruction;
    wire [31:0] imm_out;

    imm_gen uut (
        .instruction(instruction),
        .imm_out(imm_out)
    );

    task show(input [255:0] label);
        begin
            #1;
            $display("%-25s | instr=%h | imm=%h", label, instruction, imm_out);
        end
    endtask

    initial begin
        $display("Time | imm_out");
        $display("--------------------------------------------");

        // I-type: addi x15, x0, 15  (opcode=0010011, imm=0x00F)
        instruction = 32'h00F_00793;
        show("I-type addi +15");

        // I-type: addi x15, x0, -1  (opcode=0010011, imm=0xFFF sign-ext)
        instruction = 32'hFFF_00793;
        show("I-type addi -1");

        // I-type: lw x5, 4(x10)  (opcode=0000011, imm=0x004)
        instruction = 32'h004_12503;
        show("I-type lw +4");

        // I-type: lw x5, -8(x10) (opcode=0000011, imm=0xFF8 sign-ext)
        instruction = 32'hFF8_12503;
        show("I-type lw -8");

        // S-type: sw x14, 8(x10)  (opcode=0100011, imm=0x008)
        instruction = 32'h008_12523;
        show("S-type sw +8");

        // S-type: sw x14, -4(x10) (opcode=0100011, imm=0xFFC sign-ext)
        instruction = 32'hFFC_12523;
        show("S-type sw -4");

        // B-type: beq x0, x0, +0  (opcode=1100011, imm=0x000)
        instruction = 32'h000_00463;
        show("B-type beq +0");

        // B-type: bne x5, x6, -8  (opcode=1100011, imm=0xFF8 sign-ext, LSB=0)
        instruction = 32'hFF5_2C2E3;
        show("B-type bne -8");

        // U-type: lui x10, 0x12345  (opcode=0110111, imm=0x12345000)
        instruction = 32'h12345_537;
        show("U-type lui 0x12345");

        // J-type: jal x1, +8  (opcode=1101111, imm=0x008, LSB=0)
        instruction = 32'h008_000EF;
        show("J-type jal +8");

        // J-type: jal x1, -4  (opcode=1101111, imm=0xFFFFFFFC sign-ext, LSB=0)
        instruction = 32'hFFC_FF0EF;
        show("J-type jal -4");

        // Opcode invalido (default)
        instruction = 32'hDEAD_BEEF;
        show("default");

        $finish;
    end

endmodule
