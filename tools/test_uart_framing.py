"""
UART framing regression test.
uart_interface, replicating the RTL line by line.

Useful to check the two fixes (synchronizer and resync) without Vivado.
"""

CLOCK_TICK = 651        # FREQ 100e6 / (9600*16), same as the RTL
BIT_CLOCKS = 16 * CLOCK_TICK   # nominal duration of one bit on the line


class BaudGen:
    """baud_rate_gen.v exactly as it is (blocking assignments)."""
    def __init__(self):
        self.count = 0
        self.tick = 0

    def edge(self):
        if self.count == CLOCK_TICK - 1:
            self.count = 0
            self.tick = 1
        else:
            self.tick = 0
        self.count += 1
        return self.tick


class UartRx:
    """uart_rx.v WITH the 2-flop synchronizer (fix A)."""
    IDLE, START, DATA, STOP = 0, 1, 2, 3

    def __init__(self, synchronizer=True):
        self.synchronizer = synchronizer
        self.state = self.IDLE
        self.s = 0
        self.n = 0
        self.b = 0
        self.rx_meta = 1
        self.rx_sync = 1
        self.done = 0

    def edge(self, rx, s_tick):
        # --- synchronizer (separate sequential block) ---
        sampled = self.rx_sync if self.synchronizer else rx
        new_meta, new_sync = rx, self.rx_meta

        # --- combinational next state logic ---
        state_next, s_next, n_next, b_next = self.state, self.s, self.n, self.b
        self.done = 0

        if self.state == self.IDLE:
            if not sampled:
                state_next, s_next = self.START, 0
        elif self.state == self.START:
            if s_tick:
                if self.s == 7:
                    state_next, s_next, n_next = self.DATA, 0, 0
                else:
                    s_next = self.s + 1
        elif self.state == self.DATA:
            if s_tick:
                if self.s == 15:
                    s_next = 0
                    b_next = (self.b >> 1) | (sampled << 7)
                    if self.n == 7:
                        state_next = self.STOP
                    else:
                        n_next = self.n + 1
                else:
                    s_next = self.s + 1
        elif self.state == self.STOP:
            if s_tick:
                if self.s == 15:
                    state_next = self.IDLE
                    self.done = 1
                else:
                    s_next = self.s + 1

        # --- register update ---
        self.state, self.s, self.n, self.b = state_next, s_next, n_next, b_next
        if self.synchronizer:
            self.rx_meta, self.rx_sync = new_meta, new_sync
        return self.done, self.b


class UartInterfaceRx:
    """RX logic of uart_interface.v WITH idle frame resync (fix B)."""
    IDLE_TICKS = 16 * 10 * 4

    def __init__(self, resync=True):
        self.resync = resync
        self.rx_count = 0
        self.rx_buffer = 0
        self.frames = []
        self.idle_count = 0
        self.timeouts = 0

    def edge(self, rx_done_tick, rx_byte, s_tick):
        frame_timeout = (self.idle_count == self.IDLE_TICKS)

        # idle counter block
        if rx_done_tick:
            next_idle = 0
        elif s_tick and self.idle_count != self.IDLE_TICKS:
            next_idle = self.idle_count + 1
        else:
            next_idle = self.idle_count

        # frame assembly block
        if self.resync and frame_timeout and self.rx_count != 0:
            self.rx_count = 0
            self.timeouts += 1
        elif rx_done_tick:
            new_buf = ((self.rx_buffer << 8) | rx_byte) & 0xFFFFFFFFFF
            if self.rx_count == 4:
                self.frames.append(new_buf)
                self.rx_count = 0
            else:
                self.rx_count += 1
            self.rx_buffer = new_buf

        self.idle_count = next_idle


class Sim:
    def __init__(self, synchronizer=True, resync=True):
        self.baud = BaudGen()
        self.rx = UartRx(synchronizer)
        self.iface = UartInterfaceRx(resync)
        self.line = 1

    def run_clocks(self, n):
        for _ in range(n):
            tick = self.baud.edge()
            done, byte = self.rx.edge(self.line, tick)
            self.iface.edge(done, byte, tick)

    def send_byte(self, value):
        """Sends a byte at nominal baud: start, 8 bits LSB first, stop."""
        bits = [0] + [(value >> i) & 1 for i in range(8)] + [1]
        for bit in bits:
            self.line = bit
            self.run_clocks(BIT_CLOCKS)
        self.line = 1

    def idle(self, bit_times):
        self.line = 1
        self.run_clocks(BIT_CLOCKS * bit_times)

    def send_frame(self, cmd, payload):
        for b in [cmd] + list(payload.to_bytes(4, "big")):
            self.send_byte(b)


