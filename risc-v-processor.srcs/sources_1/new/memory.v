`timescale 1ns / 1ps

module memory(
    input wire          clk,
    input wire          reset,
    input wire          enable_i,
    
    input wire  [9:0]   debug_addr_i,
    input wire  [6:0]   control_i,
    input wire  [31:0]  pc_plus_4_i,
    input wire  [31:0]  pc_branch_i,
    input wire          zero_i,
    input wire  [31:0]  result_i,
    input wire  [31:0]  data2_i,
    input wire  [2:0]   funct3_i,
    input wire  [4:0]   rd_i,
    
    output wire [2:0]   control_o,
    output wire [31:0]  pc_plus_4_o,
    output wire         pc_src_o,
    output wire [31:0]  pc_branch_o,
    output wire [31:0]  result_o,
    output wire [31:0]  read_data_o,
    output wire [31:0]  mem_addr_o,
    output wire [31:0]  debug_data_o,
    output wire [4:0]   rd_o
    );
    
    // -------------------------------------------------------------------
    // Direccionamiento
    //
    // La BRAM tiene 1024 palabras de 32 bits y addra es un indice de PALABRA,
    // pero result_i es una direccion de BYTE. Hay que separarla: los bits
    // [11:2] eligen la palabra y los [1:0] el byte dentro de ella.
    //
    // (Antes se usaba result_i[9:0] directo como indice de palabra. Para
    // accesos de palabra completa era consistente consigo mismo, pero saltaba
    // de a 4 posiciones y hacia imposible direccionar un byte suelto.)
    // -------------------------------------------------------------------
    wire    [9:0]   mem_addr   = result_i[11:2];
    wire    [1:0]   byte_off   = result_i[1:0];

    wire            mem_write = control_i[4];
    wire            mem_read = control_i[5];
    // control_i[6] (Branch), control_i[3] (Jump), zero_i y pc_branch_i ya no se
    // usan aca: la decision del salto se toma en EX.

    reg     [3:0]   size_mask;      // que bytes toca la instruccion, sin desplazar
    reg     [3:0]   byte_write_en;
    reg     [31:0]  write_data;

    always @(*) begin
        case (funct3_i)
            3'b000:  size_mask = 4'b0001;   // sb
            3'b001:  size_mask = 4'b0011;   // sh
            3'b010:  size_mask = 4'b1111;   // sw
            default: size_mask = 4'b1111;
        endcase

        // La mascara y el dato se corren al carril que indica la direccion:
        // sin esto un sb siempre escribia el byte 0 sin importar el offset.
        byte_write_en = mem_write ? (size_mask << byte_off) : 4'b0000;
        write_data    = data2_i << (8 * byte_off);
    end
    
    // PCSrc
    //
    // La resolucion de saltos se movio a la etapa EX (ver top.v): alli se
    // decide con funct3, lo que permite soportar bne ademas de beq y baja la
    // penalidad de 4 ciclos a 3. (Son 3 y no 2 porque la etapa IF ocupa dos
    // ciclos por la latencia de la BRAM de instrucciones: ver
    // docs/pipeline-depth.md.) Dejar esta salida activa provocaria un segundo
    // redireccionamiento del PC, asi que se ata a cero.
    assign pc_src_o = 1'b0;
    
    // Data Memory
    
    data_memory data_memory(
        .addra(mem_addr),
        .clka(clk),
        .dina(write_data),
        .douta(read_data_o),
        .ena((mem_write | mem_read) & enable_i),
        .wea(byte_write_en),
        
        .addrb(debug_addr_i),
        .clkb(clk),
        .dinb(32'b0),
        .doutb(debug_data_o),
        .enb(1'b1),
        .web(4'b0000)
    );
    
    
    assign mem_addr_o = result_i;
    assign control_o = control_i[2:0];
    assign pc_plus_4_o = pc_plus_4_i;
    assign result_o = result_i;
    assign rd_o = rd_i;
    assign pc_branch_o = pc_branch_i;
    
endmodule
