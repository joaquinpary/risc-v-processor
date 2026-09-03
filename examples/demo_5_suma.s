# ============================================================
# DEMO 5 - Programa completo: suma de un arreglo en memoria
# Guarda 5 numeros, los recorre con un puntero y los acumula.
# Junta todo: memoria, bucle, salto condicional y riesgo load-use.
# Resultado esperado: x10 = 150
# ============================================================

# --- Guardar el arreglo en las direcciones 64, 68, 72, 76, 80 ---
        addi  x5, x0, 10
        sw    x5, 64(x0)
        addi  x5, x0, 20
        sw    x5, 68(x0)
        addi  x5, x0, 30
        sw    x5, 72(x0)
        addi  x5, x0, 40
        sw    x5, 76(x0)
        addi  x5, x0, 50
        sw    x5, 80(x0)

# --- Recorrerlo y acumular ---
        addi  x10, x0, 0          # x10 = acumulador
        addi  x11, x0, 64         # x11 = puntero al arreglo
        addi  x12, x0, 5          # x12 = cuantos quedan

LOOP:   lw    x6, 0(x11)          # traer el elemento
        add   x10, x10, x6        # LOAD-USE: burbuja + adelantamiento
        addi  x11, x11, 4         # avanzar el puntero
        addi  x12, x12, -1        # descontar
        bne   x12, x0, LOOP       # volver si quedan

# --- x10 = 10+20+30+40+50 = 150 ---
        addi  x13, x0, 150        # valor de referencia
        sub   x14, x10, x13       # x14 = 0 si la suma dio bien

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
