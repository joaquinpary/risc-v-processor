module alu (
    input wire  [31:0] data_a_i,
    input wire  [31:0] data_b_i,
    input wire  [3:0]  alu_control_i,
    output wire [31:0] result_o,
    output wire        zero_o
);

    reg [31:0]  result_aux;
    
    always @(*) begin
        case (alu_control_i)
            4'b0000: result_aux = data_a_i & data_b_i;
            4'b0001: result_aux = data_a_i | data_b_i;
            4'b0010: result_aux = data_a_i + data_b_i;
            4'b0110: result_aux = data_a_i - data_b_i;
            default: result_aux = 32'b0;
        endcase
    end
    
    assign result_o = result_aux;
    assign zero_o = (result_aux == 32'b0);

endmodule
