#!/usr/bin/env python3
"""
uart_doctor — traza y diagnostica el enlace UART con la FPGA.

Tres modos:

    # 1. Diagnostico controlado: aisla QUE comando rompe el enlace
    python uart_doctor.py diagnose --port /dev/ttyUSB1

    # 2. Corre dashboard.py con todos los bytes trazados
    python uart_doctor.py trace-dashboard --port /dev/ttyUSB1

    # 3. Corre el dashboard TUI (riscv_debug) con todos los bytes trazados
    python uart_doctor.py trace-tui --port /dev/ttyUSB1

Todo queda en un archivo de log con marcas de tiempo (--log, por defecto
uart_doctor.log) además de salir por consola.

La traza funciona parcheando serial.Serial, así que registra CUALQUIER script
que use pyserial sin tener que modificarlo.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path

# Permite importar riscv_debug estando parado en cualquier lado.
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
    """Escribe a consola y a archivo con marca de tiempo relativa."""

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
# Decodificación legible de tramas
# =====================================================================


def describe_tx(frame: bytes) -> str:
    """Describe una trama que va de la PC a la FPGA."""
    cmd, payload = frame[0], int.from_bytes(frame[1:5], "big")
    try:
        name = Command(cmd).name
    except ValueError:
        return f"!! COMANDO DESCONOCIDO 0x{cmd:02X} payload=0x{payload:08X}"

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
    """Describe una trama que viene de la FPGA."""
    code, data = frame[0], int.from_bytes(frame[1:5], "big")
    if code <= MAX_REGISTER_CODE:
        return f"REG x{code} ({ABI_NAMES[code]}) = 0x{data:08X} ({data})"
    try:
        kind = ResponseKind(code).name
    except ValueError:
        return f"!! RESPUESTA DESCONOCIDA 0x{code:02X} data=0x{data:08X}"
    return f"{kind} = 0x{data:08X} ({data})"


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# =====================================================================
# Ensamblador de tramas: detecta desalineación
# =====================================================================


class FrameAssembler:
    """
    Reconstruye tramas de 5 bytes en un sentido y lleva la cuenta total.

    El punto clave: la FPGA agrupa los bytes recibidos de a 5 sin ningún
    reencuadre (uart_interface.v cuenta rx_count módulo 5). Si el total de
    bytes que mandamos deja de ser múltiplo de 5 en un límite de trama,
    la FPGA queda desalineada para siempre.
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
                f"| PARCIAL ({len(self.buffer)}/5 bytes en el buffer){gap}"
            )

    @property
    def aligned(self) -> bool:
        return self.total_bytes % FRAME_SIZE == 0

    def report(self) -> str:
        state = "alineado" if self.aligned else f"DESALINEADO (resto {self.total_bytes % FRAME_SIZE})"
        return f"{self.direction}: {self.total_bytes} bytes, {self.frames} tramas, {state}"


# =====================================================================
# serial.Serial instrumentado
# =====================================================================

_RealSerial = serial.Serial
_tracers: list["TracedSerial"] = []


