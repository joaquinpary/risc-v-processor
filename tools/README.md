# Dashboard de depuración (UART)

TUI para controlar el procesador RISC-V en la FPGA y ver el banco de registros.

## Instalación

```bash
cd tools
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python -m riscv_debug --port /dev/ttyUSB1      # Linux
python -m riscv_debug --port COM3              # Windows
```

Opciones: `--baud` (9600 por defecto, igual que el parámetro `BAUD_RATE` de
`top.v`) y `--timeout` (2 s).

En Linux, si da error de permisos: `sudo usermod -aG dialout $USER` y volver a
iniciar sesión.

## Cargar un programa

Opción **4** del menú: pide la ruta de un `.s`/`.asm` (lo ensambla) o un `.hex`
(lo lee directo), muestra una vista previa, y lo envía con barra de progreso.
Al terminar manda un RESET y deja el PC en 0.

```bash
python -m riscv_debug.riscv_assembler          # autotest del ensamblador
```

El ensamblador (`riscv_assembler.py`) soporta los formatos R/I/S/B/U/J de RV32I,
nombres de registro `x0`-`x31` y ABI (`zero`, `sp`, `t0`, `a0`…), inmediatos en
decimal/hex/binario con signo, comentarios `#` y `;`, etiquetas, y las
pseudo-instrucciones `nop`, `mv`, `li`, `j`, `jr`, `ret`.

Además **avisa qué instrucciones no ejecuta bien este procesador**: la ALU del TP
sólo implementa AND/OR/ADD/SUB, así que `sll`, `srl`, `slt`, `xor` y sus
variantes se codifican correctamente pero la FPGA las resuelve como AND. Lo
mismo con `bne` (la condición de salto sólo mira el flag zero), `lui` y los
saltos. Se codifican igual, pero conviene saberlo antes de depurar el hardware
equivocado.

Hay un programa de ejemplo en [`examples/hazards.s`](../examples/hazards.s) que
ejercita los cuatro casos de riesgo de datos.

## Protocolo

Tramas de **5 bytes** en ambos sentidos: 1 byte de comando + 4 bytes de payload
**big-endian** (MSB primero). El orden sale de `uart_interface.v`, que arma el
paquete de 40 bits desplazando cada byte recibido hacia la derecha.

| Comando | Valor | Payload | Respuesta |
|---|---|---|---|
| STEP | `0x01` | — | ninguna |
| RUN | `0x02` | — | ninguna |
| RESET | `0x03` | — | ninguna |
| LOAD_INSTR | `0x10` | instrucción | ninguna |
| REQ_REG | `0x20` | nº de registro | código = nº de registro (`0x00`–`0x1F`) |
| REQ_MEM | `0x30` | dirección | código `0x40` |
| REQ_PC | `0x40` | — | código `0x20` |
| REQ_LATCH | `0x50` | id de latch | código `0x30` |

> Estos valores salen de leer [debug_unit.v](../risc-v-processor.srcs/sources_1/new/debug_unit.v),
> **no** del enunciado del TP: ahí STEP y RUN figuran invertidos y REQ_REG como
> `0x03`. Si alguna vez cambia el firmware, se editan en `protocol.py`.

Que `REQ_REG` conteste con el número de registro como código es útil: sirve de
acuse de recibo. `link.py` lo valida y, si no coincide, tira `ProtocolError` y
vacía el buffer para no quedar desincronizado.

### Detalle importante sobre RUN

Mientras está en `RUNNING`, el `debug_unit` **no atiende la UART**: no hay
comando de pausa y no contesta ningún pedido hasta que `cpu_halted` lo devuelve
a `IDLE`. El dashboard aprovecha eso para detectar el fin: sondea con `REQ_PC` y
la primera respuesta significa "ya frenó" (`wait_until_halted()`).

## uart_doctor — diagnóstico del enlace

Cuando la placa deja de responder, `uart_doctor.py` sirve para ver qué pasa
byte por byte y para aislar qué comando rompe el enlace.

```bash
# Secuencia controlada: prueba de vida, barrido de 33 registros, y despues
# STEP / RESET / RUN uno por uno, con prueba de vida entre cada uno
python uart_doctor.py diagnose --port /dev/ttyUSB1

# Corre dashboard.py con todos los bytes trazados y decodificados
python uart_doctor.py trace-dashboard --port /dev/ttyUSB1

# Idem con el dashboard TUI
python uart_doctor.py trace-tui --port /dev/ttyUSB1
```

Todo queda además en `uart_doctor.log` con marcas de tiempo.

La traza parchea `serial.Serial`, así que instrumenta cualquier script que use
pyserial sin modificarlo (y le fuerza el `--port`, útil porque `dashboard.py`
lo tiene hardcodeado).

### Qué distingue el diagnóstico

Ante un fallo, `diagnose` manda bytes de relleno (1 a 4) y vuelve a probar.
Como la FPGA agrupa de a 5 sin reencuadre, eso separa dos causas que se ven
idénticas desde afuera:

| Síntoma | Causa | Solución |
|---|---|---|
| Se recupera con N bytes de relleno | La FPGA quedó **desalineada** | `link.realign()`, o el fix de reencuadre en el firmware |
| No se recupera con ningún relleno | La FSM está **colgada** (RUNNING esperando `cpu_halted`, o SEND_RESP esperando `tx_busy`) | Reprogramar la placa / reset físico |

Códigos de salida: `0` sobrevivió todo, `1` hubo fallos recuperables, `2` la
FPGA quedó colgada.

## Estructura

| Archivo | Responsabilidad |
|---|---|
| `protocol.py` | Constantes y (de)codificación de tramas. Sin E/S. |
| `link.py` | Puerto serie + API asíncrona (`DebugLink`). |
| `ui.py` | Renderizado con `rich`. Sin E/S. |
| `__main__.py` | Menú y bucle principal. |

`pyserial` es bloqueante, así que toda la E/S corre en threads vía
`asyncio.to_thread`, con un `asyncio.Lock` que serializa el acceso para que dos
comandos no intercalen sus tramas.

## Rendimiento

A 9600 baudios cada lectura de registro son 10 bytes (5 de ida + 5 de vuelta),
unos 8,3 ms. Refrescar los 32 registros + el PC tarda aproximadamente **280 ms**,
que es lo que se ve al llenarse la tabla después de cada STEP.
