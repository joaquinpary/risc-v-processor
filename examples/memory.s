# ==============================================================================
# TEST DE CARGAS DESDE MEMORIA (Loads RV32I)
# Lee los datos guardados en la corrida previa:
#   - Dirección 20: 0xFFFFFFFF (sw)
#   - Dirección 24: 0x000000AA (sb) -> Byte: 0xAA (-86 sign-extended / 170 unsigned)
#   - Dirección 28: 0x00000077 (sh) -> Half: 0x0077 (+119)
# ==============================================================================

# --- FASE 1: Cargas de Memoria en las primeras instrucciones ---
lw   x1, 20(zero)       # x1  = 0xFFFFFFFF (-1) [Carga la palabra completa]
lb   x2, 24(zero)       # x2  = 0xFFFFFFAA (-86) [Load Byte con extensión de signo]
lbu  x3, 24(zero)       # x3  = 0x000000AA (170) [Load Byte Unsigned con ceros]
lh   x4, 28(zero)       # x4  = 0x00000077 (119) [Load Halfword con signo]
lhu  x5, 28(zero)       # x5  = 0x00000077 (119) [Load Halfword Unsigned]

# --- FASE 2: Operaciones con los datos cargados (Comprueba extensión de signo) ---
# Suma el byte sin signo (170) con el halfword (119)
add  x6, x3, x4         # x6  = 170 + 119 = 289 (0x121)

# Comprueba la diferencia entre lb con signo (-86) y lbu sin signo (170)
sub  x7, x3, x2         # x7  = 170 - (-86) = 256 (0x100)

# Operación lógica sobre el valor de 32 bits cargado
andi x8, x1, 0x0F       # x8  = 0xFFFFFFFF & 0x0F = 15 (0xF)

# Comparaciones de magnitudes (slt vs sltu)
slt  x9, x2, x3         # x9  = 1 (¿-86 < 170? Sí, con signo)
sltu x10, x2, x3        # x10 = 0 (¿0xFFFFFFAA < 0x000000AA? No, sin signo)

# --- FASE 3: Comprobación con Salto Condicional ---
addi x11, zero, 289     # x11 = 289 (Valor de referencia esperado de x6)
beq  x6, x11, EXITO     # Si la suma de las lecturas dio 289, salta a EXITO
addi x31, zero, 999     # ERROR: Si x31 vale 999, falló la lectura o la suma

EXITO:
addi x12, zero, 1       # x12 = 1 (Indica que todas las cargas pasaron con éxito)

# --- FIN DEL PROGRAMA ---
FIN:
beq  zero, zero, FIN    # Bucle infinito
