"""
Transport layer: serial port + protocol, exposed as an async API.

pyserial is blocking, so every I/O operation runs in a separate thread with
``asyncio.to_thread``. An ``asyncio.Lock`` serializes the access so two
concurrent commands cannot interleave their 5 byte frames.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import serial
from serial.tools import list_ports

from .protocol import (
    ACTION_COMMANDS,
    FRAME_SIZE,
    LATCH_FIELDS,
    REGISTER_COUNT,
    Command,
    Frame,
    ProtocolError,
    ResponseKind,
    decode,
    encode,
)


class DebugLinkError(Exception):
    """Base error of the connection with the board."""


class PortUnavailable(DebugLinkError):
    """The port does not exist, is busy or cannot be opened."""


class ResponseTimeout(DebugLinkError):
    """The FPGA did not answer within the expected time."""


class DebugLink:
    """
    Connection with the debug_unit of the FPGA.

    Usage:

        link = DebugLink("/dev/ttyUSB0")
        await link.open()
        try:
            await link.step()
            pc = await link.read_pc()
        finally:
            await link.close()
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def open(self) -> None:
        """
        Opens the port. Raises PortUnavailable if it cannot.

        Exclusive access is requested (POSIX only): if another process already
        has the port open, it fails here with a clear error instead of sharing
        the stream and stealing bytes from each other, which desyncs the
        protocol beyond recovery (the FPGA has no frame resync).
        """
        options = dict(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )
        try:
            try:
                self._serial = await asyncio.to_thread(
                    serial.Serial, exclusive=True, **options
                )
            except TypeError:
                # Windows: pyserial does not support exclusive
                self._serial = await asyncio.to_thread(serial.Serial, **options)
        except (serial.SerialException, ValueError, OSError) as exc:
            raise PortUnavailable(
                f"Could not open {self.port} at {self.baudrate} baud: {exc}"
            ) from exc

        # Drop stale bytes from a previous session.
        await asyncio.to_thread(self._serial.reset_input_buffer)
        await asyncio.to_thread(self._serial.reset_output_buffer)

    async def close(self) -> None:
        """Closes the port if it is open (idempotent)."""
        if self._serial is not None and self._serial.is_open:
            await asyncio.to_thread(self._serial.close)
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    async def __aenter__(self) -> "DebugLink":
        await self.open()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Transport primitives
    # ------------------------------------------------------------------
    def _require_port(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise PortUnavailable("Port is not open")
        return self._serial

    async def _write_frame(self, command: int, payload: int) -> None:
        port = self._require_port()
        try:
            await asyncio.to_thread(port.write, encode(command, payload))
            await asyncio.to_thread(port.flush)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Failed to write to {self.port}: {exc}") from exc

    async def _read_frame(self, timeout: float | None = None) -> Frame:
        port = self._require_port()
        if timeout is not None:
            port.timeout = timeout
        try:
            raw = await asyncio.to_thread(port.read, FRAME_SIZE)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Failed to read from {self.port}: {exc}") from exc
        finally:
            port.timeout = self.timeout

        if len(raw) < FRAME_SIZE:
            raise ResponseTimeout(
                f"Incomplete response: {len(raw)}/{FRAME_SIZE} bytes"
            )
        return decode(raw)

    async def resync(self) -> None:
        """
        Drops whatever is in the input buffer.

        Useful to recover from a timeout: if an answer arrived late, it would
        be misaligned with the next request.

        CAREFUL: this only cleans the PC side. If the one left misaligned is
        the FPGA, realign() is needed.
        """
        if self._serial is not None and self._serial.is_open:
            await asyncio.to_thread(self._serial.reset_input_buffer)

    async def realign(self) -> int | None:
        """
        Tries to resync the FPGA by sending padding bytes.

        uart_interface.v groups the received bytes in fives with no idle
        detection between frames, so if the stream loses alignment the FPGA
        misreads everything forever. Since the shift is modulo 5, sending
        (5-k) extra bytes completes the ghost frame and realigns; we try 1 to 4
        until it answers. ONE byte is sent per round so the running total walks
        1,2,3,4 and covers the four shifts (sending `padding` bytes per round
        would give 1,3,6,10, which mod 5 leaves +2 and +4 untested).

        Returns how many padding bytes were needed, or None if it did not
        recover (in that case the FPGA FSM is hung and it has to be
        reprogrammed or reset by hardware).
        """
        for total in range(1, FRAME_SIZE):
            async with self._lock:
                await self._write_frame_raw(b"\x00")
            await self.resync()
            try:
                await self.read_pc(timeout=1.0)
                return total
            except (ResponseTimeout, ProtocolError):
                continue
        return None

    async def _write_frame_raw(self, data: bytes) -> None:
        """Writes raw bytes (used by the resync)."""
        port = self._require_port()
        try:
            await asyncio.to_thread(port.write, data)
            await asyncio.to_thread(port.flush)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Failed to write to {self.port}: {exc}") from exc

    # ------------------------------------------------------------------
    # Action commands (no answer)
    # ------------------------------------------------------------------
    async def _send_action(self, command: Command, payload: int = 0) -> None:
        assert command in ACTION_COMMANDS
        async with self._lock:
            await self._write_frame(command, payload)

    async def step(self) -> None:
        """Advances the processor one clock cycle."""
        await self._send_action(Command.STEP)

    async def run(self) -> None:
        """
        Starts the free run.

        Careful: while in RUNNING the debug_unit ignores the UART, so it does
        not answer any request until cpu_halted brings it back to IDLE.
        See wait_until_halted().
        """
        await self._send_action(Command.RUN)

    async def reset(self) -> None:
        """Restarts the CPU and the instruction load pointer."""
        await self._send_action(Command.RESET)

    async def load_instruction(self, word: int) -> None:
        """Writes one instruction to memory (the address auto-increments)."""
        await self._send_action(Command.LOAD_INSTR, word)

    async def load_program(self, words: list[int], progress=None,
                           settle: float = 0.01) -> None:
        """
        Loads a whole program into the instruction memory.

        Sequence: RESET (which also zeroes the imem write pointer) -> one
        LOAD_INSTR frame per instruction -> a final RESET to leave the PC at 0
        and the pipeline clean.

        Careful: the firmware does NOT receive the address; `debug_unit`
        auto-increments `imem_addr_reg` on every LOAD_INSTR. That is why the
        first RESET is not optional: it is the only thing that rewinds the
        pointer.

        `progress` is an optional callable that receives (sent, total).
        `settle` is the pause between frames: LOAD_INSTR answers nothing, so
        without a pause we can run over the debug_unit while it is working.
        """
        total = len(words)
        await self.reset()
        await asyncio.sleep(0.1)

        for index, word in enumerate(words, start=1):
            await self.load_instruction(word)
            if settle:
                await asyncio.sleep(settle)
            if progress:
                progress(index, total)

        await asyncio.sleep(0.1)
        await self.reset()
        await asyncio.sleep(0.1)

    # ------------------------------------------------------------------
    # Read commands (with an answer)
    # ------------------------------------------------------------------
    async def _request(
        self,
        command: Command,
        payload: int,
        expected_code: int,
        timeout: float | None = None,
    ) -> int:
        """Sends a request and checks that the response code is the right one."""
        async with self._lock:
            await self._write_frame(command, payload)
            frame = await self._read_frame(timeout)

        if frame.code != expected_code:
            await self.resync()
            raise ProtocolError(
                f"Unexpected response to {command.name}: expected code "
                f"0x{expected_code:02X}, got 0x{frame.code:02X}"
            )
        return frame.payload

    async def read_register(self, number: int) -> int:
        """
        Reads one register from the register file.

        The debug_unit answers using the register number itself as the code, so
        it works as an acknowledgement: if we ask for x5 and it answers x6,
        something got out of sync.
        """
        if not 0 <= number < REGISTER_COUNT:
            raise ValueError(f"Register out of range: {number}")
        return await self._request(Command.REQ_REG, number, expected_code=number)

    async def read_pc(self, timeout: float | None = None) -> int:
        """Reads the current Program Counter."""
        return await self._request(
            Command.REQ_PC, 0, expected_code=ResponseKind.PC, timeout=timeout
        )

    async def read_memory(self, address: int) -> int:
        """Reads a word from the data memory (port B, it does not disturb the CPU)."""
        return await self._request(
            Command.REQ_MEM, address, expected_code=ResponseKind.MEM
        )

    async def read_latch(self, latch_id: int) -> int:
        """Reads a pipeline latch (see the debug_latch_id case in top.v)."""
        return await self._request(
            Command.REQ_LATCH, latch_id, expected_code=ResponseKind.LATCH
        )

    async def read_all_registers(self) -> AsyncIterator[tuple[int, int]]:
        """
        Reads the 32 registers. Returns a generator of (number, value).

        At 9600 baud each register is 10 bytes (5 out + 5 back), ~8.3 ms; the
        32 of them take around 270 ms.
        """
        for number in range(REGISTER_COUNT):
            yield number, await self.read_register(number)

    async def read_all_latches(self) -> AsyncIterator[tuple[int, int]]:
        """
        Reads every pipeline latch field. Yields (latch id, value).

        Same cost per field as a register, so the 26 fields add roughly
        220 ms at 9600 baud on top of a register sweep.
        """
        for latch in LATCH_FIELDS:
            yield latch.id, await self.read_latch(latch.id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def wait_until_halted(
        self,
        poll_timeout: float = 0.4,
        overall_timeout: float = 30.0,
    ) -> bool:
        """
        Waits for the CPU to finish the free run.

        Trick: during RUNNING the debug_unit does not listen to the UART, so a
        REQ_PC with no answer means "still running" and an answer means "back
        in IDLE", that is, cpu_halted went active.

        Returns True if it stopped, False if overall_timeout ran out.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + overall_timeout

        while loop.time() < deadline:
            try:
                await self.read_pc(timeout=poll_timeout)
                return True
            except (ResponseTimeout, ProtocolError):
                await self.resync()
        return False


def available_ports() -> list[str]:
    """Lists the detected serial ports, to suggest them if the connection fails."""
    return [p.device for p in list_ports.comports()]
