`timescale 1ns / 1ps

// =============================================================================
// tb_forwarding_unit
//
// Self-checking, EXHAUSTIVE testbench: sweeps the full input space
// (32 x 32 x 32 x 32 x 2 x 2 = 4,194,304 vectors) and compares the DUT
// against an independent reference model.
//
// Reference model: for each source register, forward from the YOUNGEST
// in-flight instruction that writes it (EX/MEM is younger than MEM/WB),
// never forward x0. Recomputed independently per source register; it kills
// the swapped-priority, swapped-encoding and missing-x0-guard mutants.
//
// Prints PASS/FAIL summary at the end. Run in Vivado: xsim tb_forwarding_unit
// =============================================================================

module tb_forwarding_unit;

    reg  [4:0]  rs1_id_ex;
    reg  [4:0]  rs2_id_ex;
    reg  [4:0]  rd_ex_mem;
    reg         reg_write_ex_mem;
    reg  [4:0]  rd_mem_wb;
    reg         reg_write_mem_wb;
    wire [1:0]  forward_a;
    wire [1:0]  forward_b;

    integer errors;
    integer vectors;
    integer i1, i2, im, iw, wm, ww;

    forwarding_unit uut (
        .rs1_id_ex        (rs1_id_ex),
        .rs2_id_ex        (rs2_id_ex),
        .rd_ex_mem        (rd_ex_mem),
        .reg_write_ex_mem (reg_write_ex_mem),
        .rd_mem_wb        (rd_mem_wb),
        .reg_write_mem_wb (reg_write_mem_wb),
        .forward_a        (forward_a),
        .forward_b        (forward_b)
    );

    // Reference: stage of the youngest in-flight producer of register rs
    function [1:0] expected_forward;
        input [4:0] rs;
        input [4:0] rd_m;
        input       rw_m;
        input [4:0] rd_w;
        input       rw_w;
        reg mem_produces, wb_produces;
        begin
            mem_produces = rw_m && (rd_m == rs) && (rs != 5'd0);
            wb_produces  = rw_w && (rd_w == rs) && (rs != 5'd0);
            if (mem_produces)                       // youngest producer wins
                expected_forward = 2'b10;           // (double data hazard rule)
            else if (wb_produces)
                expected_forward = 2'b01;
            else
                expected_forward = 2'b00;
        end
    endfunction

    task check;
        reg [1:0] exp_a, exp_b;
        begin
            exp_a = expected_forward(rs1_id_ex, rd_ex_mem, reg_write_ex_mem,
                                     rd_mem_wb, reg_write_mem_wb);
            exp_b = expected_forward(rs2_id_ex, rd_ex_mem, reg_write_ex_mem,
                                     rd_mem_wb, reg_write_mem_wb);
            if (forward_a !== exp_a || forward_b !== exp_b) begin
                if (errors < 10)
                    $display("FAIL: rs1=%0d rs2=%0d rd_m=%0d(w=%b) rd_w=%0d(w=%b) -> fwd_a=%b (exp %b) fwd_b=%b (exp %b)",
                             rs1_id_ex, rs2_id_ex,
                             rd_ex_mem, reg_write_ex_mem,
                             rd_mem_wb, reg_write_mem_wb,
                             forward_a, exp_a, forward_b, exp_b);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        errors  = 0;
        vectors = 0;

        // Full exhaustive sweep of the input space
        for (wm = 0; wm < 2; wm = wm + 1)
        for (ww = 0; ww < 2; ww = ww + 1)
        for (im = 0; im < 32; im = im + 1)
        for (iw = 0; iw < 32; iw = iw + 1)
        for (i1 = 0; i1 < 32; i1 = i1 + 1)
        for (i2 = 0; i2 < 32; i2 = i2 + 1) begin
            reg_write_ex_mem = wm[0];
            reg_write_mem_wb = ww[0];
            rd_ex_mem        = im[4:0];
            rd_mem_wb        = iw[4:0];
            rs1_id_ex        = i1[4:0];
            rs2_id_ex        = i2[4:0];
            #1;
            check;
            vectors = vectors + 1;
        end

        if (errors == 0)
            $display("PASS: tb_forwarding_unit - %0d vectors, 0 errors", vectors);
        else
            $display("FAIL: tb_forwarding_unit - %0d errors in %0d vectors", errors, vectors);
        $finish;
    end

endmodule
