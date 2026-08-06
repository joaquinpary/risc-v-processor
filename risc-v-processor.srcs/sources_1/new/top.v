`timescale 1ns / 1ps

module top #(
    parameter BAUD_RATE = 9600,
    parameter FREQ      = 100000000 // 100 MHz
)(
    input  wire     clk,
    input  wire     reset,

    input  wire     rx_pin,
    output wire     tx_pin
);

    // =========================================================================
    // UART INTERFACE <--> DEBUG UNIT
    // =========================================================================
    wire    [39:0]  rx_data_40b;
    wire            rx_done_40b;
    wire    [39:0]  tx_data_40b;
    wire            tx_start_40b;
    wire            tx_busy;

    uart_interface #(
        .BAUD_RATE(BAUD_RATE),
        .FREQ(FREQ)
    ) u_uart_if (
        .clk            (clk),
        .reset          (reset),
        .rx_pin_i       (rx_pin),
        .tx_pin_o       (tx_pin),
        .rx_data_40b_o  (rx_data_40b),
        .rx_done_40b_o  (rx_done_40b),
        .tx_data_40b_i  (tx_data_40b),
        .tx_start_40b_i (tx_start_40b),
        .tx_busy_o      (tx_busy)
    );

    // =========================================================================
    // DEBUG UNIT <--> PROCESSOR
    // =========================================================================
    wire            cpu_enable;
    wire            cpu_reset;
    wire            cpu_halted;
    
    wire            imem_we;
    wire    [31:0]  imem_addr;
    wire    [31:0]  imem_data;
    
    wire    [4:0]   debug_reg_addr;
    wire    [31:0]  debug_reg_data;
    
    wire    [31:0]  debug_mem_addr;
    wire    [31:0]  debug_mem_data;
    
    wire    [31:0]  debug_pc;
    
    wire    [7:0]   debug_latch_id;
    reg     [31:0]  debug_latch_data;

    debug_unit u_debug_unit (
        .clk              (clk),
        .reset            (reset),
        
        .rx_data_i        (rx_data_40b),
        .rx_done_i        (rx_done_40b),
        .tx_data_o        (tx_data_40b),
        .tx_start_o       (tx_start_40b),
        .tx_busy_i        (tx_busy),
        
        .cpu_enable_o     (cpu_enable),
        .cpu_reset_o      (cpu_reset),
        .cpu_halted_i     (cpu_halted),
        
        .imem_we_o        (imem_we),
        .imem_addr_o      (imem_addr),
        .imem_data_o      (imem_data),
        
        .debug_reg_addr_o (debug_reg_addr),
        .debug_reg_data_i (debug_reg_data),
        .debug_mem_addr_o (debug_mem_addr),
        .debug_mem_data_i (debug_mem_data),
        .debug_pc_i       (debug_pc),
        .debug_latch_id_o (debug_latch_id),
        .debug_latch_data_i(debug_latch_data)
    );

    wire pipeline_reset = reset | cpu_reset;

    // IF stage wires (outputs of instruction_fetch)
    wire    [31:0]  pc_if;
    wire    [31:0]  pc_plus_4_if;
    wire    [31:0]  instruction_if;
    wire    [31:0]  pc_branch_o_mem;
    wire            pc_src_mem;

    // IF/ID latch registers
    reg     [31:0]  pc_id;
    reg     [31:0]  pc_plus_4_id;
    reg     [31:0]  instruction_id;

    // ID stage wires (outputs of instruction_decode)
    wire    [4:0]   reg_d_wb;
    wire    [31:0]  reg_data_wb;
    wire            reg_write_wb;
    wire    [31:0]  pc_o_id;
    wire    [31:0]  pc_plus_4_o_id;
    wire    [9:0]   control_bus_o_id;
    wire    [31:0]  read_data_1_o_id;
    wire    [31:0]  read_data_2_o_id;
    wire    [31:0]  imm_gen_o_id;
    wire    [2:0]   funct3_o_id;
    wire            bit30_o_id;
    wire    [4:0]   rd_o_id;

    // ID/EX latch registers
    reg     [31:0]  pc_ex;
    reg     [31:0]  pc_plus_4_ex;
    reg     [31:0]  pc_branch_ex;
    reg     [9:0]   control_bus_ex;
    reg     [31:0]  read_data_1_ex;
    reg     [31:0]  read_data_2_ex;
    reg     [31:0]  imm_gen_ex;
    reg     [2:0]   funct3_ex;
    reg             bit30_ex;
    reg     [4:0]   rd_ex;

    // EX stage wires (outputs of execute)
    wire    [6:0]   control_o_ex;
    wire    [31:0]  pc_plus_4_o_ex;
    wire    [31:0]  pc_branch_o_ex;
    wire            zero_o_ex;
    wire    [31:0]  result_o_ex;
    wire    [31:0]  rs2_data_o_ex;
    wire    [2:0]   funct3_o_ex;
    wire    [4:0]   rd_o_ex;

    // EX/MEM latch registers
    reg     [31:0]  pc_plus_4_mem;
    reg     [31:0]  pc_branch_mem;
    reg     [6:0]   control_mem;
    reg             zero_mem;
    reg     [31:0]  result_mem;
    reg     [31:0]  rs2_data_mem;
    reg     [2:0]   funct3_mem;
    reg     [4:0]   rd_mem;

    // MEM stage wires (outputs of memory)
    wire    [2:0]   control_o_mem;
    wire    [31:0]  pc_plus_4_o_mem;
    wire    [31:0]  result_o_mem;
    wire    [31:0]  read_data_o_mem;
    wire    [31:0]  mem_addr_o_mem;
    wire    [4:0]   rd_o_mem;

    // MEM/WB latch registers
    reg     [2:0]   control_wb;
    reg     [31:0]  read_data_wb;
    reg     [31:0]  result_wb;
    reg     [31:0]  pc_plus_4_wb;
    reg     [4:0]   rd_wb;

    // ===== IF stage =====
    instruction_fetch u_if (
        .clk            (clk),
        .reset          (pipeline_reset),
        .pc_write_en_i  (cpu_enable),
        .pc_src_i       (pc_src_mem),
        .pc_branch_i    (pc_branch_o_mem),
        .ins_write_en_i (imem_we),
        .instruction_i  (imem_data),
        .mem_addr_i     (imem_addr),
        .pc_o           (pc_if),
        .pc_plus_4_o    (pc_plus_4_if),
        .instruction_o  (instruction_if)
    );

    assign debug_pc = pc_if;

    // =========================================================================
    // LATCH DEBUG
    // =========================================================================
    always @(*) begin
        case (debug_latch_id)
            // IF/ID
            8'd1:  debug_latch_data = pc_id;
            8'd2:  debug_latch_data = pc_plus_4_id;
            8'd3:  debug_latch_data = instruction_id;
            
            // ID/EX
            8'd4:  debug_latch_data = pc_ex;
            8'd5:  debug_latch_data = pc_plus_4_ex;
            8'd6:  debug_latch_data = pc_branch_ex;
            8'd7:  debug_latch_data = {22'b0, control_bus_ex}; // 10 bits
            8'd8:  debug_latch_data = read_data_1_ex;
            8'd9:  debug_latch_data = read_data_2_ex;
            8'd10: debug_latch_data = imm_gen_ex;
            8'd11: debug_latch_data = {29'b0, funct3_ex}; // 3 bits
            8'd12: debug_latch_data = {31'b0, bit30_ex}; // 1 bit
            8'd13: debug_latch_data = {27'b0, rd_ex}; // 5 bits
            
            // EX/MEM
            8'd14: debug_latch_data = pc_plus_4_mem;
            8'd15: debug_latch_data = pc_branch_mem;
            8'd16: debug_latch_data = {25'b0, control_mem}; // 7 bits
            8'd17: debug_latch_data = {31'b0, zero_mem}; // 1 bit
            8'd18: debug_latch_data = result_mem;
            8'd19: debug_latch_data = rs2_data_mem;
            8'd20: debug_latch_data = {29'b0, funct3_mem}; // 3 bits
            8'd21: debug_latch_data = {27'b0, rd_mem}; // 5 bits
            
            // MEM/WB
            8'd22: debug_latch_data = {29'b0, control_wb}; // 3 bits
            8'd23: debug_latch_data = read_data_wb;
            8'd24: debug_latch_data = result_wb;
            8'd25: debug_latch_data = pc_plus_4_wb;
            8'd26: debug_latch_data = {27'b0, rd_wb}; // 5 bits
            
            default: debug_latch_data = 32'h00000000;
        endcase
    end

    // ===== IF/ID latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            pc_id           <= 32'b0;
            pc_plus_4_id    <= 32'b0;
            instruction_id  <= 32'b0;
        end else if (cpu_enable) begin
            pc_id           <= pc_if;
            pc_plus_4_id    <= pc_plus_4_if;
            instruction_id  <= instruction_if;
        end
    end

    // ===== ID stage =====
    instruction_decode u_id (
        .clk             (clk),
        .reset           (pipeline_reset),
        .pc_i            (pc_id),
        .pc_plus_4_i     (pc_plus_4_id),
        .instruction_i   (instruction_id),
        .rd_i            (rd_wb),
        .reg_data_i      (reg_data_wb),
        .reg_write_i     (reg_write_wb),
        .debug_reg_addr_i({1'b0, debug_reg_addr}),
        .debug_reg_data_o(debug_reg_data),
        .pc_o            (pc_o_id),
        .pc_plus_4_o     (pc_plus_4_o_id),
        .control_bus_o   (control_bus_o_id),
        .read_data_1_o   (read_data_1_o_id),
        .read_data_2_o   (read_data_2_o_id),
        .imm_gen_o       (imm_gen_o_id),
        .funct3_o        (funct3_o_id),
        .bit30_o         (bit30_o_id),
        .rd_o            (rd_o_id)
    );

    // ===== ID/EX latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            pc_ex           <= 32'b0;
            pc_plus_4_ex    <= 32'b0;
            pc_branch_ex    <= 32'b0;
            control_bus_ex  <= 10'b0;
            read_data_1_ex  <= 32'b0;
            read_data_2_ex  <= 32'b0;
            imm_gen_ex      <= 32'b0;
            funct3_ex       <= 3'b0;
            bit30_ex        <= 1'b0;
            rd_ex           <= 5'b0;
        end else if (cpu_enable) begin
            pc_ex           <= pc_o_id;
            pc_plus_4_ex    <= pc_plus_4_o_id;
            pc_branch_ex    <= pc_branch_o_ex;
            control_bus_ex  <= control_bus_o_id;
            read_data_1_ex  <= read_data_1_o_id;
            read_data_2_ex  <= read_data_2_o_id;
            imm_gen_ex      <= imm_gen_o_id;
            funct3_ex       <= funct3_o_id;
            bit30_ex        <= bit30_o_id;
            rd_ex           <= rd_o_id;
        end
    end

    // ===== EX stage =====
    execute u_ex (
        .control_i      (control_bus_ex),
        .pc_i           (pc_ex),
        .pc_plus_4_i    (pc_plus_4_ex),
        .imm_gen_i      (imm_gen_ex),
        .rs1_data_i     (read_data_1_ex),
        .rs2_data_i     (read_data_2_ex),
        .funct3_i       (funct3_ex),
        .bit30_i        (bit30_ex),
        .rd_i           (rd_ex),
        .control_o      (control_o_ex),
        .pc_plus_4_o    (pc_plus_4_o_ex),
        .pc_branch_o    (pc_branch_o_ex),
        .zero_o         (zero_o_ex),
        .result_o       (result_o_ex),
        .rs2_data_o     (rs2_data_o_ex),
        .funct3_o       (funct3_o_ex),
        .rd_o           (rd_o_ex)
    );

    // ===== EX/MEM latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            pc_plus_4_mem   <= 32'b0;
            pc_branch_mem   <= 32'b0;
            control_mem     <= 7'b0;
            zero_mem        <= 1'b0;
            result_mem      <= 32'b0;
            rs2_data_mem    <= 32'b0;
            funct3_mem      <= 3'b0;
            rd_mem          <= 5'b0;
        end else if (cpu_enable) begin
            pc_plus_4_mem   <= pc_plus_4_o_ex;
            pc_branch_mem   <= pc_branch_o_ex;
            control_mem     <= control_o_ex;
            zero_mem        <= zero_o_ex;
            result_mem      <= result_o_ex;
            rs2_data_mem    <= rs2_data_o_ex;
            funct3_mem      <= funct3_o_ex;
            rd_mem          <= rd_o_ex;
        end
    end

    // ===== MEM stage =====
    memory u_mem (
        .clk           (clk),
        .reset         (pipeline_reset),
        .debug_addr_i  (debug_mem_addr[9:0]),
        .control_i     (control_mem),
        .pc_plus_4_i   (pc_plus_4_mem),
        .pc_branch_i   (pc_branch_mem),
        .zero_i        (zero_mem),
        .result_i      (result_mem),
        .data2_i       (rs2_data_mem),
        .funct3_i      (funct3_mem),
        .rd_i          (rd_mem),
        .control_o     (control_o_mem),
        .pc_plus_4_o   (pc_plus_4_o_mem),
        .pc_src_o      (pc_src_mem),
        .pc_branch_o   (pc_branch_o_mem),
        .result_o      (result_o_mem),
        .read_data_o   (read_data_o_mem),
        .mem_addr_o    (mem_addr_o_mem),
        .debug_data_o  (debug_mem_data),
        .rd_o          (rd_o_mem)
    );

    // ===== MEM/WB latch =====
    always @(posedge clk) begin
        if (pipeline_reset) begin
            control_wb      <= 3'b0;
            read_data_wb    <= 32'b0;
            result_wb       <= 32'b0;
            pc_plus_4_wb    <= 32'b0;
            rd_wb           <= 5'b0;
        end else if (cpu_enable) begin
            control_wb      <= control_o_mem;
            read_data_wb    <= read_data_o_mem;
            result_wb       <= result_o_mem;
            pc_plus_4_wb    <= pc_plus_4_o_mem;
            rd_wb           <= rd_o_mem;
        end
    end

    // ===== WB stage =====
    write_back u_wb (
        .control_i      (control_wb),
        .read_data_i    (read_data_wb),
        .result_i       (result_wb),
        .pc_plus_4_i    (pc_plus_4_wb),
        .rd_i           (rd_wb),
        .reg_write_o    (reg_write_wb),
        .write_data_o   (reg_data_wb),
        .rd_o           (reg_d_wb)
    );

    // Halt detection
    assign cpu_halted = (instruction_id == 32'b0 && pc_if > 32'h00000010);

endmodule
