# jal aislado. jal en 0x00 -> ra debe ser 0x04, DEST en 0x08.
        jal  ra, DEST
        addi x20, zero, 77      # camino no tomado, NO debe ejecutarse
DEST:   addi x21, zero, 4
