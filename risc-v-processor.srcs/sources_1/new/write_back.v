`timescale 1ns / 1ps

module write_back(
    input wire  [2:0]   control_i,
    input wire  [31:0]  read_data_i,
    input wire  [31:0]  result_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [4:0]   rd_i,
    
    output wire         reg_write_o,
    output wire [31:0]  write_data_o,
    output wire [4:0]   rd_o
    );
    
    reg     [31:0]  write_data;
    wire    [1:0]   mem_to_reg = control_i[1:0];
    
    // MUX
    
    always @(*) begin
        case (mem_to_reg)
            2'b00:   write_data = result_i;
            2'b01:   write_data = read_data_i;
            2'b10:   write_data = pc_plus_4_i; 
            default: write_data = 32'b0;
        endcase
    end
            
    assign write_data_o = write_data;
    assign reg_write_o = control_i[2];
    assign rd_o = rd_i;
    
endmodule
