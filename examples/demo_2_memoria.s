# ============================================================
# DEMO 2 - lui y accesos a memoria de byte, media palabra y palabra
# Direcciones en BYTES: 0, 4, 8, 12...
# ============================================================
        lui   t0, 0xABCDE           # t0 = 0xABCDE000
        addi  t0, t0, 0x6F          # t0 = 0xABCDE06F

# --- Palabra completa ---
        sw    t0, 0(zero)           # mem[0] = 0xABCDE06F
        lw    t1, 0(zero)           # t1 = 0xABCDE06F

# --- Byte, con y sin signo ---
        sb    t0, 4(zero)           # escribe solo 0x6F
        lb    t2, 4(zero)           # t2 = 111    (con signo)
        lbu   s0, 4(zero)           # s0 = 111    (sin signo)

# --- Media palabra, con y sin signo ---
        sh    t0, 8(zero)           # escribe 0xE06F
        lh    s1, 8(zero)           # s1 = -8081  (con signo)
        lhu   s2, 8(zero)           # s2 = 57455  (sin signo)

# --- Un byte suelto en medio de una palabra ---
        addi  t3, zero, -1
        sb    t3, 13(zero)          # solo el byte 1 de la palabra 3
        lb    s3, 13(zero)          # s3 = -1
        lbu   s4, 13(zero)          # s4 = 255
        lw    s5, 12(zero)          # s5 = 0x0000FF00  <-- los otros 3 bytes intactos

        nop
        nop
        nop
        nop

# Relleno hasta 28 palabras: asi todos los demos ocupan lo mismo
# y cargar uno sobre otro nunca deja instrucciones del anterior.
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
