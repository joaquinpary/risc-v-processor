`timescale 1ns / 1ps

module debug_unit(
    input  wire        clk,
    input  wire        reset,
    
    // Connection with uart_interface
    input  wire [39:0] rx_data_i,
    input  wire        rx_done_i,
    output wire [39:0] tx_data_o,
    output wire        tx_start_o,
    input  wire        tx_busy_i,
    
    // Processor Control
    output wire        cpu_enable_o,
    output wire        cpu_reset_o,
    input  wire        cpu_halted_i,
    
    // WRITE: Instruction Memory (Code loading)
    output wire        imem_we_o,
    output wire [31:0] imem_addr_o,
    output wire [31:0] imem_data_o,
    
    // READ: Register Bank (Debug Port)
    output wire [4:0]  debug_reg_addr_o,
    input  wire [31:0] debug_reg_data_i,
    
    // READ: Data Memory (RAM Port B)
    output wire [31:0] debug_mem_addr_o,
    input  wire [31:0] debug_mem_data_i,
    
    // READ: Current Program Counter
    input  wire [31:0] debug_pc_i,
    
    // READ: Pipeline Latches
    output wire [7:0]  debug_latch_id_o,
    input  wire [31:0] debug_latch_data_i
);

    // =========================================================
    // Breakdown of the packet received from the PC
    // =========================================================
    wire [7:0]  cmd     = rx_data_i[39:32];
    wire [31:0] payload = rx_data_i[31:0];

    // Connect the combinational address wires to the payload.
    // As soon as the command arrives, the address is already traveling to the memories.
    assign imem_data_o      = payload;
    assign debug_reg_addr_o = payload[4:0];
    assign debug_mem_addr_o = payload;
    assign debug_latch_id_o = payload[7:0];

    // Internal registers for output signals
    reg [39:0] tx_data_reg;
    reg        tx_start_reg;
    reg        cpu_enable_reg;
    reg        cpu_reset_reg;
    reg        imem_we_reg;
    reg [31:0] imem_addr_reg;

    assign tx_data_o    = tx_data_reg;
    assign tx_start_o   = tx_start_reg;
    assign cpu_enable_o = cpu_enable_reg;
    assign cpu_reset_o  = cpu_reset_reg;
    assign imem_we_o    = imem_we_reg;
    assign imem_addr_o  = imem_addr_reg;

    // =========================================================
    // State Machine (Main Controller)
    // =========================================================
    localparam IDLE       = 2'd0;
    localparam RUNNING    = 2'd1;
    localparam SEND_RESP  = 2'd2;
    
    reg [1:0] state;
    
    // Auxiliary registers to build the response to the PC
    reg [7:0] resp_cmd_aux;
    reg [2:0] req_type; // Multiplexer: 1=Reg, 2=Mem, 3=PC, 4=Latches

    always @(posedge clk) begin
        if (reset) begin
            state          <= IDLE;
            cpu_enable_reg <= 1'b0;
            cpu_reset_reg  <= 1'b0;
            imem_we_reg    <= 1'b0;
            tx_start_reg   <= 1'b0;
            imem_addr_reg  <= 32'b0;
            req_type       <= 3'd0;
        end else begin
            // Default values
            imem_we_reg   <= 1'b0;
            cpu_reset_reg <= 1'b0;
            
            case (state)
                IDLE: begin
                    cpu_enable_reg <= 1'b0; // Processor paused
                    tx_start_reg   <= 1'b0;
                    
                    if (rx_done_i) begin
                        case (cmd)
                            // ---------------------------------------------
                            // ACTION COMMANDS (Processor / PC -> FPGA)
                            // ---------------------------------------------
                            8'h01: cpu_enable_reg <= 1'b1; // STEP (1 clock cycle)
                            
                            8'h02: state <= RUNNING;     // RUN
                            
                            8'h03: begin                 // RESET
                                cpu_reset_reg <= 1'b1;
                                imem_addr_reg <= 32'b0;
                            end
                            
                            8'h10: begin                 // LOAD_INSTR
                                imem_we_reg   <= 1'b1;
                                imem_addr_reg <= imem_addr_reg + 4;
                            end
                            
                            // ---------------------------------------------
                            // READ COMMANDS (Prepare sending to PC)
                            // ---------------------------------------------
                            8'h20: begin // REQ_REG
                                // The PC tells us which register it wants, and we respond
                                // using that same number as the return "Cmd" (0x00 to 0x1F)
                                resp_cmd_aux <= payload[7:0];
                                req_type     <= 3'd1;
                                state        <= SEND_RESP;
                            end
                            
                            8'h30: begin // REQ_MEM
                                resp_cmd_aux <= 8'h40; // Table: Respond Mem with 0x40
                                req_type     <= 3'd2;
                                state        <= SEND_RESP;
                            end
                            
                            8'h40: begin // REQ_PC
                                resp_cmd_aux <= 8'h20; // Table: Respond PC with 0x20
                                req_type     <= 3'd3;
                                state        <= SEND_RESP;
                            end
                            
                            8'h50: begin // REQ_LATCH
                                resp_cmd_aux <= 8'h30;
                                req_type     <= 3'd4;
                                state        <= SEND_RESP;
                            end
                            
                            default: begin
                            end
                        endcase
                    end
                end
                
                RUNNING: begin
                    cpu_enable_reg <= 1'b1;
                    if (cpu_halted_i) begin
                        state <= IDLE;
                    end
                end
                
                SEND_RESP: begin
                    if (!tx_busy_i && !tx_start_reg) begin
                        case (req_type)
                            3'd1: tx_data_reg <= {resp_cmd_aux, debug_reg_data_i};
                            3'd2: tx_data_reg <= {resp_cmd_aux, debug_mem_data_i};
                            3'd3: tx_data_reg <= {resp_cmd_aux, debug_pc_i};
                            3'd4: tx_data_reg <= {resp_cmd_aux, debug_latch_data_i};
                            default: tx_data_reg <= {resp_cmd_aux, 32'h0};
                        endcase
                        
                        tx_start_reg <= 1'b1;
                    end
                    else if (tx_start_reg) begin
                        tx_start_reg <= 1'b0;
                        state        <= IDLE;
                    end
                end
            endcase
        end
    end

endmodule