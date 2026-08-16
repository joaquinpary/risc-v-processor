"""
UART protocol of the debug_unit - 5 byte frames.

Format (the same in both directions):

    byte 0   : command / response code
    bytes 1-4: 32-bit payload, big-endian (MSB first)

The big-endian order comes from uart_interface.v: on RX the buffer shifts every
received byte to the right (`rx_buffer <= {rx_buffer[31:0], rx_byte}`), so the
first byte ends up in rx_data[39:32] = cmd; on TX `tx_buffer[39:32]` is sent
first. That is: command first, payload MSB first.

IMPORTANT: the opcodes here come from reading debug_unit.v directly, not from
the TP statement (which has STEP and RUN swapped and REQ_REG at 0x03).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

#: Frame size in bytes (1 command + 4 of payload).
FRAME_SIZE = 5

#: 1 unsigned byte + 1 big-endian 32-bit integer.
_FRAME = struct.Struct(">BI")


class Command(IntEnum):
    """Commands the PC sends to the FPGA (debug_unit.v, IDLE state)."""

    STEP = 0x01        # advances exactly one clock cycle
    RUN = 0x02         # free run until cpu_halted goes active
    RESET = 0x03       # restarts the CPU and the instruction load pointer
    LOAD_INSTR = 0x10  # writes the payload as an instruction and auto-increments
    REQ_REG = 0x20     # payload[4:0] = register number
    REQ_MEM = 0x30     # payload = data memory address
    REQ_PC = 0x40      # no payload
    REQ_LATCH = 0x50   # payload[7:0] = pipeline latch id


class ResponseKind(IntEnum):
    """
    Codes the FPGA answers with.

    For REQ_REG the debug_unit returns the register number itself as the code
    (0x00..0x1F), so the low range is not a constant but a register.
    """

    PC = 0x20
    LATCH = 0x30
    MEM = 0x40


#: Highest response code that stands for a register (x0..x31).
MAX_REGISTER_CODE = 0x1F

#: Commands that do NOT answer: the debug_unit runs them and goes back to IDLE.
ACTION_COMMANDS = frozenset(
    {Command.STEP, Command.RUN, Command.RESET, Command.LOAD_INSTR}
)

#: ABI names of the 32 registers, to show them next to the number.
ABI_NAMES: tuple[str, ...] = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)

REGISTER_COUNT = 32


# =====================================================================
# Pipeline latches
# =====================================================================
# The ids mirror the debug_latch_id case in top.v one by one. Keep both
# sides in sync: the firmware answers 0x00000000 for an id it does not
# know, which looks exactly like a real zero, so a wrong id here shows up
# as a plausible value instead of an error.

LATCH_STAGES: tuple[str, ...] = ("IF/ID", "ID/EX", "EX/MEM", "MEM/WB")


@dataclass(frozen=True, slots=True)
class LatchField:
    """One field of a pipeline latch, as exposed by REQ_LATCH."""

    id: int
    stage: str
    label: str
    #: How to read the value: hex | instr | ctrl10 | ctrl7 | ctrl3 |
    #: funct3 | bit | reg
    kind: str


LATCH_FIELDS: tuple[LatchField, ...] = (
    LatchField(1,  "IF/ID",  "pc",     "hex"),
    LatchField(2,  "IF/ID",  "pc+4",   "hex"),
    LatchField(3,  "IF/ID",  "instr",  "instr"),

    LatchField(4,  "ID/EX",  "pc",     "hex"),
    LatchField(5,  "ID/EX",  "pc+4",   "hex"),
    LatchField(6,  "ID/EX",  "pc_br",  "hex"),
    LatchField(7,  "ID/EX",  "ctrl",   "ctrl10"),
    LatchField(8,  "ID/EX",  "rs1",    "hex"),
    LatchField(9,  "ID/EX",  "rs2",    "hex"),
    LatchField(10, "ID/EX",  "imm",    "hex"),
    LatchField(11, "ID/EX",  "f3",     "funct3"),
    LatchField(12, "ID/EX",  "bit30",  "bit"),
    LatchField(13, "ID/EX",  "rd",     "reg"),

    LatchField(14, "EX/MEM", "pc+4",   "hex"),
    LatchField(15, "EX/MEM", "pc_br",  "hex"),
    LatchField(16, "EX/MEM", "ctrl",   "ctrl7"),
    LatchField(17, "EX/MEM", "zero",   "bit"),
    LatchField(18, "EX/MEM", "result", "hex"),
    LatchField(19, "EX/MEM", "rs2",    "hex"),
    LatchField(20, "EX/MEM", "f3",     "funct3"),
    LatchField(21, "EX/MEM", "rd",     "reg"),

    LatchField(22, "MEM/WB", "ctrl",   "ctrl3"),
    LatchField(23, "MEM/WB", "rdata",  "hex"),
    LatchField(24, "MEM/WB", "result", "hex"),
    LatchField(25, "MEM/WB", "pc+4",   "hex"),
    LatchField(26, "MEM/WB", "rd",     "reg"),
)

#: Every id the dashboard asks for, in pipeline order.
LATCH_IDS: tuple[int, ...] = tuple(f.id for f in LATCH_FIELDS)


def latch_fields(stage: str) -> tuple[LatchField, ...]:
    """The fields of one latch, in the order they are declared."""
    return tuple(f for f in LATCH_FIELDS if f.stage == stage)


#: Where MemtoReg sends the value written to the register file.
MEM_TO_REG_NAMES = {0: "ALU", 1: "Mem", 2: "PC+4", 3: "?"}

#: Short tags used to render the control bus, with what each one means.
CONTROL_LEGEND = (
    "AO=ALUOp  Src=ALUSrc  Br=Branch  MR=MemRead  "
    "MW=MemWrite  J=Jump  RW=RegWrite  ->=MemtoReg"
)


def decode_control(value: int, width: int) -> str:
    """
    Turns a control bus into the list of signals that are asserted.

    `width` is how much of the bus survives at that point of the pipeline:
    10 bits in ID/EX (the whole thing), 7 in EX/MEM (execute drops ALUOp and
    ALUSrc) and 3 in MEM/WB (memory keeps only RegWrite and MemtoReg). The
    bit positions do not move, the bus is just truncated from the top.

    Layout, from control.v:
        ALUOp[9:8] ALUSrc[7] Branch[6] MemRead[5] MemWrite[4] Jump[3]
        RegWrite[2] MemtoReg[1:0]
    """
    if value == 0:
        # Every control signal off: nothing this instruction does has an
        # effect. That is a bubble, from a load-use stall or a flush.
        return "bubble"

    tags: list[str] = []
    if width >= 10:
        tags.append(f"AO={(value >> 8) & 0b11:02b}")
        if value & (1 << 7):
            tags.append("Src")
    if width >= 7:
        if value & (1 << 6):
            tags.append("Br")
        if value & (1 << 5):
            tags.append("MR")
        if value & (1 << 4):
            tags.append("MW")
        if value & (1 << 3):
            tags.append("J")
    if value & (1 << 2):
        # MemtoReg only means something when the register file is written.
        tags.append(f"RW->{MEM_TO_REG_NAMES[value & 0b11]}")
    return " ".join(tags)


class ProtocolError(Exception):
    """Malformed frame, or an answer that does not match what was asked."""


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded frame."""

    code: int
    payload: int

    @property
    def is_register(self) -> bool:
        """True if the answer is a register value (code = x0..x31)."""
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
    Builds a 5 byte frame ready to send over the serial port.

    The payload is masked to 32 bits so a negative or too large value does not
    break the packing.
    """
    return _FRAME.pack(int(command) & 0xFF, int(payload) & 0xFFFFFFFF)


def decode(raw: bytes) -> Frame:
    """Decodes a 5 byte frame received from the FPGA."""
    if len(raw) != FRAME_SIZE:
        raise ProtocolError(
            f"Expected {FRAME_SIZE} bytes, got {len(raw)}: {raw!r}"
        )
    code, payload = _FRAME.unpack(raw)
    return Frame(code=code, payload=payload)


def register_name(number: int) -> str:
    """Returns 'x5 (t0)' for register 5."""
    return f"x{number} ({ABI_NAMES[number]})"


def to_signed(value: int) -> int:
    """Reinterprets an unsigned 32-bit value as two's complement."""
    return value - 0x100000000 if value & 0x80000000 else value
