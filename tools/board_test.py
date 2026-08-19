#!/usr/bin/env python3
"""
Headless board runner: load a program, advance it, dump the state.

The dashboard is a TUI and needs a keyboard, so it is useless over SSH or in
a script. This does the same job without a screen, which is what a test run
or a remote session needs.

    python3 board_test.py --port /dev/ttyUSB1 --program ../examples/test_alu.s --steps 25
    python3 board_test.py --port /dev/ttyUSB1 --program prog.s --run --json

Careful with --run: the processor stops when a zero word reaches ID, but the
instructions behind it still need a few cycles to retire, so the last ones are
lost. Worse, a program that never reaches a zero word leaves debug_unit stuck
in RUNNING ignoring the UART, and only reprogramming the board gets it back.
That is what --pad is for: it appends NOPs so the pipeline drains and the halt
always triggers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from riscv_debug import DebugLink                                   # noqa: E402
from riscv_debug.protocol import (                                  # noqa: E402
    ABI_NAMES,
    LATCH_FIELDS,
    decode_control,
    to_signed,
)
from riscv_debug.riscv_assembler import disassemble, load_file      # noqa: E402

NOP = 0x00000013


def branch_offset(word: int) -> int:
    """Byte offset of a B-type instruction, sign extended."""
    imm = (((word >> 31) & 1) << 12 | ((word >> 7) & 1) << 11
           | ((word >> 25) & 0x3F) << 5 | ((word >> 8) & 0xF) << 1)
    return imm - 0x2000 if imm & 0x1000 else imm


def ends_in_self_loop(words: list[int]) -> bool:
    """True if the last instruction is a branch to itself.

    A program that parks in `FIN: beq zero, zero, FIN` never reaches a zero
    word, so cpu_halted never fires and RUN leaves debug_unit deaf. It only
    seemed to work before because the word after the branch was zero and got
    fetched on the wrong path; padding with NOPs takes that away.
    """
    return bool(words) and (words[-1] & 0x7F) == 0x63 and branch_offset(words[-1]) == 0


async def collect(link: DebugLink) -> dict:
    """One full snapshot: PC, the 32 registers and every latch field."""
    state = {"pc": await link.read_pc(), "registers": {}, "latches": {}}
    async for number, value in link.read_all_registers():
        state["registers"][number] = value
    async for latch_id, value in link.read_all_latches():
        state["latches"][latch_id] = value
    return state


def show(state: dict) -> None:
    print(f"\nPC = 0x{state['pc']:08X}  (word {state['pc'] // 4})")

    print("\nRegisters that are not zero:")
    nonzero = {n: v for n, v in state["registers"].items() if v}
    if not nonzero:
        print("  (all zero)")
    for number, value in sorted(nonzero.items()):
        print(f"  x{number:<2} {ABI_NAMES[number]:<5} 0x{value:08X}  {to_signed(value)}")

    print("\nPipeline latches:")
    for latch in LATCH_FIELDS:
        value = state["latches"][latch.id]
        extra = ""
        if latch.kind == "instr":
            extra = f"  {disassemble(value)}"
        elif latch.kind.startswith("ctrl"):
            width = {"ctrl10": 10, "ctrl7": 7, "ctrl3": 3}[latch.kind]
            extra = f"  {decode_control(value, width)}"
        elif latch.kind == "reg":
            extra = f"  x{value & 0x1F} {ABI_NAMES[value & 0x1F]}"
        print(f"  {latch.stage:<7} {latch.label:<7} 0x{value:08X}{extra}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a program on the board without a TUI.")
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--program", type=Path, help=".s/.asm/.hex to load (optional)")
    parser.add_argument("--steps", type=int, default=0, help="how many STEP commands to send")
    parser.add_argument("--run", action="store_true", help="free run until the CPU halts")
    parser.add_argument("--pad", type=int, default=4,
                        help="NOPs appended to the program so the pipeline drains (default 4)")
    parser.add_argument("--keep-loop", action="store_true",
                        help="do not drop a trailing branch-to-itself before a --run")
    parser.add_argument("--json", action="store_true", help="dump the snapshot as JSON")
    args = parser.parse_args()

    link = DebugLink(args.port, args.baud, timeout=2.0)
    await link.open()
    try:
        if args.program:
            program = load_file(args.program)
            for warning in program.warnings:
                print(f"WARNING: {warning}")
            words = list(program.words)
            if args.run and not args.keep_loop and ends_in_self_loop(words):
                print("NOTE: dropping the trailing infinite loop so the CPU can halt "
                      "(use --keep-loop to leave it).")
                words = words[:-1]
            words = words + [NOP] * args.pad
            print(f"Loading {args.program.name}: {len(words) - args.pad} instructions "
                  f"+ {args.pad} NOP")
            await link.load_program(words)
        else:
            await link.reset()

        if args.run:
            await link.run()
            if await link.wait_until_halted():
                print("Halted.")
            else:
                print("WARNING: it never went back to IDLE. The board is stuck in "
                      "RUNNING and needs reprogramming.")
                return 2
        for _ in range(args.steps):
            await link.step()
        if args.steps:
            print(f"{args.steps} STEP sent.")

        state = await collect(link)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            show(state)
        return 0
    finally:
        await link.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
