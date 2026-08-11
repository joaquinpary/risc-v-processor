`timescale 1ns / 1ps

// =============================================================================
// forwarding_unit
//
// Pure combinational forwarding (bypass) unit for the EX stage.
// Compares the source registers of the instruction currently in EX against
// the destination registers of the older instructions still in flight
// (EX/MEM and MEM/WB) and selects the freshest value for each ALU operand.
//
// forward_a / forward_b encoding (3-to-1 mux selectors):
//   2'b00 -> no hazard : use the value read from the register file (ID/EX)
//   2'b10 -> EX  hazard: forward the result from the EX/MEM latch
//   2'b01 -> MEM hazard: forward the write-back value from the MEM/WB latch
//
// Priority: the if/else ordering gives EX/MEM priority over MEM/WB. This
// implements the "double data hazard" rule: when both in-flight instructions
// write the same register (e.g. add x1,...; add x1,...; add x2,x1,x1) the
// NEWEST result (EX/MEM) must win, so the MEM/WB branch is only reached when
// the EX/MEM stage is not already forwarding that register.
//
// x0 is never forwarded: it is hardwired to zero, so a write to x0 must not
// shortcut a read of x0.
// =============================================================================

module forwarding_unit(
    // Source registers of the instruction in EX (from the ID/EX latch)
    input wire  [4:0]   rs1_id_ex,
    input wire  [4:0]   rs2_id_ex,

    // Destination of the instruction in MEM (from the EX/MEM latch)
    input wire  [4:0]   rd_ex_mem,
    input wire          reg_write_ex_mem,

    // Destination of the instruction in WB (from the MEM/WB latch)
    input wire  [4:0]   rd_mem_wb,
    input wire          reg_write_mem_wb,

    // Selectors for the two 3-to-1 muxes in front of the ALU
    output reg  [1:0]   forward_a,
    output reg  [1:0]   forward_b
    );

    localparam [1:0] FWD_NONE   = 2'b00;   // register file value
    localparam [1:0] FWD_EX_MEM = 2'b10;   // shortcut from EX/MEM (EX hazard)
    localparam [1:0] FWD_MEM_WB = 2'b01;   // shortcut from MEM/WB (MEM hazard)

    always @(*) begin
        // ------------------- Operand A (rs1) -------------------
        if (reg_write_ex_mem && (rd_ex_mem != 5'd0)
                             && (rd_ex_mem == rs1_id_ex))
            forward_a = FWD_EX_MEM;
        else if (reg_write_mem_wb && (rd_mem_wb != 5'd0)
                                  && (rd_mem_wb == rs1_id_ex))
            forward_a = FWD_MEM_WB;
        else
            forward_a = FWD_NONE;

        // ------------------- Operand B (rs2) -------------------
        if (reg_write_ex_mem && (rd_ex_mem != 5'd0)
                             && (rd_ex_mem == rs2_id_ex))
            forward_b = FWD_EX_MEM;
        else if (reg_write_mem_wb && (rd_mem_wb != 5'd0)
                                  && (rd_mem_wb == rs2_id_ex))
            forward_b = FWD_MEM_WB;
        else
            forward_b = FWD_NONE;
    end

endmodule
