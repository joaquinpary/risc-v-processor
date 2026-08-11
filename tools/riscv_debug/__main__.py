"""
Dashboard TUI para el procesador RISC-V segmentado.

Uso:
    python -m riscv_debug --port /dev/ttyUSB0
    python -m riscv_debug --port COM3 --baud 9600

El bucle principal es asíncrono; la E/S serie (bloqueante) corre en threads y la
entrada del usuario también, así que la interfaz nunca se traba esperando a la
placa.
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

#: Palabras de la memoria de instrucciones (instruction_memory: addrb = pc[11:2]).
IMEM_WORDS = 1024

console = Console()


# ----------------------------------------------------------------------
# Operaciones sobre la placa
# ----------------------------------------------------------------------
async def refresh_state(link: DebugLink, state: CpuState) -> None:
    """
    Relee el PC y los 32 registros, actualizando la pantalla a medida que llegan.

    Cada registro se pide por separado (el protocolo no tiene lectura en bloque),
    así que se ve la tabla llenarse en vivo.
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
    """Avanza un ciclo de reloj y relee todo el estado."""
    await link.step()
    state.cycles += 1
    await refresh_state(link, state)


async def do_run(link: DebugLink, state: CpuState) -> None:
    """
    Arranca la ejecución libre y espera a que la CPU frene.

    Mientras está en RUNNING el debug_unit no atiende la UART, así que se
    detecta el fin sondeando: la primera respuesta a un REQ_PC significa que
    volvió a IDLE (o sea, se activó cpu_halted).
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

    state.cycles = 0  # la cuenta de ciclos manual pierde sentido tras un RUN
    await refresh_state(link, state)
    state.status = "Detenido (halt)"


async def do_reset(link: DebugLink, state: CpuState) -> None:
    """Reinicia la CPU y limpia la vista."""
    await link.reset()
    state.reset_values()
    await refresh_state(link, state)
    state.status = "Reiniciado"


async def do_load_program(link: DebugLink, state: CpuState) -> None:
    """
    Ensambla un archivo .s/.asm/.hex y lo carga en la memoria de instrucciones.

    Al terminar manda un RESET (incluido en link.load_program) para dejar el PC
    en 0 y el pipeline listo, y relee el estado.
    """
    raw = await asyncio.to_thread(
        Prompt.ask, "[cyan]Archivo[/cyan] (.s / .asm / .hex)"
    )
    path = Path(raw.strip().strip('"').strip("'")).expanduser()

    # ---- Ensamblado ----
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

    # ---- Vista previa ----
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

    # Avisos: instrucciones que se codifican bien pero esta CPU no ejecuta
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

    # ---- Envío con barra de progreso ----
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
    """Lee una palabra de la memoria de datos (puerto B, no frena la CPU)."""
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
# Bucle principal
# ----------------------------------------------------------------------
async def interactive_loop(link: DebugLink, state: CpuState) -> None:
    """Dibuja el dashboard y atiende el menú hasta que el usuario salga."""
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
            # Se perdió el puerto (placa desenchufada, por ejemplo).
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
    """Muestra el error de conexión junto con los puertos que sí existen."""
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
    """Une varios Text en uno solo separado por saltos de línea."""
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
