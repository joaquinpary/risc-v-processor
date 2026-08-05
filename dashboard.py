import serial
import time

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
                0x02A00093, # addi x1, x0, 42
                0x06400113, # addi x2, x0, 100
                0x00802183, # lw   x3, 8(x0)
                0x00002023, # sw   x0, 0(x0)
                0x00208233, # add  x4, x1, x2
                0x00000463, # beq  x0, x0, +8
                0x00000000, # NOP (Trigger HALT)
                0x00000000,
                0x00000000,
                0x00000000,
                0x00000000
            ]
            for inst in instructions:
                board.load_instruction(inst)
            
            # 3. Execute
            board.run_processor()
            
            # 4. Query state
            print("\n--- Querying State ---")
            board.query_register(1)
            board.query_register(2)
            board.query_register(4)
            board.query_pc()
            
            # Latch IDs: 1 (IF/ID PC), 4 (ID/EX PC)
            board.query_latch(1, "IF/ID PC")
            board.query_latch(4, "ID/EX PC")
            
        finally:
            board.close()
