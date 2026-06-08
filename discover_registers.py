"""
SETEX 797TCE — Register discovery script
Scans holding registers 0-500 and prints all non-zero values.

Usage:
    python discover_registers.py
    python discover_registers.py --ip 192.168.1.212 --port 50000 --slave 1
    python discover_registers.py --end 1000
"""

import argparse
try:
    from pymodbus.client import ModbusTcpClient        # pymodbus 3.x
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient  # pymodbus 2.x

import pymodbus
_PM3 = int(pymodbus.__version__.split('.')[0]) >= 3

def _read(client, addr, count, slave):
    kwargs = {'slave': slave} if _PM3 else {'unit': slave}
    return client.read_holding_registers(addr, count=count, **kwargs)

def scan(ip, port, slave, start, end):
    c = ModbusTcpClient(ip, port=port, timeout=3)
    if not c.connect():
        print(f"[FAIL] Cannot connect to {ip}:{port}")
        return

    print(f"\nConnected to {ip}:{port}  slave={slave}")
    print(f"Scanning registers {start} – {end} ...\n")
    print(f"{'Addr':>5}  {'Dec':>7}  {'Hex':>6}  {'Signed':>8}  {'Float32 (with next reg)':>24}")
    print("-" * 65)

    import struct
    found = 0
    for batch_start in range(start, end + 1, 50):
        count = min(50, end - batch_start + 1)
        r = _read(c, batch_start, count, slave)
        if r.isError():
            continue
        regs = r.registers
        for i, v in enumerate(regs):
            if v != 0:
                addr = batch_start + i
                signed = v if v < 32768 else v - 65536
                # try float32 with next register
                f32 = ""
                if i + 1 < len(regs):
                    try:
                        fv = struct.unpack('>f', struct.pack('>HH', v, regs[i+1]))[0]
                        if -1e6 < fv < 1e6 and fv == fv:  # finite
                            f32 = f"{fv:.4f}"
                    except Exception:
                        pass
                print(f"  {addr:>4}  {v:>8}  {v:#06x}  {signed:>8}  {f32:>24}")
                found += 1

    print(f"\n{found} non-zero registers found out of {end - start + 1} scanned.")
    c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Discover PLC registers')
    parser.add_argument('--ip',    default='192.168.1.212')
    parser.add_argument('--port',  type=int, default=50000)
    parser.add_argument('--slave', type=int, default=1)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end',   type=int, default=500)
    args = parser.parse_args()

    scan(args.ip, args.port, args.slave, args.start, args.end)
