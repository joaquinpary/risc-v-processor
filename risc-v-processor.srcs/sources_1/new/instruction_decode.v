`timescale 1ns / 1ps

module instruction_decode(
    input wire          clk,
    input wire          reset,
    
    input wire  [31:0]  pc_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [31:0]  instruction_i,
    input wire  [4:0]   rd_i,
    input wire  [31:0]  reg_data_i,
    input wire          reg_write_i,
    input wire  [5:0]   debug_reg_addr_i,
    
    output wire [31:0]  debug_reg_data_o,
    output wire [31:0]  pc_o,
    output wire [31:0]  pc_plus_4_o,
    output wire [9:0]   control_bus_o,
    output wire [31:0]  read_data_1_o,
    output wire [31:0]  read_data_2_o,
    output wire [31:0]  imm_gen_o,
    output wire [2:0]   funct3_o,
    output wire         bit30_o,
    output wire [4:0]   rd_o,
    output wire [4:0]   rs1_o,
    output wire [4:0]   rs2_o
    );

    wire [6:0] opcode   = instruction_i[6:0];
    wire [2:0] funct3   = instruction_i[14:12];
    wire       bit30    = instruction_i[30];

    // -------------------------------------------------------------------
    // Registros fuente efectivos
    //
    // No todos los formatos usan esos campos como registro: en lui y jal los
    // bits 19:15 y 24:20 son parte del inmediato, y en los formatos tipo I el
    // campo rs2 tambien lo es. Si se los tratara como registros pasarian dos
    // cosas malas:
    //   - lui leeria un registro al azar y lo sumaria a su inmediato,
    //   - la unidad de forwarding podria adelantar un valor sobre esos bits.
    // Por eso se fuerzan a x0 cuando no son un registro de verdad, y se
    // exportan para que top.v use exactamente los mismos en el forwarding y en
    // la deteccion de riesgos.
    // -------------------------------------------------------------------
    wire uses_rs1 = (opcode != 7'b0110111)   // lui
                 && (opcode != 7'b1101111);  // jal

    wire uses_rs2 = (opcode == 7'b0110011)   // tipo R
                 || (opcode == 7'b0100011)   // stores
                 || (opcode == 7'b1100011);  // branches

    wire [4:0] rs1_addr = uses_rs1 ? instruction_i[19:15] : 5'd0;
    wire [4:0] rs2_addr = uses_rs2 ? instruction_i[24:20] : 5'd0;

    assign rs1_o = rs1_addr;
    assign rs2_o = rs2_addr;

    assign pc_o = pc_i;
    assign pc_plus_4_o = pc_plus_4_i;

    assign rd_o = instruction_i[11:7];
    assign funct3_o = funct3;
    assign bit30_o = bit30;
    
    register register (
        .clk        (clk),
        .reset      (reset),
        .reg_write  (reg_write_i),
        .rs1        (rs1_addr),
        .rs2        (rs2_addr),
        .rd         (rd_i),
        .write_data (reg_data_i),
        .debug_reg_addr_i(debug_reg_addr_i),
        .debug_reg_data_o(debug_reg_data_o),
        .read_data1 (read_data_1_o),
        .read_data2 (read_data_2_o)
    );

    control control (
        .opcode     (opcode),
        .control_bus(control_bus_o)
    );

    imm_gen imm_gen (
        .instruction(instruction_i),
        .imm_out    (imm_gen_o)
    );


endmodule
