"""
SETEX SECOM 797TCE — CoDeSys V2.3 communication test
Tests port 50002 (CoDeSys PLC-to-PLC / Network Variables)

CoDeSys V2.3 "Network Variables" protocol:
  - PLC publishes packed binary data on a configured TCP/UDP port
  - No request needed — just connect and listen (TCP) or bind (UDP)
  - Data format: 4-byte header + packed variable values

Usage:
    python test_codesys.py
    python test_codesys.py --ip 192.168.1.212
"""

import argparse
import socket
import struct
import time

IP   = '192.168.1.212'
PORT = 50002


def listen_tcp(ip, port, seconds=15):
    """Connect to TCP port and listen for any data the PLC sends."""
    print(f"\n=== TCP Listen {ip}:{port} for {seconds}s ===")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(seconds)
        s.connect((ip, port))
        print("  Connected. Waiting for PLC to send data...")
        start = time.time()
        all_data = b''
        while time.time() - start < seconds:
            try:
                chunk = s.recv(512)
                if chunk:
                    all_data += chunk
                    print(f"  Got {len(chunk)} bytes @ t={time.time()-start:.1f}s: {chunk.hex()}")
                else:
                    print("  Connection closed by PLC")
                    break
            except socket.timeout:
                break
        if not all_data:
            print("  Nothing received.")
        s.close()
        return all_data
    except Exception as e:
        print(f"  Error: {e}")
        return b''


def listen_udp(ip, port, seconds=10):
    """Listen on UDP port — CoDeSys NetVars can use UDP multicast."""
    print(f"\n=== UDP Listen port {port} for {seconds}s ===")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(seconds)
        s.bind(('', port))
        start = time.time()
        while time.time() - start < seconds:
            try:
                data, addr = s.recvfrom(1024)
                print(f"  Got {len(data)} bytes from {addr}: {data.hex()}")
            except socket.timeout:
                break
        s.close()
    except Exception as e:
        print(f"  UDP bind error: {e}")


def try_codesys_packets(ip, port):
    """Try known CoDeSys V2.3 protocol handshake packets."""
    print(f"\n=== CoDeSys V2.3 handshake attempts on {ip}:{port} ===")

    # CoDeSys V2.3 service packets (from protocol reverse-engineering)
    packets = [
        # CoDeSys 2.3 identify device
        (b'\x65\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
         "RegisterSession"),
        # CoDeSys symbol list request
        (b'\x00\x00\x00\x01\x00\x00\x00\x00',
         "SymbolList_v1"),
        # CoDeSys V2 get ident
        (struct.pack('<HH', 0x0004, 0x0000),
         "GetIdent_cmd4"),
        # CoDeSys V2 read all vars
        (struct.pack('<HH', 0x0065, 0x0000),
         "ReadVar_cmd65"),
        # Simple NULL
        (b'\x00' * 8, "NullProbe"),
        # CoDeSys gateway hello
        (b'\x5c\x00\x00\x00\x00\x00\x00\x00', "GW_5c"),
    ]

    for pkt, name in packets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, port))
            s.send(pkt)
            time.sleep(0.3)
            try:
                r = s.recv(512)
                if r:
                    print(f"  [{name}] Response {len(r)}b: {r.hex()}")
                    print(f"           ASCII: {r[:60]}")
                else:
                    print(f"  [{name}] Connection closed (0 bytes)")
            except socket.timeout:
                print(f"  [{name}] No response")
            s.close()
        except Exception as e:
            print(f"  [{name}] Error: {e}")
        time.sleep(0.2)


def decode_netvars(data: bytes):
    """Try to decode CoDeSys NetVars packet format."""
    if len(data) < 4:
        return
    print("\n=== Attempting NetVars decode ===")
    checksum = struct.unpack_from('<I', data, 0)[0]
    print(f"  Header (checksum?): {checksum:#010x}")
    payload = data[4:]
    print(f"  Payload ({len(payload)} bytes): {payload.hex()}")
    # Try to decode as array of uint16
    if len(payload) >= 2:
        vals_u16 = struct.unpack_from(f'<{len(payload)//2}H', payload)
        print(f"  As uint16[]: {list(vals_u16)}")
    # Try as array of int16
    if len(payload) >= 2:
        vals_i16 = struct.unpack_from(f'<{len(payload)//2}h', payload)
        print(f"  As int16[]:  {list(vals_i16)}")
    # Try as float32
    if len(payload) >= 4:
        vals_f32 = [struct.unpack_from('<f', payload, i*4)[0] for i in range(len(payload)//4)]
        print(f"  As float32[]: {[f'{v:.3f}' for v in vals_f32]}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip',   default=IP)
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()

    # 1. Try CoDeSys protocol handshakes
    try_codesys_packets(args.ip, args.port)

    # 2. Listen on TCP — maybe PLC pushes periodically when machine runs
    data = listen_tcp(args.ip, args.port, seconds=15)
    if data:
        decode_netvars(data)

    # 3. Try UDP on same port
    listen_udp(args.ip, args.port, seconds=5)

    # 4. Also try port 50000 (OrgaTEX)
    print(f"\n=== Also checking OrgaTEX port 50000 ===")
    try_codesys_packets(args.ip, 50000)
    data2 = listen_tcp(args.ip, 50000, seconds=10)
    if data2:
        decode_netvars(data2)

    print("\n=== Done ===")
