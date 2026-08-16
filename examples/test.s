# =========================================================
# TEST COMPLETO RV32I - Trabajo Final Arquitectura
# =========================================================

# --- FASE 1: Inicialización (Tipos U e I) ---
lui  x1, 0x00001        # x1 = 4096 (Prueba cargar en la parte alta)
addi x2, zero, 15       # x2 = 15 
addi x3, zero, 10       # x3 = 10 

# --- FASE 2: Aritmética y Lógica (Tipo R) ---
add  x4, x2, x3         # x4 = 25 (Suma básica)
sub  x5, x2, x3         # x5 = 5  (Resta básica)
and  x6, x2, x3         # x6 = 10 (15 & 10)
or   x7, x2, x3         # x7 = 15 (15 | 10)
xor  x8, x2, x3         # x8 = 5  (15 ^ 10)

# --- FASE 3: Desplazamientos y Comparaciones (Tipo R) ---
# Usamos x5 (que vale 5) como cantidad a desplazar
sll  x9, x2, x5         # x9 = 480 (15 << 5)
srl  x10, x9, x5        # x10 = 15 (480 >> 5)

slt  x11, x3, x2        # x11 = 1  (¿10 es menor que 15? Sí)
sltu x12, x2, x3        # x12 = 0  (¿15 es menor que 10? No)

# --- FASE 4: Memoria y Byte Enables (Tipos S y L) ---
# Para no complicar el direccionamiento, guardamos cerca de la dirección 20
addi x13, zero, -1      # x13 = 0xFFFFFFFF (Bits todos en 1)
sw   x13, 20(zero)      # mem[20:23] = 0xFFFFFFFF (Store Word completo)

addi x14, zero, 0xAA    # x14 = 170 (Un solo byte)
sb   x14, 24(zero)      # mem[24] = 0xAA (Prueba el Store Byte / wea[0])

addi x15, zero, 0x77    # x15 = 119
sh   x15, 28(zero)      # mem[28:29] = 0x0077 (Prueba el Store Half / wea[1:0])

lw   x16, 20(zero)      # x16 = 0xFFFFFFFF (Prueba si lee bien de RAM)

# --- FASE 5: Saltos Condicionales y Flush (Tipo B) ---
beq  x2, x2, SALTO_1    # 15 == 15 -> DEBE SALTAR (Hace flush de la sig.)
addi x31, zero, 999     # ERROR: Si x31 vale 999, falló el Flush del BEQ!

SALTO_1:
bne  x2, x3, SALTO_2    # 15 != 10 -> DEBE SALTAR
addi x31, zero, 999     # ERROR: Si x31 vale 999, falló el Flush del BNE!

SALTO_2:
# --- FASE 6: Saltos y Subrutinas (Tipos J) ---
jal  x20, FUNCION       # Salta a FUNCION y guarda la dirección de retorno en x20
    
# Cuando la subrutina termine, el programa debe regresar JUSTO AQUÍ.
# x20 debería tener el valor del PC de esta misma línea.
beq  zero, zero, FIN    # Si todo salió bien, salta al bucle infinito final

# --- SUBRUTINA (Simulando una llamada a función) ---
FUNCION:
addi x17, zero, 42      # x17 = 42 (Si x17 tiene 42, el JAL funcionó)
jalr zero, 0(x20)       # Salta a la dirección guardada en x20. ¡Retorno exitoso!
addi x31, zero, 999     # ERROR: Si x31 vale 999, falló el Flush del JALR!

# --- FIN DEL PROGRAMA ---
FIN: 
beq  zero, zero, FIN    # Bucle infinito (Atrapa al procesador aquí)
