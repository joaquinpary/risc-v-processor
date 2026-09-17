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
    state.status = "Reading state..."

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

            if state.show_latches:
                async for latch_id, value in link.read_all_latches():
                    state.set_latch(latch_id, value)
                    live.update(render_dashboard(state, show_menu=False))

        except (ResponseTimeout, ProtocolError) as exc:
            state.last_error = f"Incomplete read: {exc}"
            state.status = "Communication error"
            await link.resync()
            return

    state.last_error = None
    state.status = "Stopped"


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
    state.status = "Running..."
    console.print(
        Panel(
            Text(
                "Free run in progress. The board does not respond to requests "
                "until cpu_halted activates.",
                style="yellow",
            ),
            border_style="yellow",
        )
    )

    await link.run()

    with console.status("[yellow]Waiting for the processor to halt...", spinner="dots"):
        halted = await link.wait_until_halted()

    if not halted:
        state.status = "No response (still running?)"
        state.last_error = (
            "The CPU did not return to IDLE. The program may not end in a "
            "null instruction, or cpu_halted may never activate."
        )
        return

    state.cycles = 0  # the manual cycle count makes no sense after a RUN
    await refresh_state(link, state)
    state.status = "Stopped (halt)"


async def do_reset(link: DebugLink, state: CpuState) -> None:
    """Restarts the CPU and clears the view."""
    await link.reset()
    state.reset_values()
    await refresh_state(link, state)
    state.status = "Reset"


#: Extensions the dashboard offers to load.
PROGRAM_SUFFIXES = (".s", ".asm", ".hex")


def discover_programs() -> list[Path]:
    """
    Programs the dashboard can offer without the user typing a path.

    Looks in the examples directory of the checkout and in the directory the
    dashboard was launched from, so it works both from inside the repo and
    from anywhere else. Duplicates are dropped by resolved path.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    roots = [repo_root / "examples", Path.cwd(), Path.cwd() / "examples"]

    found: dict[Path, None] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if path.is_file() and path.suffix.lower() in PROGRAM_SUFFIXES:
                found[path.resolve()] = None
    return list(found)


def _short_path(path: Path) -> str:
    """Path with the home directory collapsed to ~, to keep the table narrow."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _program_size(path: Path) -> str:
    """Instruction count, or '?' if the file does not assemble."""
    try:
        return str(len(load_file(path)))
    except (AssemblerError, OSError):
        return "?"


def _ask_for_program(programs: list[Path]) -> Path | None:
    """
    Shows the programs found and asks which one to load.

    Blocking on purpose: the caller runs it in a thread, like every other
    prompt here. Returns None if the user cancels.
    """
    if programs:
        # Almost always every program sits in the same directory. Repeating it
        # on each row only pushes the useful columns off the screen, so it goes
        # in the subtitle and the column appears only when they really differ.
        directories = {path.parent for path in programs}
        one_place = len(directories) == 1

        table = Table(show_header=True, header_style="bold magenta", box=None,
                      pad_edge=False, padding=(0, 2))
        table.add_column("#", style="bold cyan", justify="right")
        table.add_column("Program")
        table.add_column("Instr", justify="right")
        if not one_place:
            table.add_column("Directory", style="dim")

        for index, path in enumerate(programs, start=1):
            row = [str(index), path.name, _program_size(path)]
            if not one_place:
                row.append(_short_path(path.parent))
            table.add_row(*row)

        subtitle = f"[dim]{_short_path(directories.pop())}[/dim]" if one_place else None
        console.print(Panel(table, title="[bold]Programs found[/bold]",
                            subtitle=subtitle, border_style="cyan"))

    choices = [str(i) for i in range(1, len(programs) + 1)] + ["o", "c"]
    answer = Prompt.ask(
        "[cyan]Program[/cyan]  (number | [bold]o[/bold]ther path | [bold]c[/bold]ancel)",
        choices=choices,
        default="1" if programs else "o",
        show_choices=False,
    )

    if answer == "c":
        return None
    if answer == "o":
        raw = Prompt.ask("[cyan]Path[/cyan] (.s / .asm / .hex)", default="")
        text = raw.strip().strip('"').strip("'")
        return Path(text).expanduser() if text else None
    return programs[int(answer) - 1]


