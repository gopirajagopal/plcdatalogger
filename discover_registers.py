"""
SETEX 797TCE — Register discovery script
Auto-probes slave IDs and scans all registers.

Usage:
    python discover_registers.py
    python discover_registers.py --ip 192.168.1.212 --port 50000
    python discover_registers.py --slave 255 --end 1000
"""

import argparse
import struct
import logging
logging.disable(logging.CRITICAL)   # suppress pymodbus retry noise

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient

try:
    from pymodbus.exceptions import ModbusIOException
except ImportError:
    ModbusIOException = Exception

import pymodbus as _pm
print(f"pymodbus version: {_pm.__version__}")


def _call(fn, addr, count, slave):
    for kw in [{'dev_id': slave}, {'slave': slave}, {'unit': slave}, {}]:
        try:
            return fn(addr, count=count, **kw)
        except TypeError:
            continue
    return fn(addr, count)


def _read(client, addr, count, slave):
    try:
        r = _call(client.read_holding_registers, addr, count, slave)
        if r is not None and not r.isError():
            return r
    except (ModbusIOException, Exception):
        pass
    try:
        r = _call(client.read_input_registers, addr, count, slave)
        if r is not None and not r.isError():
            return r
    except (ModbusIOException, Exception):
        pass
    return None


def probe_slave(client, candidates=(1, 0, 2, 255)):
    """Return first slave ID that responds, or None."""
    print("Probing slave IDs: ", end='', flush=True)
    for sid in candidates:
        print(f"{sid}...", end='', flush=True)
        r = _read(client, 0, 1, sid)
        if r is not None:
            print(f" → slave {sid} responds!")
            return sid
    print(" none responded.")
    return None


def scan(ip, port, slave, start, end):
    c = ModbusTcpClient(ip, port=port, timeout=2)
    if not c.connect():
        print(f"[FAIL] Cannot connect to {ip}:{port}")
        return

    print(f"Connected to {ip}:{port}")

    if slave is None:
        slave = probe_slave(c)
        if slave is None:
            print("\n[FAIL] No slave responded. Check IP, port, and Modbus config on the PLC.")
            c.close()
            return
    else:
        print(f"Using slave ID: {slave}")

    print(f"\nScanning registers {start}–{end} ...\n")
    print(f"{'Addr':>5}  {'Dec':>7}  {'Hex':>6}  {'Signed':>8}  {'Float32':>12}")
    print("-" * 50)

    found = 0
    for batch_start in range(start, end + 1, 20):
        count = min(20, end - batch_start + 1)
        r = _read(c, batch_start, count, slave)
        if r is None:
            continue
        regs = r.registers
        for i, v in enumerate(regs):
            if v != 0:
                addr = batch_start + i
                signed = v if v < 32768 else v - 65536
                f32 = ""
                if i + 1 < len(regs):
                    try:
                        fv = struct.unpack('>f', struct.pack('>HH', v, regs[i+1]))[0]
                        if -1e6 < fv < 1e6 and fv == fv:
                            f32 = f"{fv:.3f}"
                    except Exception:
                        pass
                print(f"  {addr:>4}  {v:>8}  {v:#06x}  {signed:>8}  {f32:>12}")
                found += 1

    print(f"\n{found} non-zero registers found.")
    c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Discover PLC registers')
    parser.add_argument('--ip',    default='192.168.1.212')
    parser.add_argument('--port',  type=int, default=50000)
    parser.add_argument('--slave', type=int, default=None,
                        help='Slave ID (default: auto-probe 1,0,2,255)')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end',   type=int, default=300)
    args = parser.parse_args()

    scan(args.ip, args.port, args.slave, args.start, args.end)
