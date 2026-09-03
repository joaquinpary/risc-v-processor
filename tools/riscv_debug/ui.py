"""Dashboard rendering with rich. No I/O: it only turns state into views."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .protocol import (
    CONTROL_LEGEND,
    LATCH_IDS,
    LATCH_STAGES,
    REGISTER_COUNT,
    LatchField,
    decode_control,
    latch_fields,
    to_signed,
)
from .riscv_assembler import disassemble

#: Rows of the register table: 32 registers in 2 columns.
ROWS = REGISTER_COUNT // 2


@dataclass
class CpuState:
    """Last known snapshot of the processor."""

    port: str = "-"
    baudrate: int = 9600
    connected: bool = False

    pc: int | None = None
    registers: list[int | None] = field(
        default_factory=lambda: [None] * REGISTER_COUNT
    )
    #: Registers that changed since the previous read (they get highlighted).
    changed: set[int] = field(default_factory=set)

    #: Pipeline latch fields, by REQ_LATCH id.
    latches: dict[int, int | None] = field(
        default_factory=lambda: {i: None for i in LATCH_IDS}
    )
    #: Latch fields that changed since the previous read.
    changed_latches: set[int] = field(default_factory=set)
    #: Whether to read and show the latches. Reading them doubles the time
    #: of a refresh, so it can be turned off to step faster.
    show_latches: bool = True

    cycles: int = 0
    status: str = "Disconnected"
    last_error: str | None = None
    #: Last loaded program, to show it in the status panel.
    program_name: str | None = None
    program_size: int = 0

    def begin_refresh(self) -> None:
        """Starts a new read: keeps the old values so they can be compared."""
        self._previous = list(self.registers)
        self._previous_latches = dict(self.latches)
        self.changed = set()
        self.changed_latches = set()

    def set_register(self, number: int, value: int) -> None:
        previous = getattr(self, "_previous", self.registers)[number]
        self.registers[number] = value
        if previous is not None and previous != value:
            self.changed.add(number)

    def set_latch(self, latch_id: int, value: int) -> None:
        previous = getattr(self, "_previous_latches", self.latches)[latch_id]
        self.latches[latch_id] = value
        if previous is not None and previous != value:
            self.changed_latches.add(latch_id)

    def reset_values(self) -> None:
        self.pc = None
        self.registers = [None] * REGISTER_COUNT
        self.changed = set()
        self.latches = {i: None for i in LATCH_IDS}
        self.changed_latches = set()
        self.cycles = 0


def _format_word(value: int | None) -> tuple[str, str]:
    """Returns (hexadecimal, signed decimal) ready to display."""
    if value is None:
        return "--------", "-"
    return f"{value:08X}", str(to_signed(value))


def render_status(state: CpuState) -> Panel:
    """Top panel: connection, PC and cycle counter."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim")
    table.add_column()

    link_style = "bold green" if state.connected else "bold red"
    link_text = (
        f"{state.port} @ {state.baudrate} bps"
        if state.connected
        else "disconnected"
    )
    table.add_row("Link", Text(link_text, style=link_style))

    if state.pc is None:
        pc_text = Text("unknown", style="dim")
    else:
        pc_text = Text(f"0x{state.pc:08X}", style="bold cyan")
        pc_text.append(f"   (word {state.pc // 4})", style="dim")
    table.add_row("PC", pc_text)

    table.add_row("Cycles", Text(str(state.cycles), style="bold"))
    table.add_row("Status", Text(state.status, style="yellow"))

    if state.program_name:
        table.add_row(
            "Program",
            Text(f"{state.program_name}  ({state.program_size} instructions)",
                 style="green"),
        )

    if state.last_error:
        table.add_row("Error", Text(state.last_error, style="bold red"))

    return Panel(
        table,
        title="[bold]RISC-V Processor[/bold]",
        border_style="cyan" if state.connected else "red",
    )


def render_registers(state: CpuState) -> Panel:
    """
    Table of the 32 registers in 2 columns of 16 rows.

    The left column holds x0..x15 and the right one x16..x31, and the ones
    that changed since the previous step are highlighted in yellow.

    Registers are named by number alone. The ABI aliases (t0, s0...) are
    still accepted when writing assembly, they are just not shown here.
    """
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=None,
        pad_edge=False,
        padding=(0, 1),
    )
    for _ in range(2):
        table.add_column("Reg", style="dim", width=5)
        table.add_column("Hex", justify="right", width=8)
        table.add_column("Dec", justify="right", width=12)

    for row in range(ROWS):
        cells: list[RenderableType] = []
        for number in (row, row + ROWS):
            hex_text, dec_text = _format_word(state.registers[number])
            highlight = number in state.changed

            name = Text(f"x{number}", style="bold" if highlight else "dim")

            value_style = (
                "bold yellow"
                if highlight
                else ("dim" if state.registers[number] is None else "green")
            )
            # x0 is always zero by hardware: we show it dimmed.
            if number == 0:
                value_style = "dim"

            cells.extend(
                [
                    name,
                    Text(hex_text, style=value_style),
                    Text(dec_text, style=value_style),
                ]
            )
        table.add_row(*cells)

    return Panel(
        Align.center(table),
        title="[bold]Register File[/bold]",
        border_style="magenta",
    )