async def do_load_program(link: DebugLink, state: CpuState) -> None:
    """
    Assembles a .s/.asm/.hex file and loads it into the instruction memory.

    The file is picked from a numbered list of what is on disk, so a demo does
    not depend on typing a path correctly; typing one is still offered.

    When it finishes it sends a RESET (included in link.load_program) to leave
    the PC at 0 and the pipeline ready, and re-reads the state.
    """
    programs = await asyncio.to_thread(discover_programs)
    path = await asyncio.to_thread(_ask_for_program, programs)
    if path is None:
        return

    # ---- Assembly ----
    try:
        program = await asyncio.to_thread(load_file, path)
    except AssemblerError as exc:
        state.last_error = f"Assembly error: {exc}"
        console.print(Panel(Text(str(exc), style="bold red"),
                            title="[bold red]Assembly failed[/bold red]",
                            border_style="red"))
        await asyncio.to_thread(Prompt.ask, "[dim]Enter to go back[/dim]", default="")
        return

    if not len(program):
        state.last_error = "File has no instructions"
        return

    # ---- Preview ----
    listing = Table(show_header=True, header_style="bold magenta", box=None)
    listing.add_column("Addr", style="dim", width=8)
    listing.add_column("Word", width=10)
    listing.add_column("Source")
    for address, word, source in program.listing[:12]:
        listing.add_row(f"0x{address:04X}", f"{word:08X}", source)
    if len(program.listing) > 12:
        listing.add_row("...", "...", f"(+{len(program.listing) - 12} more)")

    console.print(Panel(
        listing,
        title=f"[bold]{path.name}[/bold] — {len(program)} instructions",
        border_style="cyan",
    ))

    # Warnings: instructions that encode fine but this CPU does not run
    if program.warnings:
        console.print(Panel(
            _stack([Text(f"• {w}", style="yellow") for w in program.warnings]),
            title="[bold yellow]Warnings[/bold yellow]",
            border_style="yellow",
        ))

    if len(program) > IMEM_WORDS:
        state.last_error = (
            f"Program does not fit: {len(program)} instructions and memory "
            f"has {IMEM_WORDS} words"
        )
        console.print(Panel(Text(state.last_error, style="bold red"),
                            border_style="red"))
        return

    confirm = await asyncio.to_thread(
        Prompt.ask, "[cyan]Load to FPGA?[/cyan]",
        choices=["y", "n"], default="y",
    )
    if confirm != "y":
        return

    # ---- Sending with a progress bar ----
    state.status = "Loading program..."
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress_bar:
        task = progress_bar.add_task(f"Sending {path.name}", total=len(program))

        def advance(sent: int, total: int) -> None:
            progress_bar.update(task, completed=sent)

        try:
            await link.load_program(program.words, progress=advance)
        except DebugLinkError as exc:
            state.last_error = f"Load failed: {exc}"
            state.status = "Load error"
            return

    state.program_name = path.name
    state.program_size = len(program)
    state.last_error = None
    state.cycles = 0
    state.reset_values()

    console.print(Panel(
        Text(f"{len(program)} instructions loaded. PC at 0x00, ready to "
             f"run (option 1 = Step, 2 = Run).", style="bold green"),
        border_style="green",
    ))

    await refresh_state(link, state)
    state.status = "Program loaded"


async def do_toggle_latches(link: DebugLink, state: CpuState) -> None:
    """
    Shows or hides the pipeline latch panel.

    Turning it on reads the latches right away, so the panel is never shown
    empty. Turning it off also stops reading them, which halves the time a
    step takes.
    """
    state.show_latches = not state.show_latches
    if state.show_latches:
        await refresh_state(link, state)


async def do_read_memory(link: DebugLink, state: CpuState) -> None:
    """Reads a word from the data memory (port B, it does not stop the CPU)."""
    raw = await asyncio.to_thread(
        Prompt.ask, "[cyan]Address[/cyan] (hex with 0x, or decimal)", default="0"
    )
    try:
        address = int(raw, 0)
    except ValueError:
        state.last_error = f"Invalid address: {raw!r}"
        return

    try:
        value = await link.read_memory(address)
    except (ResponseTimeout, ProtocolError) as exc:
        state.last_error = f"Could not read 0x{address:08X}: {exc}"
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
        "7": do_toggle_latches,
    }

    await refresh_state(link, state)

    while True:
        console.clear()
        console.print(render_dashboard(state))

        choice = await asyncio.to_thread(
            Prompt.ask,
            "[bold cyan]Option[/bold cyan]",
            choices=["1", "2", "3", "4", "5", "6", "7", "q"],
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
            state.status = "Link down"
            if not link.is_open:
                console.print(
                    Panel(
                        Text(f"Connection lost: {exc}", style="bold red"),
                        border_style="red",
                    )
                )
                return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="riscv_debug",
        description="Debug dashboard for the RISC-V processor on FPGA.",
    )
    parser.add_argument(
        "--port",
        "-p",
        required=True,
        help="Serial port (e.g. /dev/ttyUSB0 on Linux, COM3 on Windows)",
    )
    parser.add_argument("--baud", "-b", type=int, default=9600, help="Baud rate (9600)")
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=2.0,
        help="Read timeout in seconds (2.0)",
    )
    return parser.parse_args(argv)


def report_port_error(exc: PortUnavailable, requested: str) -> None:
    """Shows the connection error together with the ports that do exist."""
    lines = [Text(str(exc), style="bold red"), Text("")]

    ports = available_ports()
    if ports:
        lines.append(Text("Detected ports:", style="bold"))
        lines.extend(Text(f"  • {p}", style="cyan") for p in ports)
    else:
        lines.append(
            Text(
                "No serial port detected. Check that the board is connected "
                "and programmed.",
                style="yellow",
            )
        )
        lines.append(
            Text(
                "On Linux you may need permissions: sudo usermod -aG dialout "
                "$USER (then log back in).",
                style="dim",
            )
        )

    console.print(
        Panel(
            _stack(lines),
            title=f"[bold red]Could not connect to {requested}[/bold red]",
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
    state.status = "Connected"

    try:
        await interactive_loop(link, state)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
    finally:
        await link.close()

    console.print("[dim]Port closed. Goodbye.[/dim]")
    return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