def frame_bytes(value):
    return tuple((value >> (8 * i)) & 0xFF for i in range(4, -1, -1))


fails=[]
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ")+name+("" if cond else f"  {detail}"))
    if not cond: fails.append(name)

# Threshold = 640 ticks = 40 bit times = 4 bytes.
# The real gaps between frames are >=10ms = ~96 bit times.
GAP_REAL = 96

print("=== 1. Normal reception with real gaps (10ms) ===")
s = Sim()
env=[(0x40,0),(0x20,1),(0x20,0x10),(0x10,0x02A00093)]
for c,p in env: s.send_frame(c,p); s.idle(GAP_REAL)
check("4 exact frames", s.iface.frames==[(c<<32)|p for c,p in env],
      f"-> {[hex(f) for f in s.iface.frames]}")
check("resync does not break anything (rx_count stays at 0)", s.iface.rx_count==0)

print("\n=== 2. Threshold: 30 bit times does NOT resync, 50 DOES ===")
s = Sim()
for b in [0x20,0x00]: s.send_byte(b)     # half built frame
s.idle(30)
check("30-bit gap: does not resync", s.iface.timeouts==0, f"-> {s.iface.timeouts}")
s.idle(30)                                # accumulated 60 > 40
check("60-bit gap: DOES resync", s.iface.timeouts==1, f"-> {s.iface.timeouts}")

print("\n=== 3. Lost byte -> patch fixes it ===")
s = Sim()
for b in [0x20,0x00,0x00,0x00]: s.send_byte(b)   # 4 of 5 bytes
s.idle(GAP_REAL)
s.send_frame(0x40,0); s.idle(GAP_REAL)
s.send_frame(0x20,0x02); s.idle(GAP_REAL)
check("partial frame discarded", s.iface.timeouts>=1, f"-> {s.iface.timeouts}")
check("subsequent frames arrive correctly",
      s.iface.frames==[(0x40<<32)|0, (0x20<<32)|0x02],
      f"-> {[hex(f) for f in s.iface.frames]}")

print("\n=== 4. WITHOUT patch: extra byte triggers phantom RUN ===")
s = Sim(resync=False)
s.send_byte(0xFF)                      # 1 spurious byte -> rx_count=1
s.idle(GAP_REAL)
for n in (1,2,3):                      # REQ_REG x1, x2, x3
    s.send_frame(0x20,n); s.idle(GAP_REAL)
got=[frame_bytes(f) for f in s.iface.frames]
cmds=[f[0] for f in got]
check("WITHOUT patch: frames are shifted", any(c not in (0x20,0x40,0x10,0x50) for c in cmds),
      f"-> cmds={[hex(c) for c in cmds]}")
check("WITHOUT patch: phantom STEP/RUN/RESET appears",
      any(c in (0x01,0x02,0x03) for c in cmds), f"-> cmds={[hex(c) for c in cmds]}")

print("\n=== 5. WITH patch: same spurious byte is harmless ===")
s = Sim(resync=True)
s.send_byte(0xFF); s.idle(GAP_REAL)
for n in (1,2,3):
    s.send_frame(0x20,n); s.idle(GAP_REAL)
got=[frame_bytes(f) for f in s.iface.frames]
cmds=[f[0] for f in got]
check("WITH patch: all frames are REQ_REG", cmds==[0x20,0x20,0x20],
      f"-> {[hex(c) for c in cmds]}")
check("WITH patch: requested registers are correct",
      [f[4] for f in got]==[1,2,3], f"-> {got}")
check("WITH patch: no phantom commands",
      not any(c in (0x01,0x02,0x03) for c in cmds))

print("\n"+"="*52)
print("FAILED: "+str(fails) if fails else "ALL OK")
