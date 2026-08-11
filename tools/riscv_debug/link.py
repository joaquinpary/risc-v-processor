"""
Capa de transporte: puerto serie + protocolo, expuesto como API asíncrona.

pyserial es bloqueante, así que cada operación de E/S se corre en un thread
aparte con ``asyncio.to_thread``. Un ``asyncio.Lock`` serializa el acceso para
que dos comandos concurrentes no intercalen sus tramas de 5 bytes.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import serial
from serial.tools import list_ports

from .protocol import (
    ACTION_COMMANDS,
    FRAME_SIZE,
    REGISTER_COUNT,
    Command,
    Frame,
    ProtocolError,
    ResponseKind,
    decode,
    encode,
)


class DebugLinkError(Exception):
    """Error base de la conexión con la placa."""


class PortUnavailable(DebugLinkError):
    """El puerto no existe, está ocupado o no se puede abrir."""


class ResponseTimeout(DebugLinkError):
    """La FPGA no contestó dentro del tiempo esperado."""


class DebugLink:
    """
    Conexión con el debug_unit de la FPGA.

    Uso:

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
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def open(self) -> None:
        """
        Abre el puerto. Lanza PortUnavailable si no se puede.

        Se pide acceso exclusivo (solo POSIX): si otro proceso ya tiene el
        puerto abierto, falla acá con un error claro en vez de compartir el
        stream y robarse bytes mutuamente, que desincroniza el protocolo de
        forma irrecuperable (la FPGA no tiene reencuadre de tramas).
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
                # Windows: pyserial no soporta exclusive
                self._serial = await asyncio.to_thread(serial.Serial, **options)
        except (serial.SerialException, ValueError, OSError) as exc:
            raise PortUnavailable(
                f"No se pudo abrir {self.port} a {self.baudrate} baudios: {exc}"
            ) from exc

        # Descarta bytes viejos de una sesión anterior.
        await asyncio.to_thread(self._serial.reset_input_buffer)
        await asyncio.to_thread(self._serial.reset_output_buffer)

    async def close(self) -> None:
        """Cierra el puerto si está abierto (idempotente)."""
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
    # Primitivas de transporte
    # ------------------------------------------------------------------
    def _require_port(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise PortUnavailable("El puerto no está abierto")
        return self._serial

    async def _write_frame(self, command: int, payload: int) -> None:
        port = self._require_port()
        try:
            await asyncio.to_thread(port.write, encode(command, payload))
            await asyncio.to_thread(port.flush)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Fallo al escribir en {self.port}: {exc}") from exc

    async def _read_frame(self, timeout: float | None = None) -> Frame:
        port = self._require_port()
        if timeout is not None:
            port.timeout = timeout
        try:
            raw = await asyncio.to_thread(port.read, FRAME_SIZE)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Fallo al leer de {self.port}: {exc}") from exc
        finally:
            port.timeout = self.timeout

        if len(raw) < FRAME_SIZE:
            raise ResponseTimeout(
                f"Respuesta incompleta: {len(raw)}/{FRAME_SIZE} bytes"
            )
        return decode(raw)

    async def resync(self) -> None:
        """
        Descarta lo que haya en el buffer de entrada.

        Sirve para recuperarse de un timeout: si una respuesta llegó tarde,
        quedaría desalineada con el próximo pedido.

        OJO: esto solo limpia el lado de la PC. Si la que quedó desalineada es
        la FPGA, hace falta realign().
        """
        if self._serial is not None and self._serial.is_open:
            await asyncio.to_thread(self._serial.reset_input_buffer)

    async def realign(self) -> int | None:
        """
        Intenta reencuadrar a la FPGA mandando bytes de relleno.

        uart_interface.v agrupa los bytes recibidos de a 5 sin ninguna
        detección de silencio entre tramas, así que si el stream pierde la
        alineación la FPGA malinterpreta todo para siempre. Como el desfasaje
        es módulo 5, mandar (5-k) bytes extra completa la trama fantasma y
        vuelve a alinear; probamos 1 a 4 hasta que conteste. Se manda UN byte
        por vuelta para que el acumulado recorra 1,2,3,4 y cubra los cuatro
        desfasajes (mandar `padding` bytes por vuelta daría 1,3,6,10, que mod 5
        deja sin probar +2 y +4).

        Devuelve cuántos bytes de relleno hicieron falta, o None si no se
        recuperó (en ese caso la FSM de la FPGA está colgada y hay que
        reprogramar o resetear por hardware).
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
        """Escribe bytes crudos (para el reencuadre)."""
        port = self._require_port()
        try:
            await asyncio.to_thread(port.write, data)
            await asyncio.to_thread(port.flush)
        except serial.SerialException as exc:
            raise DebugLinkError(f"Fallo al escribir en {self.port}: {exc}") from exc

    # ------------------------------------------------------------------
    # Comandos de acción (sin respuesta)
    # ------------------------------------------------------------------
    async def _send_action(self, command: Command, payload: int = 0) -> None:
        assert command in ACTION_COMMANDS
        async with self._lock:
            await self._write_frame(command, payload)

    async def step(self) -> None:
        """Avanza el procesador un ciclo de reloj."""
        await self._send_action(Command.STEP)

    async def run(self) -> None:
        """
        Arranca la ejecución libre.

        Ojo: mientras está en RUNNING el debug_unit ignora la UART, así que no
        contesta ningún pedido hasta que cpu_halted lo devuelve a IDLE.
        Ver wait_until_halted().
        """
        await self._send_action(Command.RUN)

    async def reset(self) -> None:
        """Reinicia la CPU y el puntero de carga de instrucciones."""
        await self._send_action(Command.RESET)

    async def load_instruction(self, word: int) -> None:
        """Escribe una instrucción en memoria (autoincrementa la dirección)."""
        await self._send_action(Command.LOAD_INSTR, word)

    async def load_program(self, words: list[int], progress=None,
                           settle: float = 0.01) -> None:
        """
        Carga un programa completo en la memoria de instrucciones.

        Secuencia: RESET (que además pone en cero el puntero de escritura de
        imem) -> una trama LOAD_INSTR por instrucción -> RESET final para dejar
        el PC en 0 y el pipeline limpio.

        Ojo: el firmware NO recibe la dirección; `debug_unit` autoincrementa
        `imem_addr_reg` en cada LOAD_INSTR. Por eso el RESET inicial no es
        opcional: es lo único que reposiciona el puntero.

        `progress` es un callable opcional que recibe (enviadas, total).
        `settle` es la pausa entre tramas: LOAD_INSTR no responde nada, así que
        sin pausa se le puede ir encima al debug_unit mientras procesa.
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
    # Comandos de lectura (con respuesta)
    # ------------------------------------------------------------------
    async def _request(
        self,
        command: Command,
        payload: int,
        expected_code: int,
        timeout: float | None = None,
    ) -> int:
        """Manda un pedido y valida que el código de respuesta sea el correcto."""
        async with self._lock:
            await self._write_frame(command, payload)
            frame = await self._read_frame(timeout)

        if frame.code != expected_code:
            await self.resync()
            raise ProtocolError(
                f"Respuesta inesperada a {command.name}: se esperaba código "
                f"0x{expected_code:02X} y llegó 0x{frame.code:02X}"
            )
        return frame.payload

    async def read_register(self, number: int) -> int:
        """
        Lee un registro del banco.

        El debug_unit responde usando el propio número de registro como código,
        así que sirve de acuse: si pedimos x5 y contesta x6, algo se desincronizó.
        """
        if not 0 <= number < REGISTER_COUNT:
            raise ValueError(f"Registro fuera de rango: {number}")
        return await self._request(Command.REQ_REG, number, expected_code=number)

    async def read_pc(self, timeout: float | None = None) -> int:
        """Lee el Program Counter actual."""
        return await self._request(
            Command.REQ_PC, 0, expected_code=ResponseKind.PC, timeout=timeout
        )

    async def read_memory(self, address: int) -> int:
        """Lee una palabra de la memoria de datos (puerto B, no molesta a la CPU)."""
        return await self._request(
            Command.REQ_MEM, address, expected_code=ResponseKind.MEM
        )

    async def read_latch(self, latch_id: int) -> int:
        """Lee un latch del pipeline (ver el case de debug_latch_id en top.v)."""
        return await self._request(
            Command.REQ_LATCH, latch_id, expected_code=ResponseKind.LATCH
        )

    async def read_all_registers(self) -> AsyncIterator[tuple[int, int]]:
        """
        Lee los 32 registros. Devuelve un generador de (número, valor).

        A 9600 baudios cada registro son 10 bytes (5 de ida + 5 de vuelta),
        ~8.3 ms; los 32 tardan aproximadamente 270 ms.
        """
        for number in range(REGISTER_COUNT):
            yield number, await self.read_register(number)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    async def wait_until_halted(
        self,
        poll_timeout: float = 0.4,
        overall_timeout: float = 30.0,
    ) -> bool:
        """
        Espera a que la CPU termine la ejecución libre.

        Truco: durante RUNNING el debug_unit no atiende la UART, así que un
        REQ_PC sin respuesta significa "todavía corriendo" y una respuesta
        significa "ya volvió a IDLE", o sea que se activó cpu_halted.

        Devuelve True si frenó, False si se agotó overall_timeout.
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
    """Lista los puertos serie detectados, para sugerirlos si falla la conexión."""
    return [p.device for p in list_ports.comports()]
