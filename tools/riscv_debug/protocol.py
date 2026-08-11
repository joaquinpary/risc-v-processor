"""
Protocolo UART del debug_unit — tramas de 5 bytes.

Formato (idéntico en ambos sentidos):

    byte 0   : comando / código de respuesta
    bytes 1-4: payload de 32 bits, big-endian (MSB primero)

El orden big-endian sale de uart_interface.v: en RX el buffer desplaza cada byte
recibido hacia la derecha (`rx_buffer <= {rx_buffer[31:0], rx_byte}`), así que el
primer byte queda en rx_data[39:32] = cmd; en TX se envía primero
`tx_buffer[39:32]`. O sea: comando primero, payload MSB primero.

IMPORTANTE: los opcodes de acá salen de leer debug_unit.v directamente, no del
enunciado del TP (que tiene STEP y RUN invertidos y REQ_REG en 0x03).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

#: Tamaño de trama en bytes (1 comando + 4 de payload).
FRAME_SIZE = 5

#: 1 byte sin signo + 1 entero de 32 bits big-endian.
_FRAME = struct.Struct(">BI")


class Command(IntEnum):
    """Comandos que la PC le manda a la FPGA (debug_unit.v, estado IDLE)."""

    STEP = 0x01        # avanza exactamente un ciclo de reloj
    RUN = 0x02         # ejecución libre hasta que cpu_halted se active
    RESET = 0x03       # reinicia la CPU y el puntero de carga de instrucciones
    LOAD_INSTR = 0x10  # escribe el payload como instrucción y autoincrementa
    REQ_REG = 0x20     # payload[4:0] = número de registro
    REQ_MEM = 0x30     # payload = dirección de memoria de datos
    REQ_PC = 0x40      # sin payload
    REQ_LATCH = 0x50   # payload[7:0] = id de latch del pipeline


class ResponseKind(IntEnum):
    """
    Códigos con que responde la FPGA.

    Para REQ_REG el debug_unit devuelve como código el propio número de registro
    (0x00..0x1F), así que el rango bajo no es una constante sino un registro.
    """

    PC = 0x20
    LATCH = 0x30
    MEM = 0x40


#: Código de respuesta máximo que corresponde a un registro (x0..x31).
MAX_REGISTER_CODE = 0x1F

#: Comandos que NO generan respuesta: el debug_unit los ejecuta y vuelve a IDLE.
ACTION_COMMANDS = frozenset(
    {Command.STEP, Command.RUN, Command.RESET, Command.LOAD_INSTR}
)

#: Nombres ABI de los 32 registros, para mostrarlos junto al número.
ABI_NAMES: tuple[str, ...] = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)

REGISTER_COUNT = 32


class ProtocolError(Exception):
    """Trama mal formada o respuesta que no corresponde a lo pedido."""


@dataclass(frozen=True, slots=True)
class Frame:
    """Una trama decodificada."""

    code: int
    payload: int

    @property
    def is_register(self) -> bool:
        """True si la respuesta es el valor de un registro (código = x0..x31)."""
        return self.code <= MAX_REGISTER_CODE

    def __str__(self) -> str:
        if self.is_register:
            return f"x{self.code}=0x{self.payload:08X}"
        try:
            name = ResponseKind(self.code).name
        except ValueError:
            name = f"0x{self.code:02X}"
        return f"{name}=0x{self.payload:08X}"


def encode(command: int, payload: int = 0) -> bytes:
    """
    Arma una trama de 5 bytes lista para mandar por el puerto serie.

    El payload se enmascara a 32 bits para que un valor negativo o demasiado
    grande no rompa el empaquetado.
    """
    return _FRAME.pack(int(command) & 0xFF, int(payload) & 0xFFFFFFFF)


def decode(raw: bytes) -> Frame:
    """Decodifica una trama de 5 bytes recibida desde la FPGA."""
    if len(raw) != FRAME_SIZE:
        raise ProtocolError(
            f"Se esperaban {FRAME_SIZE} bytes y llegaron {len(raw)}: {raw!r}"
        )
    code, payload = _FRAME.unpack(raw)
    return Frame(code=code, payload=payload)


def register_name(number: int) -> str:
    """Devuelve 'x5 (t0)' para el registro 5."""
    return f"x{number} ({ABI_NAMES[number]})"


def to_signed(value: int) -> int:
    """Reinterpreta un valor de 32 bits sin signo como complemento a dos."""
    return value - 0x100000000 if value & 0x80000000 else value
