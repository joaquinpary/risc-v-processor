`timescale 1ns / 1ps

// =============================================================================
// hazard_detection_unit
//
// Pure combinational detector for the load-use data hazard.
//
// A load (lw/lh/lb) produces its value at the end of MEM, so an instruction
// in ID that reads the load's destination register cannot be fixed with
// forwarding alone: the pipeline must stall for exactly one cycle. After the
// stall the value is forwarded from MEM/WB by the forwarding_unit.
//
// Condition: the instruction in EX is a load (mem_read_id_ex) and its rd
// matches rs1 or rs2 of the instruction sitting in ID (IF/ID latch).
// rd == x0 is ignored (a load to x0 writes nothing).
//
// Outputs on a hazard:
//   pc_write    = 0 (ACTIVE LOW)  -> freeze the PC (refetch same address)
//   if_id_write = 0 (ACTIVE LOW)  -> freeze the IF/ID latch (hold instruction)
//   control_mux = 1 (ACTIVE HIGH) -> zero the control bus entering ID/EX
//                                    (inserts a bubble / NOP in EX)
//
// Note: this compares the rs1/rs2 FIELDS of the instruction in ID without
// decoding whether the instruction actually uses them (e.g. lui/jal encode
// immediate bits there). A false match only costs one unnecessary stall
// cycle, never correctness. It can be refined later with an opcode decode.
// =============================================================================

module hazard_detection_unit(
    // Source register fields of the instruction in ID (from the IF/ID latch)
    input wire  [4:0]   rs1_if_id,
    input wire  [4:0]   rs2_if_id,

    // Destination and MemRead of the instruction in EX (from the ID/EX latch)
    input wire  [4:0]   rd_id_ex,
    input wire          mem_read_id_ex,

    output reg          pc_write,       // active low: 0 = freeze PC
    output reg          if_id_write,    // active low: 0 = freeze IF/ID
    output reg          control_mux     // active high: 1 = insert bubble
    );

    wire load_use_hazard = mem_read_id_ex
                         && (rd_id_ex != 5'd0)
                         && ((rd_id_ex == rs1_if_id) || (rd_id_ex == rs2_if_id));

    always @(*) begin
        if (load_use_hazard) begin
            pc_write    = 1'b0;     // stop fetching
            if_id_write = 1'b0;     // hold the dependent instruction in ID
            control_mux = 1'b1;     // the instruction in ID becomes a bubble in EX
        end else begin
            pc_write    = 1'b1;     // normal operation
            if_id_write = 1'b1;
            control_mux = 1'b0;
        end
    end

endmodule
