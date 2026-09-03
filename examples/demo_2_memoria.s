# ============================================================
# DEMO 2 - lui y accesos a memoria de byte, media palabra y palabra
# Direcciones en BYTES: 0, 4, 8, 12...
# ============================================================
        lui   x5, 0xABCDE         # x5 = 0xABCDE000
        addi  x5, x5, 0x6F        # x5 = 0xABCDE06F

# --- Palabra completa ---
        sw    x5, 0(x0)           # mem[0] = 0xABCDE06F
        lw    x6, 0(x0)           # x6 = 0xABCDE06F

# --- Byte, con y sin signo ---
        sb    x5, 4(x0)           # escribe solo 0x6F
        lb    x7, 4(x0)           # x7 = 111    (con signo)
        lbu   x8, 4(x0)           # x8 = 111    (sin signo)

# --- Media palabra, con y sin signo ---
        sh    x5, 8(x0)           # escribe 0xE06F
        lh    x9, 8(x0)           # x9 = -8081  (con signo)
        lhu   x18, 8(x0)          # x18 = 57455  (sin signo)

# --- Un byte suelto en medio de una palabra ---
        addi  x28, x0, -1
        sb    x28, 13(x0)         # solo el byte 1 de la palabra 3
        lb    x19, 13(x0)         # x19 = -1
        lbu   x20, 13(x0)         # x20 = 255
        lw    x21, 12(x0)         # x21 = 0x0000FF00  <-- los otros 3 bytes intactos

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
