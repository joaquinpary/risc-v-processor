`timescale 1ns / 1ps

// =============================================================================
// write_back
//
// Elige que se escribe en el banco de registros y, para las cargas, extrae el
// byte o la media palabra que corresponde.
//
// La extraccion va aca y no en memory.v porque la BRAM entrega el dato recien
// durante el ciclo WB. Los datos necesarios llegan por el latch MEM/WB:
// funct3_i dice el tamano y si extiende signo, y result_i es la direccion
// efectiva, asi que result_i[1:0] indica el byte dentro de la palabra.
// =============================================================================

module write_back(
    input wire  [2:0]   control_i,
    input wire  [2:0]   funct3_i,
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

    // ---------------------------------------------------------------
    // Extraccion del sub-word leido
    // ---------------------------------------------------------------
    wire    [1:0]   byte_off = result_i[1:0];

    // Se corre la palabra para dejar el dato pedido en la parte baja
    wire    [31:0]  aligned  = read_data_i >> (8 * byte_off);

    wire    [7:0]   byte_sel = aligned[7:0];
    wire    [15:0]  half_sel = aligned[15:0];

    reg     [31:0]  load_data;

    always @(*) begin
        case (funct3_i)
            // lb y lh extienden el signo; lbu y lhu rellenan con ceros
            3'b000:  load_data = {{24{byte_sel[7]}},  byte_sel};   // lb
            3'b001:  load_data = {{16{half_sel[15]}}, half_sel};   // lh
            3'b010:  load_data = read_data_i;                      // lw
            3'b100:  load_data = {24'b0, byte_sel};                // lbu
            3'b101:  load_data = {16'b0, half_sel};                // lhu
            default: load_data = read_data_i;
        endcase
    end

    // ---------------------------------------------------------------
    // MUX de escritura al banco de registros
    // ---------------------------------------------------------------
    always @(*) begin
        case (mem_to_reg)
            2'b00:   write_data = result_i;
            2'b01:   write_data = load_data;
            2'b10:   write_data = pc_plus_4_i;
            default: write_data = 32'b0;
        endcase
    end

    assign write_data_o = write_data;
    assign reg_write_o = control_i[2];
    assign rd_o = rd_i;

endmodule
