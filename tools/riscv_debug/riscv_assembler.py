"""
Ensamblador RV32I mínimo para el TP.

Convierte texto en ensamblador (o un `.hex`) a palabras de 32 bits listas para
mandarle a la FPGA por UART.

Uso rápido:

    from riscv_debug.riscv_assembler import assemble, load_file

    prog = assemble("addi x1, x0, 42\\nadd x2, x1, x1\\n")
    prog.words        # [0x02A00093, 0x001080B3]

    prog = load_file("test.s")     # detecta .s/.asm vs .hex por extension

Además de ensamblar, avisa cuáles instrucciones —aun estando bien codificadas—
NO las ejecuta correctamente ESTE procesador (ver CPU_UNSUPPORTED abajo): la ALU
del TP sólo implementa AND/OR/ADD/SUB.

Autotest: `python -m riscv_debug.riscv_assembler`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# =====================================================================
# Registros
# =====================================================================

ABI_NAMES = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)

#: Nombre -> número. Acepta xN, los nombres ABI, y "fp" como alias de s0/x8.
REGISTERS: dict[str, int] = {f"x{i}": i for i in range(32)}
REGISTERS.update({name: i for i, name in enumerate(ABI_NAMES)})
REGISTERS["fp"] = 8

# =====================================================================
# Tabla de instrucciones
# =====================================================================
# formato: (tipo, opcode, funct3, funct7)

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

#: Desplazamientos inmediatos: el "inmediato" es un shamt de 5 bits y los
#: 7 bits altos codifican la variante (lógico/aritmético).
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

#: Pseudo-instrucciones y cuántas instrucciones reales ocupan.
#: (`li` es 1 o 2 según el valor, se calcula aparte.)
PSEUDO_SIZE = {"nop": 1, "mv": 1, "j": 1, "jr": 1, "ret": 1, "li": None}

# =====================================================================
# Qué soporta REALMENTE este procesador
# =====================================================================
# La ALU del TP (alu.v) implementa sólo AND/OR/ADD/SUB, y alu_control.v manda
# todo lo que no reconoce al caso `default` (AND). Estas instrucciones se
# codifican bien pero la FPGA las ejecuta mal: conviene avisarlo antes de que
# el alumno pierda una tarde depurando el hardware equivocado.

CPU_UNSUPPORTED: dict[str, str] = {
    "sll":   "la ALU no implementa desplazamientos (alu_control lo manda a AND)",
    "srl":   "la ALU no implementa desplazamientos (alu_control lo manda a AND)",
    "sra":   "la ALU no implementa desplazamientos (alu_control lo manda a AND)",
    "slt":   "la ALU no implementa comparaciones (alu_control lo manda a AND)",
    "sltu":  "la ALU no implementa comparaciones (alu_control lo manda a AND)",
    "xor":   "la ALU no implementa XOR (alu_control lo manda a AND)",
    "slli":  "la ALU no implementa desplazamientos",
    "srli":  "la ALU no implementa desplazamientos",
    "srai":  "la ALU no implementa desplazamientos",
    "slti":  "la ALU no implementa comparaciones",
    "sltiu": "la ALU no implementa comparaciones",
    "xori":  "la ALU no implementa XOR",
    "lui":   "control.v le pone ALUSrc=1 y suma rs1, pero lui no tiene rs1: da basura",
    "auipc": "no esta en la tabla de control.v",
    "bne":   "memory.v resuelve el salto con (branch & zero): solo funciona BEQ",
    "blt":   "no implementado: la condicion de salto solo mira el flag zero",
    "bge":   "no implementado: la condicion de salto solo mira el flag zero",
    "bltu":  "no implementado: la condicion de salto solo mira el flag zero",
    "bgeu":  "no implementado: la condicion de salto solo mira el flag zero",
    "sb":    "el byte_write_en de memory.v no desplaza segun el offset",
    "sh":    "el byte_write_en de memory.v no desplaza segun el offset",
    "lb":    "memory.v no extrae ni extiende el sub-word leido",
    "lh":    "memory.v no extrae ni extiende el sub-word leido",
    "lbu":   "memory.v no extrae el sub-word leido",
    "lhu":   "memory.v no extrae el sub-word leido",
    "jal":   "el destino usa pc+imm con el inmediato desplazado de mas (ver docs/control-hazards.md)",
    "jalr":  "el destino deberia ser rs1+imm, pero se calcula pc+imm",
}


# =====================================================================
# Errores y resultado
# =====================================================================


class AssemblerError(Exception):
    """Error de sintaxis o de rango, siempre con número de línea."""

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
    """Resultado del ensamblado."""

    words: list[int] = field(default_factory=list)
    #: Índice de palabra -> texto fuente, para mostrarlo en el dashboard.
    listing: list[tuple[int, int, str]] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    #: Avisos de instrucciones que esta CPU no ejecuta bien.
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.words)

    def to_bytes(self, byteorder: str = "big") -> bytes:
        """Serializa el programa completo (big-endian por defecto, como el protocolo)."""
        return b"".join(w.to_bytes(4, byteorder) for w in self.words)

    def to_hex_lines(self) -> list[str]:
        return [f"{w:08X}" for w in self.words]


# =====================================================================
# Utilidades de parseo
# =====================================================================

_COMMENT = re.compile(r"[#;].*$")
_LABEL_DEF = re.compile(r"^\s*([A-Za-z_.][A-Za-z0-9_.$]*)\s*:\s*(.*)$")
_MEM_OPERAND = re.compile(r"^\s*(-?(?:0[xX])?[0-9A-Fa-f]+)?\s*\(\s*([A-Za-z0-9]+)\s*\)\s*$")


def strip_comment(line: str) -> str:
    """Saca comentarios (`#` o `;`) y espacios sobrantes."""
    return _COMMENT.sub("", line).strip()


def parse_register(token: str, line_number: int, source: str) -> int:
    """Acepta `x5`, `t0`, `sp`, `fp`... y devuelve el número de registro."""
    name = token.strip().lower()
    if name not in REGISTERS:
        raise AssemblerError(f"registro desconocido: {token!r}", line_number, source)
    return REGISTERS[name]


def parse_immediate(token: str, line_number: int, source: str) -> int:
    """
    Acepta decimal (`42`, `-10`), hexadecimal (`0x2A`, `-0x10`) y binario (`0b1010`).
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
    """Valida que un inmediato entre en la cantidad de bits del formato."""
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
    Parsea `offset(base)` -> (offset, nº de registro base).

    Acepta también `(x2)` (offset implícito 0) y `4 (x2)` con espacios.
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
# Codificadores por formato
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
    """El inmediato de branch es par y se guarda en bits salteados."""
    imm &= 0x1FFF
    return (((imm >> 12) & 0x1) << 31 | ((imm >> 5) & 0x3F) << 25
            | (rs2 & 0x1F) << 20 | (rs1 & 0x1F) << 15 | (funct3 & 0x7) << 12
            | ((imm >> 1) & 0xF) << 8 | ((imm >> 11) & 0x1) << 7 | (opcode & 0x7F))


