`timescale 1ns / 1ps

// =============================================================================
// tb_hazard_detection_unit
//
// Self-checking, EXHAUSTIVE testbench: sweeps the full input space
// (32 x 32 x 32 x 2 = 65,536 vectors) and compares the DUT against an
// independent reference model of the load-use hazard rule.
//
// Prints PASS/FAIL summary at the end. Run in Vivado: xsim tb_hazard_detection_unit
// =============================================================================

module tb_hazard_detection_unit;

    reg  [4:0]  rs1_if_id;
    reg  [4:0]  rs2_if_id;
    reg  [4:0]  rd_id_ex;
    reg         mem_read_id_ex;
    wire        pc_write;
    wire        if_id_write;
    wire        control_mux;

    integer errors;
    integer i1, i2, id, mr;
    reg     exp_stall;

    hazard_detection_unit uut (
        .rs1_if_id      (rs1_if_id),
        .rs2_if_id      (rs2_if_id),
        .rd_id_ex       (rd_id_ex),
        .mem_read_id_ex (mem_read_id_ex),
        .pc_write       (pc_write),
        .if_id_write    (if_id_write),
        .control_mux    (control_mux)
    );

    initial begin
        errors = 0;

        for (mr = 0; mr < 2; mr = mr + 1)
        for (id = 0; id < 32; id = id + 1)
        for (i1 = 0; i1 < 32; i1 = i1 + 1)
        for (i2 = 0; i2 < 32; i2 = i2 + 1) begin
            mem_read_id_ex = mr[0];
            rd_id_ex       = id[4:0];
            rs1_if_id      = i1[4:0];
            rs2_if_id      = i2[4:0];
            #1;

            // Reference: stall iff the load in EX writes a real register
            // that the instruction in ID reads
            exp_stall = (mr[0] == 1'b1) && (id != 0) && (id == i1 || id == i2);

            // pc_write / if_id_write active LOW, control_mux active HIGH
            if (pc_write    !== ~exp_stall ||
                if_id_write !== ~exp_stall ||
                control_mux !==  exp_stall) begin
                if (errors < 10)
                    $display("FAIL: rs1=%0d rs2=%0d rd_ex=%0d mem_read=%b -> pc_w=%b if_id_w=%b ctrl_mux=%b (exp stall=%b)",
                             rs1_if_id, rs2_if_id, rd_id_ex, mem_read_id_ex,
                             pc_write, if_id_write, control_mux, exp_stall);
                errors = errors + 1;
            end
        end

        if (errors == 0)
            $display("PASS: tb_hazard_detection_unit - 65536 vectors, 0 errors");
        else
            $display("FAIL: tb_hazard_detection_unit - %0d errors", errors);
        $finish;
    end

endmodule
