"""Renderizado del dashboard con rich. Sin E/S: solo transforma estado en vistas."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .protocol import ABI_NAMES, REGISTER_COUNT, to_signed

#: Filas de la tabla de registros: 32 registros en 2 columnas.
ROWS = REGISTER_COUNT // 2


@dataclass
class CpuState:
    """Última foto conocida del procesador."""

    port: str = "-"
    baudrate: int = 9600
    connected: bool = False

    pc: int | None = None
    registers: list[int | None] = field(
        default_factory=lambda: [None] * REGISTER_COUNT
    )
    #: Registros que cambiaron respecto de la lectura anterior (se resaltan).
    changed: set[int] = field(default_factory=set)

    cycles: int = 0
    status: str = "Sin conectar"
    last_error: str | None = None
    #: Último programa cargado, para mostrarlo en el panel de estado.
    program_name: str | None = None
    program_size: int = 0

    def begin_refresh(self) -> None:
        """Arranca una lectura nueva: guarda los valores viejos para comparar."""
        self._previous = list(self.registers)
        self.changed = set()

    def set_register(self, number: int, value: int) -> None:
        previous = getattr(self, "_previous", self.registers)[number]
        self.registers[number] = value
        if previous is not None and previous != value:
            self.changed.add(number)

    def reset_values(self) -> None:
        self.pc = None
        self.registers = [None] * REGISTER_COUNT
        self.changed = set()
        self.cycles = 0


def _format_word(value: int | None) -> tuple[str, str]:
    """Devuelve (hexadecimal, decimal con signo) listos para mostrar."""
    if value is None:
        return "--------", "-"
    return f"{value:08X}", str(to_signed(value))


def render_status(state: CpuState) -> Panel:
    """Panel superior: conexión, PC y contador de ciclos."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim")
    table.add_column()

    link_style = "bold green" if state.connected else "bold red"
    link_text = (
        f"{state.port} @ {state.baudrate} bps"
        if state.connected
        else "desconectado"
    )
    table.add_row("Enlace", Text(link_text, style=link_style))

    if state.pc is None:
        pc_text = Text("desconocido", style="dim")
    else:
        pc_text = Text(f"0x{state.pc:08X}", style="bold cyan")
        pc_text.append(f"   (palabra {state.pc // 4})", style="dim")
    table.add_row("PC", pc_text)

    table.add_row("Ciclos", Text(str(state.cycles), style="bold"))
    table.add_row("Estado", Text(state.status, style="yellow"))

    if state.program_name:
        table.add_row(
            "Programa",
            Text(f"{state.program_name}  ({state.program_size} instrucciones)",
                 style="green"),
        )

    if state.last_error:
        table.add_row("Error", Text(state.last_error, style="bold red"))

    return Panel(
        table,
        title="[bold]Procesador RISC-V[/bold]",
        border_style="cyan" if state.connected else "red",
    )


def render_registers(state: CpuState) -> Panel:
    """
    Tabla de los 32 registros en 2 columnas de 16 filas.

    La columna izquierda lleva x0..x15 y la derecha x16..x31. Los registros que
    cambiaron desde el paso anterior se resaltan en amarillo.
    """
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=None,
        pad_edge=False,
        padding=(0, 1),
    )
    for _ in range(2):
        table.add_column("Reg", style="dim", width=10)
        table.add_column("Hex", justify="right", width=8)
        table.add_column("Dec", justify="right", width=12)

    for row in range(ROWS):
        cells: list[RenderableType] = []
        for number in (row, row + ROWS):
            hex_text, dec_text = _format_word(state.registers[number])
            highlight = number in state.changed

            name = Text(f"x{number}", style="bold" if highlight else "dim")
            name.append(f" {ABI_NAMES[number]}", style="dim italic")

            value_style = (
                "bold yellow"
                if highlight
                else ("dim" if state.registers[number] is None else "green")
            )
            # x0 siempre vale cero por hardware: lo mostramos apagado.
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
        title="[bold]Banco de registros[/bold]",
        border_style="magenta",
    )


def render_menu() -> Panel:
    """Panel inferior con las opciones disponibles."""
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
        Text.assemble(("4", "bold cyan"), (" Cargar programa (.s / .hex)", "")),
        Text.assemble(("5", "bold cyan"), (" Refrescar", "")),
        Text.assemble(("6", "bold cyan"), (" Leer memoria", "")),
    )
    table.add_row(Text.assemble(("q", "bold cyan"), (" Salir", "")))
    return Panel(table, border_style="dim", title="[dim]Menú[/dim]")


def render_dashboard(state: CpuState, show_menu: bool = True) -> RenderableType:
    """Arma el dashboard completo."""
    parts: list[RenderableType] = [render_status(state), render_registers(state)]
    if show_menu:
        parts.append(render_menu())
    return Group(*parts)
