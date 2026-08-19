# ============================================================
# DEMO 1 - Unidad Aritmetico-Logica
# Las 10 operaciones del set, cada una con un resultado distinto
# para que no se puedan confundir entre si.
# ============================================================
        addi  t0, zero, 1           # t0 = 1
        addi  t1, zero, 8           # t1 = 8
        addi  t2, zero, -16         # t2 = -16

# --- Tipo R: registro con registro ---
        add   s0, t1, t0            # s0  = 9
        sub   s1, t1, t0            # s1  = 7
        and   s2, t1, t0            # s2  = 0
        or    s3, t1, t0            # s3  = 9
        xor   s4, t1, t0            # s4  = 9
        sll   s5, t1, t0            # s5  = 16      (8 << 1)
        srl   s6, t1, t0            # s6  = 4       (8 >> 1 logico)
        sra   s7, t2, t0            # s7  = -8      (-16 >> 1 aritmetico)
        slt   s8, t2, zero          # s8  = 1       (-16 < 0 con signo)
        sltu  s9, t2, zero          # s9  = 0       (sin signo NO es menor)

# --- Tipo I: registro con inmediato ---
        slli  s10, t1, 2            # s10 = 32
        srai  s11, t2, 2            # s11 = -4
        andi  a0, t1, 12            # a0  = 8
        ori   a1, t1, 1             # a1  = 9
        xori  a2, t1, 15            # a2  = 7
        slti  a3, t2, 0             # a3  = 1
        sltiu a4, t2, 0             # a4  = 0
        addi  a5, t0, -1            # a5  = 0   <-- suma con negativo, NO resta

        nop
        nop
        nop
        nop

# Relleno hasta 28 palabras: asi todos los demos ocupan lo mismo
# y cargar uno sobre otro nunca deja instrucciones del anterior.
        nop
        nop
        nop
