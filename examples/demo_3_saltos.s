# ============================================================
# DEMO 3 - Riesgos de control: saltos, vaciado del pipeline y bucle
# Los registros que quedan en CERO son la prueba de que el vaciado
# funciona: esas instrucciones nunca se ejecutaron.
# ============================================================
        addi  x5, x0, 5
        addi  x6, x0, 5

# --- beq TOMADO: se saltea las dos siguientes ---
        beq   x5, x6, L1
        addi  x7, x0, 99          # NO debe ejecutarse -> x7 = 0
        addi  x28, x0, 88         # NO debe ejecutarse -> x28 = 0
L1:     addi  x8, x0, 7           # x8 = 7

# --- bne NO tomado: sigue de largo ---
        bne   x5, x6, L2
        addi  x9, x0, 1           # SI se ejecuta -> x9 = 1
L2:     addi  x18, x0, 3          # contador del bucle
        addi  x19, x0, 0          # acumulador

# --- Bucle con salto hacia atras, 3 vueltas ---
LOOP:   addi  x19, x19, 10
        addi  x18, x18, -1
        bne   x18, x0, LOOP       # x19 = 30 al salir
        addi  x20, x0, 4          # x20 = 4

# --- Salto incondicional ---
        j     FIN
        addi  x21, x0, 77         # NO debe ejecutarse -> x21 = 0
FIN:    addi  x22, x0, 1          # x22 = 1

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
