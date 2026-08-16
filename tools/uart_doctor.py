#!/usr/bin/env python3
"""
uart_doctor - traces and diagnoses the UART link with the FPGA.

Three modes:

    # 1. Controlled diagnosis: isolates WHICH command breaks the link
    python uart_doctor.py diagnose --port /dev/ttyUSB1

    # 2. Runs dashboard.py with every byte traced
    python uart_doctor.py trace-dashboard --port /dev/ttyUSB1

    # 3. Runs the TUI dashboard (riscv_debug) with every byte traced
    python uart_doctor.py trace-tui --port /dev/ttyUSB1

Everything is kept in a log file with timestamps (--log, uart_doctor.log by
default) besides going to the console.

The trace works by patching serial.Serial, so it records ANY script that uses
pyserial without having to modify it.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path

# Allows importing riscv_debug from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import serial  # noqa: E402

from riscv_debug.protocol import (  # noqa: E402
    ABI_NAMES,
    FRAME_SIZE,
    Command,
    MAX_REGISTER_CODE,
    ResponseKind,
)

# =====================================================================
# Log
# =====================================================================


class Log:
    """Writes to console and to file with a relative timestamp."""

    def __init__(self, path: Path | None):
        self.t0 = time.monotonic()
        self.file = path.open("w", encoding="utf-8") if path else None

    def __call__(self, text: str = "", *, quiet: bool = False) -> None:
        stamp = f"[{time.monotonic() - self.t0:9.4f}] "
        line = f"{stamp}{text}" if text else ""
        if not quiet:
            print(line, flush=True)
        if self.file:
            self.file.write(line + "\n")
            self.file.flush()

    def rule(self, title: str) -> None:
        self(f"{'=' * 12} {title} {'=' * 12}")

    def close(self) -> None:
        if self.file:
            self.file.close()


# =====================================================================
# Readable frame decoding
# =====================================================================


def describe_tx(frame: bytes) -> str:
    """Describes a frame going from the PC to the FPGA."""
    cmd, payload = frame[0], int.from_bytes(frame[1:5], "big")
    try:
        name = Command(cmd).name
    except ValueError:
        return f"!! UNKNOWN COMMAND 0x{cmd:02X} payload=0x{payload:08X}"

    if cmd == Command.REQ_REG:
        n = payload & 0x1F
        return f"REQ_REG  x{n} ({ABI_NAMES[n]})"
    if cmd == Command.REQ_MEM:
        return f"REQ_MEM  addr=0x{payload:08X}"
    if cmd == Command.REQ_LATCH:
        return f"REQ_LATCH id={payload & 0xFF}"
    if cmd == Command.LOAD_INSTR:
        return f"LOAD_INSTR 0x{payload:08X}"
    return f"{name}"


def describe_rx(frame: bytes) -> str:
    """Describes a frame coming from the FPGA."""
    code, data = frame[0], int.from_bytes(frame[1:5], "big")
    if code <= MAX_REGISTER_CODE:
        return f"REG x{code} ({ABI_NAMES[code]}) = 0x{data:08X} ({data})"
    try:
        kind = ResponseKind(code).name
    except ValueError:
        return f"!! UNKNOWN RESPONSE 0x{code:02X} data=0x{data:08X}"
    return f"{kind} = 0x{data:08X} ({data})"


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# =====================================================================
# Frame assembler: detects misalignment
# =====================================================================


class FrameAssembler:
    """
    Rebuilds 5 byte frames in one direction and keeps the running total.

    The key point: the FPGA groups the received bytes in fives with no resync
    (uart_interface.v counts rx_count modulo 5). If the total number of bytes
    we send stops being a multiple of 5 at a frame boundary, the FPGA stays
    misaligned forever.
    """

    def __init__(self, direction: str, log: Log, describe):
        self.direction = direction
        self.log = log
        self.describe = describe
        self.buffer = bytearray()
        self.total_bytes = 0
        self.frames = 0
        self.last_time: float | None = None

    def feed(self, data: bytes) -> None:
        now = time.monotonic()
        gap = "" if self.last_time is None else f" (+{(now - self.last_time) * 1000:.1f}ms)"
        self.last_time = now

        self.total_bytes += len(data)
        self.buffer.extend(data)

        while len(self.buffer) >= FRAME_SIZE:
            frame = bytes(self.buffer[:FRAME_SIZE])
            del self.buffer[:FRAME_SIZE]
            self.frames += 1
            self.log(
                f"  {self.direction} #{self.frames:<4} {hexdump(frame)}  "
                f"| {self.describe(frame)}{gap}"
            )
            gap = ""

        if self.buffer:
            self.log(
                f"  {self.direction} .... {hexdump(self.buffer)}  "
                f"| PARTIAL ({len(self.buffer)}/5 bytes in buffer){gap}"
            )

    @property
    def aligned(self) -> bool:
        return self.total_bytes % FRAME_SIZE == 0

    def report(self) -> str:
        state = "aligned" if self.aligned else f"MISALIGNED (remainder {self.total_bytes % FRAME_SIZE})"
        return f"{self.direction}: {self.total_bytes} bytes, {self.frames} frames, {state}"


# =====================================================================
# Instrumented serial.Serial
# =====================================================================

_RealSerial = serial.Serial
_tracers: list["TracedSerial"] = []


def make_traced_serial(log: Log, force_port: str | None = None,
                       force_baud: int | None = None):
    """
    Returns a serial.Serial subclass that logs all the traffic.

    force_port/force_baud override whatever the traced script asks for:
    dashboard.py has the port hardcoded, so without this --port would have no
    effect.
    """

    class TracedSerial(_RealSerial):
        def __init__(self, *args, **kwargs):
            if force_port is not None:
                if args:  # port as the first positional argument
                    args = (force_port,) + args[1:]
                kwargs["port"] = force_port
            if force_baud is not None:
                kwargs["baudrate"] = force_baud
            super().__init__(*args, **kwargs)
            self._log = log
            self.tx = FrameAssembler("TX", log, describe_tx)
            self.rx = FrameAssembler("RX", log, describe_rx)
            _tracers.append(self)
            log(
                f"OPEN  {self.port} @{self.baudrate} "
                f"{self.bytesize}{self.parity}{self.stopbits} timeout={self.timeout}"
            )

        def write(self, data):
            written = super().write(data)
            if written is not None and written != len(data):
                self._log(f"  !! PARTIAL WRITE: {written}/{len(data)} bytes")
            self.tx.feed(bytes(data))
            return written

        def read(self, size=1):
            t0 = time.monotonic()
            data = super().read(size)
            elapsed = (time.monotonic() - t0) * 1000
            if len(data) < size:
                self._log(
                    f"  !! TIMEOUT: requested {size} bytes, got "
                    f"{len(data)} after {elapsed:.0f}ms"
                )
            if data:
                self.rx.feed(data)
            return data

        def reset_input_buffer(self):
            pending = self.in_waiting
            if pending:
                stale = super().read(pending)
                self._log(
                    f"  !! DISCARDED {len(stale)} stale bytes from buffer: "
                    f"{hexdump(stale)}"
                )
                self.rx.total_bytes += len(stale)
            return super().reset_input_buffer()

        def close(self):
            if self.is_open:
                self._log(f"CLOSE {self.port}")
                self._log(f"  {self.tx.report()}")
                self._log(f"  {self.rx.report()}")
            return super().close()

    return TracedSerial


def install_tracer(log: Log, port: str | None = None,
                   baud: int | None = None) -> None:
    """Patches serial.Serial so any script becomes instrumented."""
    serial.Serial = make_traced_serial(log, port, baud)
    log(f"Tracer installed on serial.Serial (forcing port {port})")


def summarize_tracers(log: Log) -> None:
    for tracer in _tracers:
        log(tracer.tx.report())
        log(tracer.rx.report())
        if not tracer.tx.aligned:
            log(
                "  !! Total bytes sent is NOT a multiple of 5: the FPGA "
                "stays misaligned and cannot recover without reset "
                "(uart_interface.v has no resync)."
            )


# =====================================================================
# Mode 1: controlled diagnosis
# =====================================================================


class Probe:
    """Sends raw commands and measures the answer, with no abstraction."""

    def __init__(self, port: str, baud: int, timeout: float, log: Log):
        self.log = log
        self.timeout = timeout
        try:
            # exclusive=True makes opening the port twice fail instead of
            # silently corrupting the stream (POSIX only).
            self.ser = _RealSerial(
                port=port, baudrate=baud, timeout=timeout, exclusive=True
            )
        except TypeError:
            self.ser = _RealSerial(port=port, baudrate=baud, timeout=timeout)
        except serial.SerialException as exc:
            raise SystemExit(
                f"Could not open {port}: {exc}\n"
                "If it says 'device reports readiness'/'Resource busy', another "
                "process has the port open (dashboard.py running?)."
            )
        self.tx_total = 0

    def drain(self, label: str = "") -> bytes:
        """Empties the input buffer and reports what was there (orphan bytes)."""
        time.sleep(0.2)
        pending = self.ser.in_waiting
        if not pending:
            return b""
        stale = self.ser.read(pending)
        self.log(
            f"  !! {len(stale)} orphan bytes in buffer {label}: {hexdump(stale)}"
        )
        return stale

    def send(self, cmd: int, payload: int = 0) -> None:
        frame = bytes([cmd]) + payload.to_bytes(4, "big")
        self.ser.write(frame)
        self.ser.flush()
        self.tx_total += len(frame)
        self.log(f"  TX {hexdump(frame)}  | {describe_tx(frame)}")

    def expect(self, timeout: float | None = None) -> bytes | None:
        """Reads a frame and reports it. Returns None on timeout."""
        self.ser.timeout = timeout or self.timeout
        t0 = time.monotonic()
        data = self.ser.read(FRAME_SIZE)
        elapsed = (time.monotonic() - t0) * 1000
        self.ser.timeout = self.timeout

        if len(data) == FRAME_SIZE:
            self.log(f"  RX {hexdump(data)}  | {describe_rx(data)}  ({elapsed:.0f}ms)")
            return data
        self.log(
            f"  RX -- NO RESPONSE: {len(data)}/5 bytes after {elapsed:.0f}ms"
            + (f"  partial={hexdump(data)}" if data else "")
        )
        return None

    def ping(self, timeout: float | None = None) -> bool:
        """REQ_PC as a liveness check."""
        self.send(Command.REQ_PC)
        return self.expect(timeout) is not None

    def try_realign(self) -> int | None:
        """
        Tries to resync the FPGA by sending padding bytes.

        Since it groups in fives with no resync, if it was left shifted by k
        bytes, sending (5-k) extra bytes completes the ghost frame and
        realigns. Returns how many bytes were needed in total, or None if it
        did not recover.

        ONE byte is sent per round, so the accumulated padding walks 1,2,3,4
        and covers the four possible shifts. (Sending `padding` bytes per round
        would accumulate 1,3,6,10 == 1,3,1,0 mod 5 and would never test +2
        or +4.)
        """
        self.log("  Trying resync with padding bytes...")
        for total in range(1, FRAME_SIZE):
            self.ser.write(b"\x00")
            self.ser.flush()
            self.tx_total += 1
            self.drain("(after padding)")
            self.log(f"    accumulated padding of {total} byte(s) -> trying REQ_PC")
            if self.ping(timeout=1.0):
                self.log(f"  ==> RECOVERED with {total} byte(s) of padding")
                return total
        self.log("  ==> Did not recover with any padding (tried +1,+2,+3,+4)")
        return None

    def close(self) -> None:
        self.ser.close()


def diagnose(port: str, baud: int, timeout: float, log: Log) -> int:
    """
    Controlled sequence that isolates which command breaks the link.

    After every action it does a REQ_PC liveness check; the first failure names
    the culprit, and there the resync is attempted to tell apart "misaligned
    FPGA" from "hung FSM".
    """
    probe = Probe(port, baud, timeout, log)
    verdict = 0

    try:
        log.rule("0. Initial state")
        stale = probe.drain("on open (leftover from previous session)")
        if stale:
            log(
                "  NOTE: there were unread bytes. If not a multiple of 5, the "
                "previous session left the FPGA misaligned."
            )

        log.rule("1. Liveness check (10 x REQ_PC consecutive)")
        alive = 0
        for i in range(10):
            if probe.ping():
                alive += 1
            else:
                log(f"  !! died on attempt {i + 1}")
                break
        log(f"  {alive}/10 responses")
        if alive == 0:
            log("  The link was already dead before sending any command.")
            if probe.try_realign() is None:
                log(
                    "  DIAGNOSIS: FPGA does not respond even after resync. "
                    "Its FSM is hung (probably in RUNNING waiting for "
                    "cpu_halted, or in SEND_RESP waiting for tx_busy). "
                    "The board must be reprogrammed or the physical reset pressed."
                )
                return 2
            log("  DIAGNOSIS: it was MISALIGNED, not hung.")

        log.rule("2. Full register sweep (33 exchanges)")
        ok = 0
        probe.send(Command.REQ_PC)
        if probe.expect():
            ok += 1
        for n in range(32):
            probe.send(Command.REQ_REG, n)
            if probe.expect():
                ok += 1
            else:
                log(f"  !! died reading x{n} (exchange {ok + 1})")
                break
        log(f"  {ok}/33 complete exchanges")
        if ok < 33:
            verdict = 1
            probe.try_realign()

        log.rule("3. STEP command, then liveness check")
        probe.send(Command.STEP)
        time.sleep(0.2)
        probe.drain("(STEP should not respond)")
        if probe.ping():
            log("  OK: link survives STEP")
        else:
            log("  !! LINK DIED AFTER STEP")
            verdict = 1
            if probe.try_realign() is None:
                log(
                    "  DIAGNOSIS: STEP hangs the FSM. With cpu_enable high for one "
                    "cycle the pipeline advances; check if something in the datapath "
                    "prevents debug_unit from returning to IDLE."
                )
                return 2

        log.rule("4. RESET command, then liveness check")
        probe.send(Command.RESET)
        time.sleep(0.2)
        probe.drain("(RESET should not respond)")
        if probe.ping():
            log("  OK: link survives RESET")
        else:
            log("  !! LINK DIED AFTER RESET")
            verdict = 1
            if probe.try_realign() is None:
                return 2

        log.rule("5. RUN command, then poll until it stops")
        probe.send(Command.RUN)
        log("  Polling REQ_PC (FPGA ignores UART while running)...")
        deadline = time.monotonic() + 10.0
        recovered = False
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            if probe.ping(timeout=0.5):
                recovered = True
                break
        if recovered:
            log(f"  OK: stopped and responded after {attempts} polls")
        else:
            log("  !! NEVER CAME BACK after RUN (10 s)")
            verdict = 1
            log(
                "  PROBABLE DIAGNOSIS: cpu_halted never activates, so "
                "debug_unit stays in RUNNING forever ignoring the UART. "
                "cpu_halted = (instruction_id == 0 && pc_if > 0x10): if the "
                "program does not end in null instructions, or the pipeline "
                "is stalled with PC below 0x10, it never triggers. "
                "This is a hang that cannot be recovered via UART: reprogramming is required."
            )
            if probe.try_realign() is None:
                return 2

        log.rule("Summary")
        log(f"  Total bytes sent: {probe.tx_total} "
            f"({'multiple of 5, aligned' if probe.tx_total % 5 == 0 else 'NOT multiple of 5'})")
        if verdict == 0:
            log("  The link survived the entire sequence.")
        return verdict

    except KeyboardInterrupt:
        log("Interrupted by user")
        return 130
    finally:
        probe.close()


# =====================================================================
# Modes 2 and 3: run another script under trace
# =====================================================================


def trace_dashboard(port: str, baud: int, log: Log) -> int:
    """Runs dashboard.py (the one at the repo root) with the trace on."""
    script = Path(__file__).resolve().parent.parent / "dashboard.py"
    if not script.exists():
        log(f"Cannot find {script}")
        return 1

    install_tracer(log, port, baud)
    log.rule(f"Running {script.name}")
    sys.argv = [str(script)]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001 - we want to see any failure
        log(f"!! Script terminated with exception: {exc!r}")
    finally:
        log.rule("Trace summary")
        summarize_tracers(log)
    return 0


def trace_tui(port: str, baud: int, log: Log) -> int:
    """Runs the TUI dashboard (riscv_debug) with the trace on."""
    install_tracer(log, port, baud)
    log.rule("Running riscv_debug")
    from riscv_debug.__main__ import main as tui_main

    sys.argv = ["riscv_debug", "--port", port, "--baud", str(baud)]
    try:
        tui_main()
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001
        log(f"!! Dashboard terminated with exception: {exc!r}")
    finally:
        log.rule("Trace summary")
        summarize_tracers(log)
    return 0


# =====================================================================
# CLI
# =====================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="uart_doctor",
        description="Traces and diagnoses the UART link with the FPGA.",
    )
    parser.add_argument(
        "mode",
        choices=["diagnose", "trace-dashboard", "trace-tui"],
        help="diagnose: controlled sequence; trace-*: runs script under trace",
    )
    parser.add_argument("--port", "-p", required=True)
    parser.add_argument("--baud", "-b", type=int, default=9600)
    parser.add_argument("--timeout", "-t", type=float, default=2.0)
    parser.add_argument("--log", "-l", default="uart_doctor.log")
    args = parser.parse_args()

    log = Log(Path(args.log) if args.log else None)
    log(f"uart_doctor — mode {args.mode} — port {args.port} @ {args.baud}")
    log(f"log: {args.log}")
    log()

    try:
        if args.mode == "diagnose":
            return diagnose(args.port, args.baud, args.timeout, log)
        if args.mode == "trace-dashboard":
            return trace_dashboard(args.port, args.baud, log)
        return trace_tui(args.port, args.baud, log)
    finally:
        log()
        log(f"Full log at: {Path(args.log).resolve()}")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
