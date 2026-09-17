# Procesador RISC-V segmentado

Implementación en Verilog de un procesador RISC-V de 5 etapas (IF, ID, EX, MEM, WB)
con forwarding y detección de riesgos, más un dashboard de depuración por UART que
corre en la PC.

## Placa

| | |
|---|---|
| Placa | Digilent Arty A7-35T (`digilentinc.com:arty-a7-35:part0:1.1`) |
| FPGA | Xilinx Artix-7 XC7A35T |
| Reloj de entrada | Oscilador de 100 MHz en el pin `E3` |
| Reloj del CPU | 62 MHz, generados con un MMCM (Clock Wizard) |
| Reset | Botón `BTN0` (pin `D9`) |
| UART | 9600 baudios, 8N1, por el mismo cable USB (`tx_pin` = `D10`, `rx_pin` = `A9`) |

Las memorias de instrucciones y de datos son BRAM generadas con IP de Vivado.
La memoria de instrucciones tiene 1024 palabras, así que un programa no puede pasar
de 1024 instrucciones.

## Cómo correr el dashboard

El dashboard es una TUI en Python que se conecta por UART a la placa: permite cargar
un programa, avanzarlo ciclo a ciclo o de corrido, y ver los registros, el PC y los
latches del pipeline.

### 1. Programar la FPGA

Abrir `risc-v-processor.xpr` en Vivado, generar el bitstream y programar la placa
(Open Hardware Manager → Program Device). El proyecto está guardado con Vivado 2025.1.

### 2. Instalar las dependencias

```bash
cd tools
pip install -r requirements.txt
```

Hace falta Python 3.9 o superior. Las dependencias son `pyserial` y `rich`.

### 3. Conectarse

Desde el directorio `tools/`:

```bash
python -m riscv_debug --port /dev/ttyUSB1
```

En Windows el puerto es del estilo `COM3`. Si el puerto está mal, el programa
muestra la lista de los que sí detectó.

Opciones disponibles:

| Opción | Default | Qué hace |
|---|---|---|
| `--port`, `-p` | (obligatoria) | Puerto serie de la placa |
| `--baud`, `-b` | `9600` | Baudios, tiene que coincidir con el `BAUD_RATE` de `top.v` |
| `--timeout`, `-t` | `2.0` | Segundos de espera por respuesta |

En Linux, si el puerto da error de permisos:

```bash
sudo usermod -aG dialout $USER
```

y volver a iniciar sesión.

### 4. Usarlo

El menú del dashboard tiene estas opciones:

| Tecla | Acción |
|---|---|
| `1` | Step — avanza un ciclo de reloj |
| `2` | Run — corre libre hasta que el CPU se detiene |
| `3` | Reset — reinicia el CPU y deja el PC en 0 |
| `4` | Load program — ensambla un `.s` / `.asm` / `.hex` y lo carga en la placa |
| `5` | Refresh — vuelve a leer el PC y los 32 registros |
| `6` | Read memory — lee una palabra de la memoria de datos |
| `7` | Muestra u oculta el panel de latches del pipeline |
| `q` | Salir |

El flujo típico es: `4` para cargar un programa, después `1` para ir ciclo a ciclo
o `2` para dejarlo correr hasta el final.

El programa termina cuando el CPU llega a una instrucción nula (`32'b0`), que es lo
que activa `cpu_halted`. Los programas de ejemplo ya terminan así.

## Programas de ejemplo

La opción `4` del menú lista sola lo que hay en `examples/`:

| Archivo | Qué muestra |
|---|---|
| `demo_alu.s` | Las 10 operaciones de la ALU, cada una con un resultado distinto |
| `demo_memoria.s` | `lui` y accesos de byte, media palabra y palabra |
| `demo_saltos.s` | Riesgos de control: saltos, vaciado del pipeline y un bucle |
| `demo_riesgos.s` | Riesgos de datos: forwarding y parada por load-use |
| `demo.s` | Programa completo: suma de un arreglo en memoria (`x10` = 150) |

Cada archivo arranca con un comentario que explica qué resultado se espera en cada
registro, así que el dashboard sirve para verificarlo a simple vista.

## Estructura del repo

```
examples/                        programas de ejemplo en assembly
risc-v-processor.srcs/
  sources_1/new/                 módulos Verilog del procesador
  sources_1/ip/                  IP de Vivado (Clock Wizard, BRAMs)
  sim_1/new/                     testbenches
  constrs_1/                     constraints de la Arty A7-35T
tools/riscv_debug/               dashboard de depuración
```
