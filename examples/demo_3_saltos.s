# ============================================================
# DEMO 3 - Riesgos de control: saltos, vaciado del pipeline y bucle
# Los registros que quedan en CERO son la prueba de que el vaciado
# funciona: esas instrucciones nunca se ejecutaron.
# ============================================================
        addi  t0, zero, 5
        addi  t1, zero, 5

# --- beq TOMADO: se saltea las dos siguientes ---
        beq   t0, t1, L1
        addi  t2, zero, 99          # NO debe ejecutarse -> t2 = 0
        addi  t3, zero, 88          # NO debe ejecutarse -> t3 = 0
L1:     addi  s0, zero, 7           # s0 = 7

# --- bne NO tomado: sigue de largo ---
        bne   t0, t1, L2
        addi  s1, zero, 1           # SI se ejecuta -> s1 = 1
L2:     addi  s2, zero, 3           # contador del bucle
        addi  s3, zero, 0           # acumulador

# --- Bucle con salto hacia atras, 3 vueltas ---
LOOP:   addi  s3, s3, 10
        addi  s2, s2, -1
        bne   s2, zero, LOOP        # s3 = 30 al salir
        addi  s4, zero, 4           # s4 = 4

# --- Salto incondicional ---
        j     FIN
        addi  s5, zero, 77          # NO debe ejecutarse -> s5 = 0
FIN:    addi  s6, zero, 1           # s6 = 1

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
