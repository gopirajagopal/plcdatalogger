"""
SETEX 797TCE — Read all registers (including zeros) to verify communication.
Usage:
    python test_read_all.py
"""
import logging
logging.disable(logging.CRITICAL)

from pymodbus.client import ModbusTcpClient

IP    = '192.168.1.212'
PORT  = 50002
SLAVE = 0

def try_read(c, fn, addr, count, label):
    for kw in [{'dev_id': SLAVE}, {'slave': SLAVE}, {'unit': SLAVE}, {}]:
        try:
            r = fn(addr, count=count, **kw)
            if not r.isError():
                return r.registers if hasattr(r, 'registers') else list(r.bits[:count])
            print(f"  [{label}] Modbus error response: {r}")
            return None
        except TypeError:
            continue
        except Exception as e:
            print(f"  [{label}] Exception: {e}")
            return None
    return None

c = ModbusTcpClient(IP, port=PORT, timeout=3)
if not c.connect():
    print(f"Cannot connect to {IP}:{PORT}")
    exit()

print(f"Connected to {IP}:{PORT}  slave={SLAVE}\n")

# FC3 holding registers 0-124
print("=== FC3 Holding Registers 0-124 ===")
regs = try_read(c, c.read_holding_registers, 0, 125, 'FC3')
if regs is None:
    print("  ERROR / no response")
else:
    print(f"  Got {len(regs)} registers")
    for i, v in enumerate(regs):
        signed = v if v < 32768 else v - 65536
        print(f"  [{i:>3}] dec={v:>6}  hex={v:#06x}  signed={signed:>6}")

# FC4 input registers 0-49
print("\n=== FC4 Input Registers 0-49 ===")
regs4 = try_read(c, c.read_input_registers, 0, 50, 'FC4')
if regs4 is None:
    print("  ERROR / no response")
else:
    print(f"  Got {len(regs4)} registers")
    for i, v in enumerate(regs4):
        if v != 0:
            print(f"  [{i:>3}] dec={v:>6}  hex={v:#06x}")
    if all(v == 0 for v in regs4):
        print("  All zeros")

# FC1 coils 0-31
print("\n=== FC1 Coils 0-31 ===")
coils = try_read(c, c.read_coils, 0, 32, 'FC1')
if coils is None:
    print("  ERROR / no response")
else:
    ones = [i for i, b in enumerate(coils) if b]
    print(f"  Coils ON: {ones if ones else 'none'}")

c.close()
print("\nDone.")