def _format_latch(latch: LatchField, value: int | None) -> tuple[str, str, bool]:
    """
    Returns (value, explanation, put the explanation on the same line).

    Each field is shown the way it is actually used: an instruction with its
    mnemonic, a control bus with the signals it asserts, rd as a register
    number. Showing all of them as plain hex would hide exactly what one
    wants to see when following an instruction through the pipeline.
    """
    if value is None:
        return "--------", "", True

    if latch.kind == "instr":
        return f"0x{value:08X}", disassemble(value), True
    if latch.kind == "reg":
        return f"x{value & 0x1F}", "", True
    if latch.kind == "bit":
        return str(value & 1), "", True
    if latch.kind == "funct3":
        return f"0b{value & 0b111:03b}", "", True
    if latch.kind.startswith("ctrl"):
        width = {"ctrl10": 10, "ctrl7": 7, "ctrl3": 3}[latch.kind]
        # The decoded bus is long, so it goes on its own line.
        return f"0x{value:03X}", decode_control(value, width), False
    return f"0x{value:08X}", "", True


def render_latches(state: CpuState) -> Panel:
    """
    The four pipeline latches, one column each.

    Read left to right it is the pipeline itself: what sits in IF/ID this
    cycle is in ID/EX the next one. The highlight is what makes a stall or a
    flush visible, because a frozen latch stops changing and a flushed one
    goes to zero.
    """
    grid = Table.grid(padding=(0, 3))
    for _ in LATCH_STAGES:
        grid.add_column(vertical="top")

    columns: list[RenderableType] = []
    for stage in LATCH_STAGES:
        table = Table(
            show_header=True,
            header_style="bold blue",
            box=None,
            pad_edge=False,
            padding=(0, 1),
        )
        # No fixed widths: the columns size to their content, so nothing gets
        # truncated into an ellipsis and the panel only takes what it needs.
        table.add_column(stage, style="dim", no_wrap=True)
        table.add_column("", justify="left", no_wrap=True)

        for latch in latch_fields(stage):
            value = state.latches[latch.id]
            main, detail, inline = _format_latch(latch, value)
            highlight = latch.id in state.changed_latches

            style = (
                "bold yellow"
                if highlight
                else ("dim" if value is None else "green")
            )
            cell = Text(main, style=style)
            if detail:
                cell.append(("  " if inline else "\n") + detail,
                            style="dim italic")
            table.add_row(latch.label, cell)

        columns.append(table)

    grid.add_row(*columns)
    return Panel(
        grid,
        title="[bold]Pipeline Latches[/bold]",
        subtitle=f"[dim]{CONTROL_LEGEND}[/dim]",
        border_style="blue",
    )


def render_menu(state: CpuState) -> Panel:
    """Bottom panel with the available options."""
    table = Table.grid(padding=(0, 3))
    table.add_column()
    table.add_column()
    table.add_column()

    table.add_row(
        Text.assemble(("1", "bold cyan"), (" Step", "")),
        Text.assemble(("2", "bold cyan"), (" Run", "")),
        Text.assemble(("3", "bold cyan"), (" Reset", "")),
    )
    table.add_row(
        Text.assemble(("4", "bold cyan"), (" Load program (.s / .hex)", "")),
        Text.assemble(("5", "bold cyan"), (" Refresh", "")),
        Text.assemble(("6", "bold cyan"), (" Read memory", "")),
    )
    latches = "Hide" if state.show_latches else "Show"
    table.add_row(
        Text.assemble(("7", "bold cyan"), (f" {latches} pipeline latches", "")),
        Text.assemble(("q", "bold cyan"), (" Quit", "")),
    )
    return Panel(table, border_style="dim", title="[dim]Menu[/dim]")


def render_dashboard(state: CpuState, show_menu: bool = True) -> RenderableType:
    """Builds the complete dashboard."""
    parts: list[RenderableType] = [render_status(state), render_registers(state)]
    if state.show_latches:
        parts.append(render_latches(state))
    if show_menu:
        parts.append(render_menu(state))
    return Group(*parts)
