"""
Minimal RV32I assembler for the TP.

Turns assembly text (or a `.hex`) into 32-bit words ready to send to the FPGA
over UART.

Quick usage:

    from riscv_debug.riscv_assembler import assemble, load_file

    prog = assemble("addi x1, x0, 42\\nadd x2, x1, x1\\n")
    prog.words        # [0x02A00093, 0x001080B3]

    prog = load_file("test.s")     # picks .s/.asm vs .hex by extension

Besides assembling, it warns which instructions -even when encoded correctly-
THIS processor does NOT run properly (see CPU_UNSUPPORTED below).

Self test: `python -m riscv_debug.riscv_assembler`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# =====================================================================
# Registers
# =====================================================================

ABI_NAMES = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)

#: Name -> number. Accepts xN, the ABI names, and "fp" as an alias of s0/x8.
REGISTERS: dict[str, int] = {f"x{i}": i for i in range(32)}
REGISTERS.update({name: i for i, name in enumerate(ABI_NAMES)})
REGISTERS["fp"] = 8

# =====================================================================
# Instruction table
# =====================================================================
# format: (type, opcode, funct3, funct7)

R_TYPE = {
    "add":  (0b0110011, 0b000, 0b0000000),
    "sub":  (0b0110011, 0b000, 0b0100000),
    "sll":  (0b0110011, 0b001, 0b0000000),
    "slt":  (0b0110011, 0b010, 0b0000000),
    "sltu": (0b0110011, 0b011, 0b0000000),
    "xor":  (0b0110011, 0b100, 0b0000000),
    "srl":  (0b0110011, 0b101, 0b0000000),
    "sra":  (0b0110011, 0b101, 0b0100000),
    "or":   (0b0110011, 0b110, 0b0000000),
    "and":  (0b0110011, 0b111, 0b0000000),
}

I_ARITH = {
    "addi":  (0b0010011, 0b000),
    "slti":  (0b0010011, 0b010),
    "sltiu": (0b0010011, 0b011),
    "xori":  (0b0010011, 0b100),
    "ori":   (0b0010011, 0b110),
    "andi":  (0b0010011, 0b111),
}

#: Immediate shifts: the "immediate" is a 5 bit shamt and the top 7 bits
#: encode the variant (logical/arithmetic).
I_SHIFT = {
    "slli": (0b0010011, 0b001, 0b0000000),
    "srli": (0b0010011, 0b101, 0b0000000),
    "srai": (0b0010011, 0b101, 0b0100000),
}

I_LOAD = {
    "lb":  (0b0000011, 0b000),
    "lh":  (0b0000011, 0b001),
    "lw":  (0b0000011, 0b010),
    "lbu": (0b0000011, 0b100),
    "lhu": (0b0000011, 0b101),
}

I_JALR = {"jalr": (0b1100111, 0b000)}

S_TYPE = {
    "sb": (0b0100011, 0b000),
    "sh": (0b0100011, 0b001),
    "sw": (0b0100011, 0b010),
}

B_TYPE = {
    "beq":  (0b1100011, 0b000),
    "bne":  (0b1100011, 0b001),
    "blt":  (0b1100011, 0b100),
    "bge":  (0b1100011, 0b101),
    "bltu": (0b1100011, 0b110),
    "bgeu": (0b1100011, 0b111),
}

U_TYPE = {
    "lui":   0b0110111,
    "auipc": 0b0010111,
}

J_TYPE = {"jal": 0b1101111}

#: Pseudo-instructions and how many real instructions they take.
#: (`li` is 1 or 2 depending on the value, computed apart.)
PSEUDO_SIZE = {"nop": 1, "mv": 1, "j": 1, "jr": 1, "ret": 1, "li": None}

# =====================================================================
# What this processor REALLY supports
# =====================================================================
# The 32 instructions the TP asks for are already implemented. What is left
# here are the ones the assembler can encode but the processor does not run
# yet, so nobody loses an afternoon debugging the wrong hardware.

CPU_UNSUPPORTED: dict[str, str] = {
    "auipc": "no esta en la tabla de opcodes de control.v",
    "blt":   "la condicion de salto solo decodifica beq y bne",
    "bge":   "la condicion de salto solo decodifica beq y bne",
    "bltu":  "la condicion de salto solo decodifica beq y bne",
    "bgeu":  "la condicion de salto solo decodifica beq y bne",
}


# =====================================================================
# Errors and result
# =====================================================================


class AssemblerError(Exception):
    """Syntax or range error, always with a line number."""

    def __init__(self, message: str, line_number: int | None = None,
                 source: str | None = None):
        self.line_number = line_number
        self.source = source
        if line_number is not None:
            message = f"linea {line_number}: {message}"
            if source:
                message += f"\n    {source.strip()}"
        super().__init__(message)


@dataclass
class Program:
    """Result of the assembly."""

    words: list[int] = field(default_factory=list)
    #: Word index -> source text, to show it in the dashboard.
    listing: list[tuple[int, int, str]] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    #: Warnings about instructions this CPU does not run properly.
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.words)

    def to_bytes(self, byteorder: str = "big") -> bytes:
        """Serializes the whole program (big-endian by default, like the protocol)."""
        return b"".join(w.to_bytes(4, byteorder) for w in self.words)

    def to_hex_lines(self) -> list[str]:
        return [f"{w:08X}" for w in self.words]


# =====================================================================
# Parsing helpers
# =====================================================================

_COMMENT = re.compile(r"[#;].*$")
_LABEL_DEF = re.compile(r"^\s*([A-Za-z_.][A-Za-z0-9_.$]*)\s*:\s*(.*)$")
_MEM_OPERAND = re.compile(r"^\s*(-?(?:0[xX])?[0-9A-Fa-f]+)?\s*\(\s*([A-Za-z0-9]+)\s*\)\s*$")


def strip_comment(line: str) -> str:
    """Strips comments (`#` or `;`) and extra spaces."""
    return _COMMENT.sub("", line).strip()


def parse_register(token: str, line_number: int, source: str) -> int:
    """Accepts `x5`, `t0`, `sp`, `fp`... and returns the register number."""
    name = token.strip().lower()
    if name not in REGISTERS:
        raise AssemblerError(f"registro desconocido: {token!r}", line_number, source)
    return REGISTERS[name]


def parse_immediate(token: str, line_number: int, source: str) -> int:
    """
    Accepts decimal (`42`, `-10`), hex (`0x2A`, `-0x10`) and binary (`0b1010`).
    """
    text = token.strip()
    negative = text.startswith("-")
    if negative:
        text = text[1:].strip()

    try:
        if text.lower().startswith("0x"):
            value = int(text, 16)
        elif text.lower().startswith("0b"):
            value = int(text, 2)
        else:
            value = int(text, 10)
    except ValueError:
        raise AssemblerError(
            f"inmediato invalido: {token!r}", line_number, source
        ) from None
    return -value if negative else value


def check_range(value: int, bits: int, name: str, line_number: int,
                source: str, signed: bool = True) -> None:
    """Checks that an immediate fits in the bit count of the format."""
    if signed:
        low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    else:
        low, high = 0, (1 << bits) - 1
    if not low <= value <= high:
        raise AssemblerError(
            f"{name} fuera de rango: {value} (permitido {low}..{high})",
            line_number, source,
        )


def split_operands(text: str) -> list[str]:
    return [op.strip() for op in text.split(",") if op.strip()]


def parse_mem_operand(token: str, line_number: int, source: str) -> tuple[int, int]:
    """
    Parses `offset(base)` -> (offset, base register number).

    It also accepts `(x2)` (implicit offset 0) and `4 (x2)` with spaces.
    """
    match = _MEM_OPERAND.match(token)
    if not match:
        raise AssemblerError(
            f"esperaba la forma offset(registro), recibi {token!r}",
            line_number, source,
        )
    offset_text, base_text = match.groups()
    offset = parse_immediate(offset_text, line_number, source) if offset_text else 0
    return offset, parse_register(base_text, line_number, source)


# =====================================================================
# Encoders per format
# =====================================================================


def encode_r(opcode: int, funct3: int, funct7: int, rd: int, rs1: int, rs2: int) -> int:
    return ((funct7 & 0x7F) << 25 | (rs2 & 0x1F) << 20 | (rs1 & 0x1F) << 15
            | (funct3 & 0x7) << 12 | (rd & 0x1F) << 7 | (opcode & 0x7F))


def encode_i(opcode: int, funct3: int, rd: int, rs1: int, imm: int) -> int:
    return ((imm & 0xFFF) << 20 | (rs1 & 0x1F) << 15 | (funct3 & 0x7) << 12
            | (rd & 0x1F) << 7 | (opcode & 0x7F))


def encode_s(opcode: int, funct3: int, rs1: int, rs2: int, imm: int) -> int:
    imm &= 0xFFF
    return ((imm >> 5) << 25 | (rs2 & 0x1F) << 20 | (rs1 & 0x1F) << 15
            | (funct3 & 0x7) << 12 | (imm & 0x1F) << 7 | (opcode & 0x7F))


def encode_b(opcode: int, funct3: int, rs1: int, rs2: int, imm: int) -> int:
    """The branch immediate is even and is stored in scattered bits."""
    imm &= 0x1FFF
    return (((imm >> 12) & 0x1) << 31 | ((imm >> 5) & 0x3F) << 25
            | (rs2 & 0x1F) << 20 | (rs1 & 0x1F) << 15 | (funct3 & 0x7) << 12
            | ((imm >> 1) & 0xF) << 8 | ((imm >> 11) & 0x1) << 7 | (opcode & 0x7F))


def encode_u(opcode: int, rd: int, imm: int) -> int:
    return ((imm & 0xFFFFF) << 12 | (rd & 0x1F) << 7 | (opcode & 0x7F))


def encode_j(opcode: int, rd: int, imm: int) -> int:
    """The jal immediate is even and is stored in scattered bits."""
    imm &= 0x1FFFFF
    return (((imm >> 20) & 0x1) << 31 | ((imm >> 1) & 0x3FF) << 21
            | ((imm >> 11) & 0x1) << 20 | ((imm >> 12) & 0xFF) << 12
            | (rd & 0x1F) << 7 | (opcode & 0x7F))


# =====================================================================
# Assembler
# =====================================================================


@dataclass
class _Line:
    """A line with an instruction, already stripped of comments and labels."""

    number: int
    source: str
    mnemonic: str
    operands: list[str]
    address: int


def _li_parts(value: int) -> tuple[int | None, int]:
    """
    Splits `li rd, value` into (upper for lui, lower for addi).

    If it fits in 12 bits it returns (None, value): a single `addi` is enough.
    If not, 0x800 is added before splitting to compensate that the `addi`
    sign extends the low immediate.
    """
    if -2048 <= value <= 2047:
        return None, value
    unsigned = value & 0xFFFFFFFF
    upper = (unsigned + 0x800) >> 12 & 0xFFFFF
    lower = unsigned - ((upper << 12) & 0xFFFFFFFF)
    lower = ((lower + 0x800) & 0xFFF) - 0x800     # to signed 12 bits
    return upper, lower


def _pseudo_size(mnemonic: str, operands: list[str], number: int, source: str) -> int:
    if mnemonic != "li":
        return PSEUDO_SIZE[mnemonic]
    if len(operands) != 2:
        raise AssemblerError("li espera 2 operandos: li rd, valor", number, source)
    upper, _ = _li_parts(parse_immediate(operands[1], number, source))
    return 1 if upper is None else 2


def assemble(text: str, base_address: int = 0) -> Program:
    """
    Assembles RISC-V text and returns a Program.

    Two passes: the first collects labels with their address, the second
    encodes resolving the branches.
    """
    program = Program()

    # ---------------- Pass 1: labels and addresses ----------------
    lines: list[_Line] = []
    address = base_address

    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = strip_comment(raw)
        if not stripped:
            continue

        # There can be several labels before the instruction, or a lone label
        while True:
            match = _LABEL_DEF.match(stripped)
            if not match:
                break
            label, rest = match.groups()
            if label in program.labels:
                raise AssemblerError(f"etiqueta duplicada: {label!r}", number, raw)
            program.labels[label] = address
            stripped = rest.strip()
            if not stripped:
                break
        if not stripped:
            continue

        # Assembler directives: ignored with a warning
        if stripped.startswith("."):
            program.warnings.append(
                f"linea {number}: directiva ignorada: {stripped.split()[0]}"
            )
            continue

        parts = stripped.replace("\t", " ").split(None, 1)
        mnemonic = parts[0].lower()
        operands = split_operands(parts[1]) if len(parts) > 1 else []

        if mnemonic in PSEUDO_SIZE:
            size = _pseudo_size(mnemonic, operands, number, raw)
        elif _is_known(mnemonic):
            size = 1
        else:
            raise AssemblerError(f"instruccion desconocida: {mnemonic!r}", number, raw)

        lines.append(_Line(number, raw, mnemonic, operands, address))
        address += 4 * size

    # ---------------- Pass 2: encoding ----------------
    seen_unsupported: set[str] = set()

    for line in lines:
        words = _encode_line(line, program.labels)
        for offset, word in enumerate(words):
            program.words.append(word)
            program.listing.append(
                (line.address + 4 * offset, word, strip_comment(line.source))
            )
        if line.mnemonic in CPU_UNSUPPORTED and line.mnemonic not in seen_unsupported:
            seen_unsupported.add(line.mnemonic)
            program.warnings.append(
                f"'{line.mnemonic}' se codifica bien pero esta CPU no lo ejecuta "
                f"correctamente: {CPU_UNSUPPORTED[line.mnemonic]}"
            )

    return program


def _is_known(mnemonic: str) -> bool:
    return (mnemonic in R_TYPE or mnemonic in I_ARITH or mnemonic in I_SHIFT
            or mnemonic in I_LOAD or mnemonic in I_JALR or mnemonic in S_TYPE
            or mnemonic in B_TYPE or mnemonic in U_TYPE or mnemonic in J_TYPE)


def _resolve_target(token: str, labels: dict[str, int], current: int,
                    number: int, source: str) -> int:
    """
    A branch target can be a label or a numeric offset.

    With a label it is computed relative to the PC of the current instruction;
    with a number it is taken as the offset itself (which is what the TP
    statement expects).
    """
    if token in labels:
        return labels[token] - current
    if re.match(r"^-?(0[xX])?[0-9A-Fa-f]+$", token) and not token.isalpha():
        return parse_immediate(token, number, source)
    raise AssemblerError(f"etiqueta no definida: {token!r}", number, source)


def _encode_line(line: _Line, labels: dict[str, int]) -> list[int]:
    """Encodes one line; returns 1 word (or 2 for a large `li`)."""
    m, ops, n, src = line.mnemonic, line.operands, line.number, line.source

    def reg(index: int) -> int:
        return parse_register(ops[index], n, src)

    def need(count: int, form: str) -> None:
        if len(ops) != count:
            raise AssemblerError(
                f"{m} espera {count} operandos ({form}), recibi {len(ops)}", n, src
            )

    # -------- pseudo-instructions --------
    if m == "nop":
        return [encode_i(0b0010011, 0b000, 0, 0, 0)]           # addi x0, x0, 0
    if m == "mv":
        need(2, "mv rd, rs")
        return [encode_i(0b0010011, 0b000, reg(0), reg(1), 0)]  # addi rd, rs, 0
    if m == "ret":
        return [encode_i(0b1100111, 0b000, 0, 1, 0)]            # jalr x0, 0(ra)
    if m == "jr":
        need(1, "jr rs")
        return [encode_i(0b1100111, 0b000, 0, reg(0), 0)]
    if m == "j":
        need(1, "j destino")
        offset = _resolve_target(ops[0], labels, line.address, n, src)
        check_range(offset, 21, "offset de j", n, src)
        if offset % 2:
            raise AssemblerError("el destino de j debe ser par", n, src)
        return [encode_j(0b1101111, 0, offset)]
    if m == "li":
        need(2, "li rd, valor")
        rd = reg(0)
        upper, lower = _li_parts(parse_immediate(ops[1], n, src))
        if upper is None:
            return [encode_i(0b0010011, 0b000, rd, 0, lower)]
        return [
            encode_u(0b0110111, rd, upper),                      # lui rd, upper
            encode_i(0b0010011, 0b000, rd, rd, lower),           # addi rd, rd, lower
        ]

    # -------- R-type --------
    if m in R_TYPE:
        need(3, f"{m} rd, rs1, rs2")
        opcode, funct3, funct7 = R_TYPE[m]
        return [encode_r(opcode, funct3, funct7, reg(0), reg(1), reg(2))]

    # -------- Arithmetic I-type --------
    if m in I_ARITH:
        need(3, f"{m} rd, rs1, imm")
        opcode, funct3 = I_ARITH[m]
        imm = parse_immediate(ops[2], n, src)
        check_range(imm, 12, f"inmediato de {m}", n, src)
        return [encode_i(opcode, funct3, reg(0), reg(1), imm)]

    # -------- Shift I-type --------
    if m in I_SHIFT:
        need(3, f"{m} rd, rs1, shamt")
        opcode, funct3, funct7 = I_SHIFT[m]
        shamt = parse_immediate(ops[2], n, src)
        check_range(shamt, 5, f"shamt de {m}", n, src, signed=False)
        return [encode_i(opcode, funct3, reg(0), reg(1), (funct7 << 5) | shamt)]

    # -------- Load I-type / jalr --------
    if m in I_LOAD or m in I_JALR:
        opcode, funct3 = (I_LOAD | I_JALR)[m]
        if len(ops) == 2:                       # lw x5, 4(x2)  /  jalr x1, 0(x2)
            imm, rs1 = parse_mem_operand(ops[1], n, src)
        elif len(ops) == 3:                     # jalr x1, x2, 0
            rs1, imm = reg(1), parse_immediate(ops[2], n, src)
        else:
            raise AssemblerError(
                f"{m} espera 'rd, offset(base)' o 'rd, rs1, offset'", n, src
            )
        check_range(imm, 12, f"offset de {m}", n, src)
        return [encode_i(opcode, funct3, reg(0), rs1, imm)]

    # -------- S-type --------
    if m in S_TYPE:
        need(2, f"{m} rs2, offset(base)")
        opcode, funct3 = S_TYPE[m]
        imm, rs1 = parse_mem_operand(ops[1], n, src)
        check_range(imm, 12, f"offset de {m}", n, src)
        return [encode_s(opcode, funct3, rs1, reg(0), imm)]

    # -------- B-type --------
    if m in B_TYPE:
        need(3, f"{m} rs1, rs2, destino")
        opcode, funct3 = B_TYPE[m]
        offset = _resolve_target(ops[2], labels, line.address, n, src)
        if offset % 2:
            raise AssemblerError("el destino de un branch debe ser par", n, src)
        check_range(offset, 13, f"offset de {m}", n, src)
        return [encode_b(opcode, funct3, reg(0), reg(1), offset)]

    # -------- U-type --------
    if m in U_TYPE:
        need(2, f"{m} rd, imm20")
        imm = parse_immediate(ops[1], n, src)
        check_range(imm, 20, f"inmediato de {m}", n, src, signed=False)
        return [encode_u(U_TYPE[m], reg(0), imm)]

    # -------- J-type --------
    if m in J_TYPE:
        need(2, f"{m} rd, destino")
        offset = _resolve_target(ops[1], labels, line.address, n, src)
        if offset % 2:
            raise AssemblerError("el destino de jal debe ser par", n, src)
        check_range(offset, 21, f"offset de {m}", n, src)
        return [encode_j(J_TYPE[m], reg(0), offset)]

    raise AssemblerError(f"instruccion desconocida: {m!r}", n, src)


# =====================================================================
# File reading
# =====================================================================


def parse_hex(text: str) -> Program:
    """
    Reads a `.hex`: one word per line, 8 hexadecimal digits.

    It tolerates the `0x` prefix, underscores, comments and blank lines.
    """
    program = Program()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = strip_comment(raw).replace("_", "").replace(" ", "")
        if not line:
            continue
        if line.lower().startswith("0x"):
            line = line[2:]
        if not re.fullmatch(r"[0-9A-Fa-f]{1,8}", line):
            raise AssemblerError(
                f"esperaba una palabra hexadecimal de hasta 8 digitos, recibi {raw.strip()!r}",
                number, raw,
            )
        word = int(line, 16)
        program.words.append(word)
        program.listing.append((4 * (len(program.words) - 1), word, f"0x{word:08X}"))
    return program


def load_file(path: str | Path) -> Program:
    """Loads `.hex` or assembly depending on the extension."""
    file_path = Path(path)
    if not file_path.exists():
        raise AssemblerError(f"no existe el archivo: {file_path}")
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix.lower() in (".hex", ".txt"):
        return parse_hex(text)
    return assemble(text)


# =====================================================================
# Self test
# =====================================================================


def _run_self_test() -> int:
    """Quick tests. The reference vectors come from the TP test program
    (dashboard.py), already verified running on the FPGA."""
    failures: list[str] = []

    def check(name: str, got, expected) -> None:
        ok = got == expected
        shown_got = f"0x{got:08X}" if isinstance(got, int) else got
        shown_exp = f"0x{expected:08X}" if isinstance(expected, int) else expected
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + ("" if ok else f"   obtuve {shown_got}, esperaba {shown_exp}"))
        if not ok:
            failures.append(name)

    def one(text: str) -> int:
        return assemble(text).words[0]

    print("=== Vectores del programa de prueba del TP ===")
    golden = [
        ("addi x1, x0, 42",   0x02A00093),
        ("addi x2, x0, 100",  0x06400113),
        ("add  x4, x1, x2",   0x00208233),
        ("sub  x5, x4, x1",   0x401202B3),
        ("add  x6, x5, x4",   0x00428333),
        ("addi x7, x6, 1",    0x00130393),
        ("addi x8, x0, 8",    0x00800413),
        ("sw   x8, 8(x0)",    0x00802423),
        ("lw   x9, 8(x0)",    0x00802483),
        ("add  x10, x9, x1",  0x00148533),
        ("add  x11, x10, x9", 0x009505B3),
        ("beq  x0, x0, 8",    0x00000463),
    ]
    for source, expected in golden:
        check(source, one(source), expected)

    print("\n=== Formatos pedidos ===")
    check("lw x5, 4(x2)",   one("lw x5, 4(x2)"),   0x00412283)
    check("sw x5, 0(x2)",   one("sw x5, 0(x2)"),   0x00512023)
    check("sw x5, 4(x2)",   one("sw x5, 4(x2)"),   0x00512223)
    check("beq x1, x2, 12", one("beq x1, x2, 12"), 0x00208663)
    check("lui x1, 0x12345", one("lui x1, 0x12345"), 0x123450B7)
    check("jal x1, 16",     one("jal x1, 16"),     0x010000EF)
    check("jalr x1, 0(x2)", one("jalr x1, 0(x2)"), 0x000100E7)
    check("and x3, x1, x2", one("and x3, x1, x2"), 0x0020F1B3)
    check("or x3, x1, x2",  one("or x3, x1, x2"),  0x0020E1B3)
    check("sll x3, x1, x2", one("sll x3, x1, x2"), 0x002091B3)
    check("srl x3, x1, x2", one("srl x3, x1, x2"), 0x0020D1B3)
    check("slt x3, x1, x2", one("slt x3, x1, x2"), 0x0020A1B3)

    print("\n=== Nombres ABI, hex, negativos, comentarios ===")
    check("addi t0, zero, 42 == addi x5, x0, 42",
          one("addi t0, zero, 42"), one("addi x5, x0, 42"))
    check("addi x1, x0, 0x2A == 42", one("addi x1, x0, 0x2A"), 0x02A00093)
    check("addi x1, x0, -1", one("addi x1, x0, -1"), 0xFFF00093)
    check("addi x1, x0, -10", one("addi x1, x0, -10"), 0xFF600093)
    check("sw con offset negativo", one("sw x5, -4(x2)"), 0xFE512E23)
    check("comentario con #", one("addi x1, x0, 42  # hola"), 0x02A00093)
    check("comentario con ;", one("addi x1, x0, 42  ; hola"), 0x02A00093)
    check("nop", one("nop"), 0x00000013)
    check("mv x1, x2", one("mv x1, x2"), 0x00010093)

    print("\n=== Etiquetas ===")
    prog = assemble("""
        # add until t0 is 0
        addi t0, zero, 3
    LOOP:
        addi t1, t1, 1
        addi t0, t0, -1
        beq  t0, zero, FIN
        beq  zero, zero, LOOP
    FIN:
        add  a0, t1, zero
    """)
    check("etiquetas: 6 instrucciones", len(prog), 6)
    check("LOOP en 0x04", prog.labels["LOOP"], 4)
    check("FIN en 0x14", prog.labels["FIN"], 20)
    # beq t0, zero, FIN is at 0x0C and jumps to 0x14 -> offset +8
    check("salto hacia adelante (+8)", prog.words[3], 0x00028463)
    # beq zero,zero,LOOP is at 0x10 and jumps to 0x04 -> offset -12
    check("salto hacia atras (-12)", prog.words[4], 0xFE000AE3)

    print("\n=== li (1 y 2 instrucciones) ===")
    check("li chico = addi", assemble("li x1, 42").words, [0x02A00093])
    big = assemble("li x1, 0x12345678")
    check("li grande = 2 palabras", len(big), 2)
    check("li grande: lui", big.words[0], 0x123450B7)
    check("li grande: addi", big.words[1], 0x67808093)

    print("\n=== Lectura de .hex ===")
    hex_prog = parse_hex("02A00093\n0x06400113  # con prefijo\n\n00208233\n")
    check("hex: 3 palabras", hex_prog.words,
          [0x02A00093, 0x06400113, 0x00208233])

    print("\n=== Serializacion ===")
    check("to_bytes big-endian", assemble("addi x1, x0, 42").to_bytes(),
          bytes([0x02, 0xA0, 0x00, 0x93]))

    print("\n=== Errores bien reportados ===")
    for source, fragment in [
        ("addi x1, x0, 5000", "fuera de rango"),
        ("addi x1, x99, 1", "registro desconocido"),
        ("frobnicate x1, x2", "desconocida"),
        ("beq x1, x2, NOEXISTE", "etiqueta no definida"),
        ("addi x1, x0", "espera 3 operandos"),
        ("lw x5, 4 x2", "offset(registro)"),
        ("beq x1, x2, 7", "debe ser par"),
    ]:
        try:
            assemble(source)
            check(f"rechaza {source!r}", "no fallo", f"error con {fragment!r}")
        except AssemblerError as exc:
            check(f"rechaza {source!r}", fragment in str(exc), True)

    print("\n=== Avisos de lo que esta CPU no ejecuta ===")
    check("avisa de blt/bgeu (sin implementar)",
          len(assemble("blt x1, x2, 8\nbgeu x1, x2, 8").warnings), 2)
    supported = ("add x1,x2,x3\nsll x1,x2,x3\nslt x1,x2,x3\nxor x1,x2,x3\n"
                 "srai x1,x2,3\nlui x1,1\nbne x1,x2,8\njal x1,8\n"
                 "jalr x1,0(x2)\nlb x1,1(x2)\nsh x1,2(x2)\n")
    check("no avisa de las 32 del TP", len(assemble(supported).warnings), 0)

    print("\n" + "=" * 54)
    if failures:
        print(f"FALLARON {len(failures)}: {failures}")
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_self_test())
