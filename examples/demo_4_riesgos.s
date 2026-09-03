# ============================================================
# DEMO 4 - Riesgos de datos: adelantamiento (forwarding) y parada
# Cada instruccion usa el resultado de la anterior. Sin forwarding
# todos estos valores saldrian mal.
# ============================================================
        addi  x5, x0, 42          # x5 = 42
        addi  x6, x0, 100         # x6 = 100

# --- Cadena dependiente: forwarding EX/MEM y MEM/WB ---
        add   x7, x5, x6          # x7 = 142   <- adelanta los DOS operandos
        sub   x8, x7, x5          # x8 = 100   <- adelanta desde EX/MEM
        add   x9, x8, x7          # x9 = 242
        addi  x10, x9, 1          # x10 = 243

# --- Adelantamiento al dato de un store ---
        addi  x11, x0, 8
        sw    x11, 32(x0)         # mem[32] = 8   <- adelanta el dato

# --- LOAD-USE: aca el forwarding no alcanza, hay que FRENAR un ciclo ---
        lw    x12, 32(x0)         # x12 = 8
        add   x13, x12, x5        # x13 = 50    <- burbuja + adelantamiento
        add   x14, x13, x12       # x14 = 58

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
        nop
        nop
        nop
        nop