def encode_u(opcode: int, rd: int, imm: int) -> int:
    return ((imm & 0xFFFFF) << 12 | (rd & 0x1F) << 7 | (opcode & 0x7F))


def encode_j(opcode: int, rd: int, imm: int) -> int:
    """El inmediato de jal es par y se guarda en bits salteados."""
    imm &= 0x1FFFFF
    return (((imm >> 20) & 0x1) << 31 | ((imm >> 1) & 0x3FF) << 21
            | ((imm >> 11) & 0x1) << 20 | ((imm >> 12) & 0xFF) << 12
            | (rd & 0x1F) << 7 | (opcode & 0x7F))


# =====================================================================
# Ensamblador
# =====================================================================


@dataclass
class _Line:
    """Una línea con instrucción, ya despojada de comentarios y etiquetas."""

    number: int
    source: str
    mnemonic: str
    operands: list[str]
    address: int


def _li_parts(value: int) -> tuple[int | None, int]:
    """
    Descompone `li rd, value` en (upper para lui, lower para addi).

    Si entra en 12 bits devuelve (None, value): alcanza un solo `addi`.
    Si no, se suma 0x800 antes de partir para compensar que el `addi`
    extiende el signo del inmediato bajo.
    """
    if -2048 <= value <= 2047:
        return None, value
    unsigned = value & 0xFFFFFFFF
    upper = (unsigned + 0x800) >> 12 & 0xFFFFF
    lower = unsigned - ((upper << 12) & 0xFFFFFFFF)
    lower = ((lower + 0x800) & 0xFFF) - 0x800     # a 12 bits con signo
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
    Ensambla texto RISC-V y devuelve un Program.

    Dos pasadas: la primera recolecta etiquetas con su dirección, la segunda
    codifica resolviendo los saltos.
    """
    program = Program()

    # ---------------- Pasada 1: etiquetas y direcciones ----------------
    lines: list[_Line] = []
    address = base_address

    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = strip_comment(raw)
        if not stripped:
            continue

        # Puede haber varias etiquetas antes de la instrucción, o etiqueta sola
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

        # Directivas de ensamblador: se ignoran con aviso
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

    # ---------------- Pasada 2: codificación ----------------
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
    Un destino de salto puede ser una etiqueta o un offset numérico.

    Con etiqueta se calcula relativo al PC de la instrucción actual; con número
    se toma tal cual como offset (que es lo que espera el enunciado del TP).
    """
    if token in labels:
        return labels[token] - current
    if re.match(r"^-?(0[xX])?[0-9A-Fa-f]+$", token) and not token.isalpha():
        return parse_immediate(token, number, source)
    raise AssemblerError(f"etiqueta no definida: {token!r}", number, source)


