import serial
import time


def _sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return value - (1 << bits) if value & sign_bit else value


def decode_instruction(instruction):
    """Decodes the RV32I instructions used by the dashboard test."""
    opcode = instruction & 0x7F
    rd = (instruction >> 7) & 0x1F
    funct3 = (instruction >> 12) & 0x07
    rs1 = (instruction >> 15) & 0x1F
    rs2 = (instruction >> 20) & 0x1F
    funct7 = (instruction >> 25) & 0x7F

    if instruction == 0:
        return "nop"

    if opcode == 0x13 and funct3 == 0x0:  # ADDI
        immediate = _sign_extend((instruction >> 20) & 0xFFF, 12)
        return f"addi x{rd}, x{rs1}, {immediate}"

    if opcode == 0x33 and funct3 == 0x0:  # ADD/SUB
        if funct7 == 0x00:
            return f"add x{rd}, x{rs1}, x{rs2}"
        if funct7 == 0x20:
            return f"sub x{rd}, x{rs1}, x{rs2}"

    if opcode == 0x03 and funct3 == 0x2:  # LW
        immediate = _sign_extend((instruction >> 20) & 0xFFF, 12)
        return f"lw x{rd}, {immediate}(x{rs1})"

    if opcode == 0x23 and funct3 == 0x2:  # SW
        immediate = ((instruction >> 25) << 5) | ((instruction >> 7) & 0x1F)
        immediate = _sign_extend(immediate, 12)
        return f"sw x{rs2}, {immediate}(x{rs1})"

    if opcode == 0x63 and funct3 == 0x0:  # BEQ
        immediate = (
            (((instruction >> 31) & 0x1) << 12)
            | (((instruction >> 7) & 0x1) << 11)
            | (((instruction >> 25) & 0x3F) << 5)
            | (((instruction >> 8) & 0xF) << 1)
        )
        immediate = _sign_extend(immediate, 13)
        return f"beq x{rs1}, x{rs2}, {immediate:+d}"

    return f".word 0x{instruction:08X}"


class RiscVDashboard:
    def __init__(self, port='/dev/ttyUSB1', baudrate=9600):
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"Connected to {port} at {baudrate} baud.")
            time.sleep(2) # Give the connection some time to settle
        except serial.SerialException as e:
            print(f"Failed to connect: {e}")
            self.ser = None

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial port closed.")

    def send_packet(self, cmd, data_int):
        """Sends a 5-byte packet (40 bits): 1 byte CMD, 4 bytes DATA."""
        if not self.ser or not self.ser.is_open:
            print("Serial port not open.")
            return

        # Pack the integer into 4 bytes (big endian)
        data_bytes = data_int.to_bytes(4, byteorder='big', signed=False)
        cmd_byte = cmd.to_bytes(1, byteorder='big')
        packet = cmd_byte + data_bytes
        
        self.ser.write(packet)
        # print(f"[TX] CMD=0x{cmd:02X} | DATA=0x{data_int:08X}")

    def receive_packet(self):
        """Waits and receives a 5-byte packet from the FPGA."""
        if not self.ser or not self.ser.is_open:
            return None, None

        packet = self.ser.read(5)
        if len(packet) == 5:
            cmd = packet[0]
            data_int = int.from_bytes(packet[1:5], byteorder='big', signed=False)
            # print(f"[RX] CMD=0x{cmd:02X} | DATA=0x{data_int:08X} ({data_int})")
            return cmd, data_int
        else:
            print("[RX] Timeout: Incomplete or no packet received.")
            return None, None

    # --- High-level operations ---
    
    def reset_processor(self):
        print("\n--- Resetting Processor ---")
        self.send_packet(0x03, 0x00000000)
        time.sleep(0.1)

    def load_instruction(self, inst_hex):
        """Loads a 32-bit instruction into memory."""
        self.send_packet(0x10, inst_hex)
        time.sleep(0.01) # Small delay to not overwhelm the RX buffer

    def run_processor(self):
        print("\n--- Running Processor ---")
        self.send_packet(0x02, 0x00000000)
        time.sleep(0.1) # Wait for execution to finish and halt

    def query_register(self, reg_id):
        self.send_packet(0x20, reg_id)
        cmd, data = self.receive_packet()
        if cmd is not None:
            print(f"Register x{reg_id:02d} = {data:10d} (0x{data:08X})")
        return data

    def query_pc(self):
        self.send_packet(0x40, 0x00000000)
        cmd, data = self.receive_packet()
        if cmd is not None:
            print(f"PC          = {data:10d} (0x{data:08X})")
        return data

    def query_latch(self, latch_id, name="Latch"):
        self.send_packet(0x50, latch_id)
        cmd, data = self.receive_packet()
        if cmd is not None:
            print(f"{name:<11} = {data:10d} (0x{data:08X})")
        return data

# =========================================================
# Main Execution Flow
# =========================================================
if __name__ == '__main__':
    # Adjust port based on your system (e.g., COM3 on Windows, /dev/ttyUSB1 on Linux)
    board = RiscVDashboard(port='/dev/ttyUSB1', baudrate=9600)
    
    if board.ser:
        try:
            # 1. Reset
            board.reset_processor()
            
            # 2. Load instructions (same test program)
            print("--- Loading Instructions ---")
            instructions = [
                0x02A00093, # addi x1,  x0, 42
                0x06400113, # addi x2,  x0, 100
                0x00208233, # add  x4,  x1, x2       (RAW: x1, x2)
                0x401202B3, # sub  x5,  x4, x1       (RAW: x4)
                0x00428333, # add  x6,  x5, x4       (RAW: x5, x4)
                0x00130393, # addi x7,  x6, 1        (RAW: x6)
                0x00800413, # addi x8,  x0, 8
                0x00802423, # sw   x8,  8(x0)       (RAW: x8)
                0x00802483, # lw   x9,  8(x0)
                0x00148533, # add  x10, x9, x1       (load-use: x9)
                0x009505B3, # add  x11, x10, x9      (RAW: x10, x9)
                0x00000463, # beq  x0,  x0, +8
                0x00000000, # NOP (Trigger HALT)
                0x00000000,
                0x00000000,
                0x00000000,
                0x00000000
            ]
            for index, inst in enumerate(instructions):
                asm = decode_instruction(inst)
                print(f"[LOAD] IMEM[{index * 4:02d}] <- 0x{inst:08X}    {asm}")
                board.load_instruction(inst)
            
            # 3. Execute
            board.run_processor()
            
            # 4. Query state
            print("\n--- Querying State ---")
            board.query_register(1)
            board.query_register(2)
            board.query_register(4)
            board.query_register(5)
            board.query_register(6)
            board.query_register(7)
            board.query_register(8)
            board.query_register(9)
            board.query_register(10)
            board.query_register(11)
            board.query_pc()
            
            # Latch IDs: 1 (IF/ID PC), 4 (ID/EX PC)
            board.query_latch(1, "IF/ID PC")
            board.query_latch(4, "ID/EX PC")
            
        finally:
            board.close()
