"""
SETEX 797TCE — Connection diagnostic script
Tests raw TCP, standard Modbus TCP, and Modbus RTU-over-TCP.

Usage:
    python test_connection.py
    python test_connection.py --ip 192.168.1.212 --port 50000
"""

import argparse
import socket
import struct

IP   = '192.168.1.212'
PORT = 50000

# ── CRC for Modbus RTU ────────────────────────────────────────────────────────
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else crc >> 1
    return crc

# ── Helpers ───────────────────────────────────────────────────────────────────
def raw_send(ip, port, data: bytes, label: str):
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect((ip, port))
        s.send(data)
        try:
            r = s.recv(256)
            print(f"  [{label}] Response ({len(r)} bytes): {r.hex()}")
            return r
        except socket.timeout:
            print(f"  [{label}] No response (timeout)")
        finally:
            s.close()
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
    return None

# ── Tests ─────────────────────────────────────────────────────────────────────
def test_ports(ip):
    print(f"\n=== Port scan on {ip} ===")
    open_ports = []
    for port in [502, 503, 1502, 2000, 5000, 5001, 8080, 8502,
                 50000, 50001, 50002, 50003, 50004, 50005,
                 20000, 44818, 1200, 1201, 4840]:
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect((ip, port))
            print(f"  Port {port:>6}: OPEN")
            open_ports.append(port)
            s.close()
        except:
            pass
    if not open_ports:
        print("  No ports responded.")
    return open_ports


def test_modbus_tcp(ip, port):
    print(f"\n=== Modbus TCP (standard) on {ip}:{port} ===")
    for slave in [1, 0, 2, 255]:
        # MBAP header + FC3 read 1 register from address 0
        pkt = struct.pack('>HHHBB HH', 1, 0, 6, slave, 3, 0, 1)
        raw_send(ip, port, pkt, f"FC3 slave={slave}")


def test_modbus_rtu_over_tcp(ip, port):
    print(f"\n=== Modbus RTU-over-TCP on {ip}:{port} ===")
    for slave in [1, 0, 2, 255]:
        pdu = bytes([slave, 3, 0, 0, 0, 1])   # FC3 read reg 0, count 1
        crc = crc16(pdu)
        frame = pdu + struct.pack('<H', crc)
        raw_send(ip, port, frame, f"RTU FC3 slave={slave}")


def test_read_coils(ip, port):
    print(f"\n=== Modbus TCP FC1 (read coils) on {ip}:{port} ===")
    for slave in [1, 255]:
        pkt = struct.pack('>HHHBB HH', 1, 0, 6, slave, 1, 0, 8)
        raw_send(ip, port, pkt, f"FC1 coils slave={slave}")


def test_raw_hello(ip, port):
    print(f"\n=== Raw hello on {ip}:{port} ===")
    for probe in [b'\x00' * 8, b'\xff' * 4, b'SETEX\r\n', b'\x01\x03\x00\x00\x00\x01']:
        raw_send(ip, port, probe, probe.hex()[:16])


def test_listen(ip, port, seconds=5):
    """Just connect and listen — PLC may push data without needing a request."""
    print(f"\n=== Listen-only on {ip}:{port} (waiting {seconds}s) ===")
    try:
        s = socket.socket()
        s.settimeout(seconds)
        s.connect((ip, port))
        print(f"  Connected. Waiting for PLC to push data...")
        try:
            data = s.recv(512)
            print(f"  PLC pushed {len(data)} bytes: {data.hex()}")
            print(f"  ASCII: {data[:80]}")
        except socket.timeout:
            print(f"  Nothing received in {seconds}s — not a push port")
        s.close()
    except Exception as e:
        print(f"  ERROR: {e}")


def test_modbus_tcp_port(ip, port):
    print(f"\n=== Modbus TCP on {ip}:{port} ===")
    for slave in [1, 0, 255]:
        pkt = struct.pack('>HHHBB HH', 1, 0, 6, slave, 3, 0, 1)
        raw_send(ip, port, pkt, f"FC3 slave={slave}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip',   default=IP)
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()

    print(f"Target: {args.ip}:{args.port}")

    open_ports = test_ports(args.ip)
    test_modbus_tcp(args.ip, args.port)
    test_modbus_rtu_over_tcp(args.ip, args.port)
    test_read_coils(args.ip, args.port)

    # Test: PLC might push data without needing a request
    test_listen(args.ip, 50000, seconds=5)
    test_listen(args.ip, 50002, seconds=5)

    # Test Modbus on port 50002
    test_modbus_tcp_port(args.ip, 50002)

    print("\n=== Done. Share the output above. ===")
