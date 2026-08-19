# ============================================================
# DEMO 4 - Riesgos de datos: adelantamiento (forwarding) y parada
# Cada instruccion usa el resultado de la anterior. Sin forwarding
# todos estos valores saldrian mal.
# ============================================================
        addi  t0, zero, 42          # t0 = 42
        addi  t1, zero, 100         # t1 = 100

# --- Cadena dependiente: forwarding EX/MEM y MEM/WB ---
        add   t2, t0, t1            # t2 = 142   <- adelanta los DOS operandos
        sub   s0, t2, t0            # s0 = 100   <- adelanta desde EX/MEM
        add   s1, s0, t2            # s1 = 242
        addi  a0, s1, 1             # a0 = 243

# --- Adelantamiento al dato de un store ---
        addi  a1, zero, 8
        sw    a1, 32(zero)          # mem[32] = 8   <- adelanta el dato

# --- LOAD-USE: aca el forwarding no alcanza, hay que FRENAR un ciclo ---
        lw    a2, 32(zero)          # a2 = 8
        add   a3, a2, t0            # a3 = 50    <- burbuja + adelantamiento
        add   a4, a3, a2            # a4 = 58

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
