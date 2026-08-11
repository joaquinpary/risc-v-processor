"""
TUI dashboard for the pipelined RISC-V processor.

Usage:
    python -m riscv_debug --port /dev/ttyUSB0
    python -m riscv_debug --port COM3 --baud 9600

The main loop is async; the serial I/O (blocking) runs in threads and so does
the user input, so the interface never freezes waiting for the board.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .link import (
    DebugLink,
    DebugLinkError,
    PortUnavailable,
    ResponseTimeout,
    available_ports,
)
from .protocol import ProtocolError, REGISTER_COUNT
from .riscv_assembler import AssemblerError, load_file
from .ui import CpuState, render_dashboard

#: Words in the instruction memory (instruction_memory: addrb = pc[11:2]).
IMEM_WORDS = 1024

console = Console()


# ----------------------------------------------------------------------
# Board operations
# ----------------------------------------------------------------------
async def refresh_state(link: DebugLink, state: CpuState) -> None:
    """
    Re-reads the PC and the 32 registers, updating the screen as they arrive.

    Each register is asked for separately (the protocol has no block read), so
    the table can be seen filling up live.
    """
    state.begin_refresh()
    state.status = "Leyendo estado..."

    with Live(
        render_dashboard(state, show_menu=False),
        console=console,
        refresh_per_second=15,
        transient=True,
    ) as live:
        try:
            state.pc = await link.read_pc()
            live.update(render_dashboard(state, show_menu=False))

            async for number, value in link.read_all_registers():
                state.set_register(number, value)
                live.update(render_dashboard(state, show_menu=False))

        except (ResponseTimeout, ProtocolError) as exc:
            state.last_error = f"Lectura incompleta: {exc}"
            state.status = "Error de comunicación"
            await link.resync()
            return

    state.last_error = None
    state.status = "Detenido"


async def do_step(link: DebugLink, state: CpuState) -> None:
    """Advances one clock cycle and re-reads the whole state."""
    await link.step()
    state.cycles += 1
    await refresh_state(link, state)


async def do_run(link: DebugLink, state: CpuState) -> None:
    """
    Starts the free run and waits for the CPU to stop.

    While in RUNNING the debug_unit does not listen to the UART, so the end is
    detected by polling: the first answer to a REQ_PC means it went back to
    IDLE (that is, cpu_halted went active).
    """
    state.status = "Ejecutando..."
    console.print(
        Panel(
            Text(
                "Ejecución libre en curso. La placa no responde pedidos hasta "
                "que se active cpu_halted.",
                style="yellow",
            ),
            border_style="yellow",
        )
    )

    await link.run()

    with console.status("[yellow]Esperando a que el procesador frene...", spinner="dots"):
        halted = await link.wait_until_halted()

    if not halted:
        state.status = "Sin respuesta (¿sigue corriendo?)"
        state.last_error = (
            "La CPU no volvió a IDLE. Puede que el programa no termine en una "
            "instrucción nula, o que cpu_halted nunca se active."
        )
        return

    state.cycles = 0  # the manual cycle count makes no sense after a RUN
    await refresh_state(link, state)
    state.status = "Detenido (halt)"


async def do_reset(link: DebugLink, state: CpuState) -> None:
    """Restarts the CPU and clears the view."""
    await link.reset()
    state.reset_values()
    await refresh_state(link, state)
    state.status = "Reiniciado"


async def do_load_program(link: DebugLink, state: CpuState) -> None:
    """
    Assembles a .s/.asm/.hex file and loads it into the instruction memory.

    When it finishes it sends a RESET (included in link.load_program) to leave
    the PC at 0 and the pipeline ready, and re-reads the state.
    """
    raw = await asyncio.to_thread(
        Prompt.ask, "[cyan]Archivo[/cyan] (.s / .asm / .hex)"
    )
    path = Path(raw.strip().strip('"').strip("'")).expanduser()

    # ---- Assembly ----
    try:
        program = await asyncio.to_thread(load_file, path)
    except AssemblerError as exc:
        state.last_error = f"Error de ensamblado: {exc}"
        console.print(Panel(Text(str(exc), style="bold red"),
                            title="[bold red]No se pudo ensamblar[/bold red]",
                            border_style="red"))
        await asyncio.to_thread(Prompt.ask, "[dim]Enter para volver[/dim]", default="")
        return

    if not len(program):
        state.last_error = "El archivo no tiene instrucciones"
        return

    # ---- Preview ----
    listing = Table(show_header=True, header_style="bold magenta", box=None)
    listing.add_column("Dir", style="dim", width=8)
    listing.add_column("Palabra", width=10)
    listing.add_column("Fuente")
    for address, word, source in program.listing[:12]:
        listing.add_row(f"0x{address:04X}", f"{word:08X}", source)
    if len(program.listing) > 12:
        listing.add_row("...", "...", f"(+{len(program.listing) - 12} mas)")

    console.print(Panel(
        listing,
        title=f"[bold]{path.name}[/bold] — {len(program)} instrucciones",
        border_style="cyan",
    ))

    # Warnings: instructions that encode fine but this CPU does not run
    if program.warnings:
        console.print(Panel(
            _stack([Text(f"• {w}", style="yellow") for w in program.warnings]),
            title="[bold yellow]Avisos[/bold yellow]",
            border_style="yellow",
        ))

    if len(program) > IMEM_WORDS:
        state.last_error = (
            f"El programa no entra: {len(program)} instrucciones y la memoria "
            f"tiene {IMEM_WORDS} palabras"
        )
        console.print(Panel(Text(state.last_error, style="bold red"),
                            border_style="red"))
        return

    confirm = await asyncio.to_thread(
        Prompt.ask, "[cyan]Cargar a la FPGA?[/cyan]",
        choices=["s", "n"], default="s",
    )
    if confirm != "s":
        return

    # ---- Sending with a progress bar ----
    state.status = "Cargando programa..."
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress_bar:
        task = progress_bar.add_task(f"Enviando {path.name}", total=len(program))

        def advance(sent: int, total: int) -> None:
            progress_bar.update(task, completed=sent)

        try:
            await link.load_program(program.words, progress=advance)
        except DebugLinkError as exc:
            state.last_error = f"Fallo la carga: {exc}"
            state.status = "Error al cargar"
            return

    state.program_name = path.name
    state.program_size = len(program)
    state.last_error = None
    state.cycles = 0
    state.reset_values()

    console.print(Panel(
        Text(f"{len(program)} instrucciones cargadas. PC en 0x00, listo para "
             f"correr (opcion 1 = Step, 2 = Run).", style="bold green"),
        border_style="green",
    ))

    await refresh_state(link, state)
    state.status = "Programa cargado"


async def do_read_memory(link: DebugLink, state: CpuState) -> None:
    """Reads a word from the data memory (port B, it does not stop the CPU)."""
    raw = await asyncio.to_thread(
        Prompt.ask, "[cyan]Dirección[/cyan] (hex con 0x, o decimal)", default="0"
    )
    try:
        address = int(raw, 0)
    except ValueError:
        state.last_error = f"Dirección inválida: {raw!r}"
        return

    try:
        value = await link.read_memory(address)
    except (ResponseTimeout, ProtocolError) as exc:
        state.last_error = f"No se pudo leer 0x{address:08X}: {exc}"
        await link.resync()
        return

    console.print(
        Panel(
            Text(f"mem[0x{address:08X}] = 0x{value:08X}  ({value})", style="bold green"),
            border_style="green",
        )
    )


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
async def interactive_loop(link: DebugLink, state: CpuState) -> None:
    """Draws the dashboard and serves the menu until the user quits."""
    actions = {
        "1": do_step,
        "2": do_run,
        "3": do_reset,
        "4": do_load_program,
        "5": refresh_state,
        "6": do_read_memory,
    }

    await refresh_state(link, state)

    while True:
        console.clear()
        console.print(render_dashboard(state))

        choice = await asyncio.to_thread(
            Prompt.ask,
            "[bold cyan]Opción[/bold cyan]",
            choices=["1", "2", "3", "4", "5", "6", "q"],
            default="1",
        )

        if choice == "q":
            return

        try:
            await actions[choice](link, state)
        except DebugLinkError as exc:
            # The port was lost (board unplugged, for example).
            state.connected = link.is_open
            state.last_error = str(exc)
            state.status = "Enlace caído"
            if not link.is_open:
                console.print(
                    Panel(
                        Text(f"Se perdió la conexión: {exc}", style="bold red"),
                        border_style="red",
                    )
                )
                return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="riscv_debug",
        description="Dashboard de depuración para el procesador RISC-V en FPGA.",
    )
    parser.add_argument(
        "--port",
        "-p",
        required=True,
        help="Puerto serie (ej. /dev/ttyUSB0 en Linux, COM3 en Windows)",
    )
    parser.add_argument("--baud", "-b", type=int, default=9600, help="Baudios (9600)")
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=2.0,
        help="Timeout de lectura en segundos (2.0)",
    )
    return parser.parse_args(argv)


def report_port_error(exc: PortUnavailable, requested: str) -> None:
    """Shows the connection error together with the ports that do exist."""
    lines = [Text(str(exc), style="bold red"), Text("")]

    ports = available_ports()
    if ports:
        lines.append(Text("Puertos detectados:", style="bold"))
        lines.extend(Text(f"  • {p}", style="cyan") for p in ports)
    else:
        lines.append(
            Text(
                "No se detectó ningún puerto serie. Revisá que la placa esté "
                "conectada y programada.",
                style="yellow",
            )
        )
        lines.append(
            Text(
                "En Linux puede faltar permiso: sudo usermod -aG dialout $USER "
                "(y volver a iniciar sesión).",
                style="dim",
            )
        )

    console.print(
        Panel(
            _stack(lines),
            title=f"[bold red]No se pudo conectar a {requested}[/bold red]",
            border_style="red",
        )
    )


def _stack(items: list[Text]) -> Text:
    """Joins several Text objects into one, separated by line breaks."""
    out = Text()
    for index, item in enumerate(items):
        if index:
            out.append("\n")
        out.append_text(item)
    return out


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    state = CpuState(port=args.port, baudrate=args.baud)
    link = DebugLink(args.port, args.baud, timeout=args.timeout)

    try:
        await link.open()
    except PortUnavailable as exc:
        report_port_error(exc, args.port)
        return 1

    state.connected = True
    state.status = "Conectado"

    try:
        await interactive_loop(link, state)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrumpido por el usuario.[/yellow]")
    finally:
        await link.close()

    console.print("[dim]Puerto cerrado. Hasta luego.[/dim]")
    return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
