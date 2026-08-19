# ============================================================
# DEMO 5 - Programa completo: suma de un arreglo en memoria
# Guarda 5 numeros, los recorre con un puntero y los acumula.
# Junta todo: memoria, bucle, salto condicional y riesgo load-use.
# Resultado esperado: a0 = 150
# ============================================================

# --- Guardar el arreglo en las direcciones 64, 68, 72, 76, 80 ---
        addi  t0, zero, 10
        sw    t0, 64(zero)
        addi  t0, zero, 20
        sw    t0, 68(zero)
        addi  t0, zero, 30
        sw    t0, 72(zero)
        addi  t0, zero, 40
        sw    t0, 76(zero)
        addi  t0, zero, 50
        sw    t0, 80(zero)

# --- Recorrerlo y acumular ---
        addi  a0, zero, 0           # a0 = acumulador
        addi  a1, zero, 64          # a1 = puntero al arreglo
        addi  a2, zero, 5           # a2 = cuantos quedan

LOOP:   lw    t1, 0(a1)             # traer el elemento
        add   a0, a0, t1            # LOAD-USE: burbuja + adelantamiento
        addi  a1, a1, 4             # avanzar el puntero
        addi  a2, a2, -1            # descontar
        bne   a2, zero, LOOP        # volver si quedan

# --- a0 = 10+20+30+40+50 = 150 ---
        addi  a3, zero, 150         # valor de referencia
        sub   a4, a0, a3            # a4 = 0 si la suma dio bien

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
