#!/usr/bin/env python3
"""
Step the board one cycle at a time and print the pipeline latches.

The hardware equivalent of the cycle trace in tools/test_pipeline.py: it makes
it possible to compare the real processor against the model cycle by cycle,
which is the only way to tell a model bug from a hardware bug apart.

    python3 board_trace.py --port /dev/ttyUSB1 --program ../examples/test_branch.s --steps 30
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_test import NOP, ends_in_self_loop                       # noqa: E402
from riscv_debug import DebugLink                                   # noqa: E402
from riscv_debug.protocol import ABI_NAMES, decode_control          # noqa: E402
from riscv_debug.riscv_assembler import disassemble, load_file      # noqa: E402

# Latch ids we care about for following an instruction (see top.v).
IFID_PC, IFID_PC4, IFID_INSTR = 1, 2, 3
IDEX_PC, IDEX_PC4, IDEX_CTRL, IDEX_RD = 4, 5, 7, 13
MEMWB_CTRL, MEMWB_RES, MEMWB_PC4, MEMWB_RD = 22, 24, 25, 26


async def main() -> int:
    parser = argparse.ArgumentParser(description="Cycle by cycle trace of the board.")
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--pad", type=int, default=4)
    parser.add_argument("--watch", type=int, default=1,
                        help="register to print every cycle (default x1 = ra)")
    args = parser.parse_args()

    link = DebugLink(args.port, args.baud, timeout=2.0)
    await link.open()
    try:
        program = load_file(args.program)
        words = list(program.words)
        if ends_in_self_loop(words):
            words = words[:-1]
        await link.load_program(words + [NOP] * args.pad)

        w = args.watch
        print(f"\nciclo | IF/ID pc   instr          | ID/EX pc     pc+4       rd  "
              f"| MEM/WB pc+4     rd   ctrl        | x{w} {ABI_NAMES[w]}")
        print("-" * 125)
        for cycle in range(args.steps):
            ifid_pc = await link.read_latch(IFID_PC)
            ifid_in = await link.read_latch(IFID_INSTR)
            idex_pc = await link.read_latch(IDEX_PC)
            idex_p4 = await link.read_latch(IDEX_PC4)
            idex_rd = await link.read_latch(IDEX_RD)
            wb_ctrl = await link.read_latch(MEMWB_CTRL)
            wb_pc4 = await link.read_latch(MEMWB_PC4)
            wb_rd = await link.read_latch(MEMWB_RD)
            watched = await link.read_register(w)

            print(f"  {cycle:2d}  | 0x{ifid_pc:08X} {disassemble(ifid_in):<6} "
                  f"0x{ifid_in:08X} | 0x{idex_pc:08X} 0x{idex_p4:08X} x{idex_rd:<2} "
                  f"| 0x{wb_pc4:08X} x{wb_rd:<3} {decode_control(wb_ctrl, 3):<11} "
                  f"| 0x{watched:08X}")
            await link.step()
        return 0
    finally:
        await link.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
