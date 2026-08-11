# Programa de prueba de riesgos de datos.
# Ejercita forwarding EX/MEM, MEM/WB, dato de store y load-use.

        addi t0, zero, 42        # x5 = 42
        addi t1, zero, 100       # x6 = 100
        add  t2, t0, t1          # x7 = 142   <- forwarding de los dos
        sub  s0, t2, t0          # x8 = 100   <- forwarding EX/MEM
        add  s1, s0, t2          # x9 = 242
        addi a0, s1, 1           # x10 = 243
        addi a1, zero, 8         # x11 = 8
        sw   a1, 8(zero)         # mem[8] = 8 <- forwarding al dato del store
        lw   a2, 8(zero)         # x12 = 8
        add  a3, a2, t0          # x13 = 50   <- LOAD-USE: burbuja + forward
        add  a4, a3, a2          # x14 = 58
FIN:    beq  zero, zero, FIN     # loop infinito
