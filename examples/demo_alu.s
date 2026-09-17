# ============================================================
# DEMO 1 - Unidad Aritmetico-Logica
# Las 10 operaciones del set, cada una con un resultado distinto
# para que no se puedan confundir entre si.
# ============================================================
        addi  x5, x0, 1           # x5 = 1
        addi  x6, x0, 8           # x6 = 8
        addi  x7, x0, -16         # x7 = -16

# --- Tipo R: registro con registro ---
        add   x8, x6, x5          # x8 = 9
        sub   x9, x6, x5          # x9 = 7
        and   x18, x6, x5         # x18 = 0
        or    x19, x6, x5         # x19 = 9
        xor   x20, x6, x5         # x20 = 9
        sll   x21, x6, x5         # x21 = 16      (8 << 1)
        srl   x22, x6, x5         # x22 = 4       (8 >> 1 logico)
        sra   x23, x7, x5         # x23 = -8      (-16 >> 1 aritmetico)
        slt   x24, x7, x0         # x24 = 1       (-16 < 0 con signo)
        sltu  x25, x7, x0         # x25 = 0       (sin signo NO es menor)

# --- Tipo I: registro con inmediato ---
        slli  x26, x6, 2          # x26 = 32
        srai  x27, x7, 2          # x27 = -4
        andi  x10, x6, 12         # x10 = 8
        ori   x11, x6, 1          # x11 = 9
        xori  x12, x6, 15         # x12 = 7
        slti  x13, x7, 0          # x13 = 1
        sltiu x14, x7, 0          # x14 = 0
        addi  x15, x5, -1         # x15 = 0   <-- suma con negativo, NO resta

        nop
        nop
        nop
        nop

# Relleno hasta 28 palabras: asi todos los demos ocupan lo mismo
# y cargar uno sobre otro nunca deja instrucciones del anterior.
        nop
        nop
        nop