def _encode_line(line: _Line, labels: dict[str, int]) -> list[int]:
    """Codifica una línea; devuelve 1 palabra (o 2 para `li` grande)."""
    m, ops, n, src = line.mnemonic, line.operands, line.number, line.source

    def reg(index: int) -> int:
        return parse_register(ops[index], n, src)

    def need(count: int, form: str) -> None:
        if len(ops) != count:
            raise AssemblerError(
                f"{m} espera {count} operandos ({form}), recibi {len(ops)}", n, src
            )

    # -------- pseudo-instrucciones --------
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

    # -------- Tipo R --------
    if m in R_TYPE:
        need(3, f"{m} rd, rs1, rs2")
        opcode, funct3, funct7 = R_TYPE[m]
        return [encode_r(opcode, funct3, funct7, reg(0), reg(1), reg(2))]

    # -------- Tipo I aritmético --------
    if m in I_ARITH:
        need(3, f"{m} rd, rs1, imm")
        opcode, funct3 = I_ARITH[m]
        imm = parse_immediate(ops[2], n, src)
        check_range(imm, 12, f"inmediato de {m}", n, src)
        return [encode_i(opcode, funct3, reg(0), reg(1), imm)]

    # -------- Tipo I desplazamiento --------
    if m in I_SHIFT:
        need(3, f"{m} rd, rs1, shamt")
        opcode, funct3, funct7 = I_SHIFT[m]
        shamt = parse_immediate(ops[2], n, src)
        check_range(shamt, 5, f"shamt de {m}", n, src, signed=False)
        return [encode_i(opcode, funct3, reg(0), reg(1), (funct7 << 5) | shamt)]

    # -------- Tipo I carga / jalr --------
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

    # -------- Tipo S --------
    if m in S_TYPE:
        need(2, f"{m} rs2, offset(base)")
        opcode, funct3 = S_TYPE[m]
        imm, rs1 = parse_mem_operand(ops[1], n, src)
        check_range(imm, 12, f"offset de {m}", n, src)
        return [encode_s(opcode, funct3, rs1, reg(0), imm)]

    # -------- Tipo B --------
    if m in B_TYPE:
        need(3, f"{m} rs1, rs2, destino")
        opcode, funct3 = B_TYPE[m]
        offset = _resolve_target(ops[2], labels, line.address, n, src)
        if offset % 2:
            raise AssemblerError("el destino de un branch debe ser par", n, src)
        check_range(offset, 13, f"offset de {m}", n, src)
        return [encode_b(opcode, funct3, reg(0), reg(1), offset)]

    # -------- Tipo U --------
    if m in U_TYPE:
        need(2, f"{m} rd, imm20")
        imm = parse_immediate(ops[1], n, src)
        check_range(imm, 20, f"inmediato de {m}", n, src, signed=False)
        return [encode_u(U_TYPE[m], reg(0), imm)]

    # -------- Tipo J --------
    if m in J_TYPE:
        need(2, f"{m} rd, destino")
        offset = _resolve_target(ops[1], labels, line.address, n, src)
        if offset % 2:
            raise AssemblerError("el destino de jal debe ser par", n, src)
        check_range(offset, 21, f"offset de {m}", n, src)
        return [encode_j(J_TYPE[m], reg(0), offset)]

    raise AssemblerError(f"instruccion desconocida: {m!r}", n, src)


# =====================================================================
# Lectura de archivos
# =====================================================================


def parse_hex(text: str) -> Program:
    """
    Lee un `.hex`: una palabra por línea, 8 dígitos hexadecimales.

    Tolera el prefijo `0x`, guiones bajos, comentarios y líneas en blanco.
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
    """Carga `.hex` o ensamblador según la extensión."""
    file_path = Path(path)
    if not file_path.exists():
        raise AssemblerError(f"no existe el archivo: {file_path}")
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix.lower() in (".hex", ".txt"):
        return parse_hex(text)
    return assemble(text)


# =====================================================================
# Autotest
# =====================================================================


def _run_self_test() -> int:
    """Pruebas rápidas. Los vectores de referencia salen del programa de prueba
    del TP (dashboard.py), que ya se verifico corriendo en la FPGA."""
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
        # suma hasta que t0 valga 0
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
    # beq t0, zero, FIN esta en 0x0C y salta a 0x14 -> offset +8
    check("salto hacia adelante (+8)", prog.words[3], 0x00028463)
    # beq zero,zero,LOOP esta en 0x10 y salta a 0x04 -> offset -12
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
    warned = assemble("sll x1, x2, x3\nbne x1, x2, 8\nlui x1, 1")
    check("avisa sll/bne/lui", len(warned.warnings), 3)
    check("no avisa de add/addi", len(assemble("add x1,x2,x3\naddi x1,x0,1").warnings), 0)

    print("\n" + "=" * 54)
    if failures:
        print(f"FALLARON {len(failures)}: {failures}")
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_self_test())