def make_traced_serial(log: Log, force_port: str | None = None,
                       force_baud: int | None = None):
    """
    Devuelve una subclase de serial.Serial que registra todo el tráfico.

    force_port/force_baud pisan lo que pida el script trazado: dashboard.py
    tiene el puerto hardcodeado, así que sin esto --port no tendría efecto.
    """

    class TracedSerial(_RealSerial):
        def __init__(self, *args, **kwargs):
            if force_port is not None:
                if args:  # port como primer posicional
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
                self._log(f"  !! ESCRITURA PARCIAL: {written}/{len(data)} bytes")
            self.tx.feed(bytes(data))
            return written

        def read(self, size=1):
            t0 = time.monotonic()
            data = super().read(size)
            elapsed = (time.monotonic() - t0) * 1000
            if len(data) < size:
                self._log(
                    f"  !! TIMEOUT: se pidieron {size} bytes y llegaron "
                    f"{len(data)} tras {elapsed:.0f}ms"
                )
            if data:
                self.rx.feed(data)
            return data

        def reset_input_buffer(self):
            pending = self.in_waiting
            if pending:
                stale = super().read(pending)
                self._log(
                    f"  !! DESCARTADOS {len(stale)} bytes viejos del buffer: "
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
    """Parchea serial.Serial para que cualquier script quede instrumentado."""
    serial.Serial = make_traced_serial(log, port, baud)
    log(f"Tracer instalado sobre serial.Serial (forzando puerto {port})")


def summarize_tracers(log: Log) -> None:
    for tracer in _tracers:
        log(tracer.tx.report())
        log(tracer.rx.report())
        if not tracer.tx.aligned:
            log(
                "  !! El total de bytes enviados NO es multiplo de 5: la FPGA "
                "quedo desalineada y no se recupera sin reset (uart_interface.v "
                "no tiene reencuadre)."
            )


# =====================================================================
# Modo 1: diagnóstico controlado
# =====================================================================


class Probe:
    """Envía comandos crudos y mide la respuesta, sin ninguna abstracción."""

    def __init__(self, port: str, baud: int, timeout: float, log: Log):
        self.log = log
        self.timeout = timeout
        try:
            # exclusive=True hace que abrir el puerto dos veces falle en vez de
            # corromper el stream en silencio (solo POSIX).
            self.ser = _RealSerial(
                port=port, baudrate=baud, timeout=timeout, exclusive=True
            )
        except TypeError:
            self.ser = _RealSerial(port=port, baudrate=baud, timeout=timeout)
        except serial.SerialException as exc:
            raise SystemExit(
                f"No se pudo abrir {port}: {exc}\n"
                "Si dice 'device reports readiness'/'Resource busy', hay otro "
                "proceso con el puerto abierto (¿dashboard.py corriendo?)."
            )
        self.tx_total = 0

    def drain(self, label: str = "") -> bytes:
        """Vacía el buffer de entrada y reporta lo que había (bytes huérfanos)."""
        time.sleep(0.2)
        pending = self.ser.in_waiting
        if not pending:
            return b""
        stale = self.ser.read(pending)
        self.log(
            f"  !! {len(stale)} bytes huerfanos en el buffer {label}: {hexdump(stale)}"
        )
        return stale

    def send(self, cmd: int, payload: int = 0) -> None:
        frame = bytes([cmd]) + payload.to_bytes(4, "big")
        self.ser.write(frame)
        self.ser.flush()
        self.tx_total += len(frame)
        self.log(f"  TX {hexdump(frame)}  | {describe_tx(frame)}")

    def expect(self, timeout: float | None = None) -> bytes | None:
        """Lee una trama y la reporta. Devuelve None si hubo timeout."""
        self.ser.timeout = timeout or self.timeout
        t0 = time.monotonic()
        data = self.ser.read(FRAME_SIZE)
        elapsed = (time.monotonic() - t0) * 1000
        self.ser.timeout = self.timeout

        if len(data) == FRAME_SIZE:
            self.log(f"  RX {hexdump(data)}  | {describe_rx(data)}  ({elapsed:.0f}ms)")
            return data
        self.log(
            f"  RX -- SIN RESPUESTA: {len(data)}/5 bytes tras {elapsed:.0f}ms"
            + (f"  parcial={hexdump(data)}" if data else "")
        )
        return None

    def ping(self, timeout: float | None = None) -> bool:
        """REQ_PC como prueba de vida."""
        self.send(Command.REQ_PC)
        return self.expect(timeout) is not None

    def try_realign(self) -> int | None:
        """
        Intenta reencuadrar a la FPGA mandando bytes de relleno.

        Como agrupa de a 5 sin reencuadre, si quedó corrida k bytes, mandar
        (5-k) bytes extra completa la trama fantasma y vuelve a alinear.
        Devuelve cuántos bytes hicieron falta en total, o None si no se recuperó.

        Se manda UN byte por vuelta, así el relleno acumulado recorre 1,2,3,4 y
        cubre los cuatro desfasajes posibles. (Mandar `padding` bytes por vuelta
        acumularía 1,3,6,10 == 1,3,1,0 mod 5 y nunca probaría +2 ni +4.)
        """
        self.log("  Probando reencuadre con bytes de relleno...")
        for total in range(1, FRAME_SIZE):
            self.ser.write(b"\x00")
            self.ser.flush()
            self.tx_total += 1
            self.drain("(tras relleno)")
            self.log(f"    relleno acumulado de {total} byte(s) -> probando REQ_PC")
            if self.ping(timeout=1.0):
                self.log(f"  ==> RECUPERADO con {total} byte(s) de relleno")
                return total
        self.log("  ==> No se recupero con ningun relleno (probados +1,+2,+3,+4)")
        return None

    def close(self) -> None:
        self.ser.close()


def diagnose(port: str, baud: int, timeout: float, log: Log) -> int:
    """
    Secuencia controlada que aisla qué comando rompe el enlace.

    Después de cada acción hace un REQ_PC de prueba de vida; el primer fallo
    identifica al culpable, y ahí se intenta el reencuadre para distinguir
    entre "FPGA desalineada" y "FSM colgada".
    """
    probe = Probe(port, baud, timeout, log)
    verdict = 0

    try:
        log.rule("0. Estado inicial")
        stale = probe.drain("al abrir (sobras de una sesion anterior)")
        if stale:
            log(
                "  NOTA: habia bytes sin leer. Si no son multiplo de 5, la "
                "sesion anterior dejo la FPGA desalineada."
            )

        log.rule("1. Prueba de vida (10 x REQ_PC seguidos)")
        alive = 0
        for i in range(10):
            if probe.ping():
                alive += 1
            else:
                log(f"  !! murio en el intento {i + 1}")
                break
        log(f"  {alive}/10 respuestas")
        if alive == 0:
            log("  El enlace ya estaba muerto antes de mandar ningun comando.")
            if probe.try_realign() is None:
                log(
                    "  DIAGNOSTICO: la FPGA no responde ni reencuadrando. "
                    "Su FSM esta colgada (probablemente en RUNNING esperando "
                    "cpu_halted, o en SEND_RESP esperando tx_busy). "
                    "Hay que reprogramar la placa o apretar el reset fisico."
                )
                return 2
            log("  DIAGNOSTICO: estaba DESALINEADA, no colgada.")

        log.rule("2. Barrido completo de registros (33 intercambios)")
        ok = 0
        probe.send(Command.REQ_PC)
        if probe.expect():
            ok += 1
        for n in range(32):
            probe.send(Command.REQ_REG, n)
            if probe.expect():
                ok += 1
            else:
                log(f"  !! murio leyendo x{n} (intercambio {ok + 1})")
                break
        log(f"  {ok}/33 intercambios completos")
        if ok < 33:
            verdict = 1
            probe.try_realign()

        log.rule("3. Comando STEP, despues prueba de vida")
        probe.send(Command.STEP)
        time.sleep(0.2)
        probe.drain("(STEP no deberia responder nada)")
        if probe.ping():
            log("  OK: el enlace sobrevive a STEP")
        else:
            log("  !! EL ENLACE MURIO DESPUES DE STEP")
            verdict = 1
            if probe.try_realign() is None:
                log(
                    "  DIAGNOSTICO: STEP cuelga la FSM. Con cpu_enable en 1 un "
                    "ciclo el pipeline avanza; revisar si algo en el datapath "
                    "deja al debug_unit sin volver a IDLE."
                )
                return 2

        log.rule("4. Comando RESET, despues prueba de vida")
        probe.send(Command.RESET)
        time.sleep(0.2)
        probe.drain("(RESET no deberia responder nada)")
        if probe.ping():
            log("  OK: el enlace sobrevive a RESET")
        else:
            log("  !! EL ENLACE MURIO DESPUES DE RESET")
            verdict = 1
            if probe.try_realign() is None:
                return 2

        log.rule("5. Comando RUN, despues sondeo hasta que frene")
        probe.send(Command.RUN)
        log("  Sondeando REQ_PC (la FPGA ignora la UART mientras corre)...")
        deadline = time.monotonic() + 10.0
        recovered = False
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            if probe.ping(timeout=0.5):
                recovered = True
                break
        if recovered:
            log(f"  OK: freno y volvio a responder tras {attempts} sondeos")
        else:
            log("  !! NO VOLVIO NUNCA tras RUN (10 s)")
            verdict = 1
            log(
                "  DIAGNOSTICO PROBABLE: cpu_halted nunca se activa, asi que el "
                "debug_unit se queda en RUNNING para siempre ignorando la UART. "
                "cpu_halted = (instruction_id == 0 && pc_if > 0x10): si el "
                "programa no termina en instrucciones nulas, o el pipeline "
                "quedo frenado con el PC por debajo de 0x10, no se cumple nunca. "
                "Es un cuelgue del que NO se sale por UART: hay que reprogramar."
            )
            if probe.try_realign() is None:
                return 2

        log.rule("Resumen")
        log(f"  Bytes enviados en total: {probe.tx_total} "
            f"({'multiplo de 5, alineado' if probe.tx_total % 5 == 0 else 'NO multiplo de 5'})")
        if verdict == 0:
            log("  El enlace sobrevivio a toda la secuencia.")
        return verdict

    except KeyboardInterrupt:
        log("Interrumpido por el usuario")
        return 130
    finally:
        probe.close()


# =====================================================================
# Modos 2 y 3: correr otro script bajo traza
# =====================================================================


def trace_dashboard(port: str, baud: int, log: Log) -> int:
    """Corre dashboard.py (el de la raíz del repo) con la traza puesta."""
    script = Path(__file__).resolve().parent.parent / "dashboard.py"
    if not script.exists():
        log(f"No encuentro {script}")
        return 1

    install_tracer(log, port, baud)
    log.rule(f"Ejecutando {script.name}")
    sys.argv = [str(script)]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001 - queremos ver cualquier fallo
        log(f"!! El script termino con excepcion: {exc!r}")
    finally:
        log.rule("Resumen de la traza")
        summarize_tracers(log)
    return 0


def trace_tui(port: str, baud: int, log: Log) -> int:
    """Corre el dashboard TUI (riscv_debug) con la traza puesta."""
    install_tracer(log, port, baud)
    log.rule("Ejecutando riscv_debug")
    from riscv_debug.__main__ import main as tui_main

    sys.argv = ["riscv_debug", "--port", port, "--baud", str(baud)]
    try:
        tui_main()
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001
        log(f"!! El dashboard termino con excepcion: {exc!r}")
    finally:
        log.rule("Resumen de la traza")
        summarize_tracers(log)
    return 0


# =====================================================================
# CLI
# =====================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="uart_doctor",
        description="Traza y diagnostica el enlace UART con la FPGA.",
    )
    parser.add_argument(
        "mode",
        choices=["diagnose", "trace-dashboard", "trace-tui"],
        help="diagnose: secuencia controlada; trace-*: corre el script bajo traza",
    )
    parser.add_argument("--port", "-p", required=True)
    parser.add_argument("--baud", "-b", type=int, default=9600)
    parser.add_argument("--timeout", "-t", type=float, default=2.0)
    parser.add_argument("--log", "-l", default="uart_doctor.log")
    args = parser.parse_args()

    log = Log(Path(args.log) if args.log else None)
    log(f"uart_doctor — modo {args.mode} — puerto {args.port} @ {args.baud}")
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
        log(f"Log completo en: {Path(args.log).resolve()}")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
