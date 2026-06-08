"""
PLC client for SETEX 797TCE (CoDeSys V2) via Modbus TCP.

CoDeSys V2 Modbus slave mapping:
  %MW0, %MW1 ...  →  Holding registers  0, 1 ...  (FC3 read_holding_registers)
  %MX0.0 ...      →  Coils              0 ...      (FC1 read_coils)
  %IW0, %IW1 ...  →  Input registers    0, 1 ...   (FC4 read_input_registers)

Machine: SECOM-AK04  |  IP: 192.168.1.220  |  Port: 502  |  Slave ID: 1
"""

import struct
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable

import pymodbus as _pymodbus_pkg
try:
    from pymodbus.client import ModbusTcpClient          # pymodbus >= 3.0
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient    # pymodbus 2.x fallback
_PYMODBUS3 = int(_pymodbus_pkg.__version__.split('.')[0]) >= 3

def _slave_kwarg(slave_id: int) -> dict:
    return {'slave': slave_id} if _PYMODBUS3 else {'unit': slave_id}

log = logging.getLogger(__name__)


@dataclass
class Tag:
    name: str
    address: int        # Modbus register address (0-based = %MW0, %MW1 ...)
    dtype: str          # 'uint16' | 'int16' | 'float32' | 'bool' | 'coil'
    bit: int = 0        # for dtype='bool': which bit within the holding register
    unit: str = ''
    description: str = ''
    scale: float = 1.0
    offset: float = 0.0
    slave_id: int = 1
    hi_alarm: Optional[float] = None
    lo_alarm: Optional[float] = None
    trend: bool = True


@dataclass
class TagValue:
    name: str
    value: float = 0.0
    alarm: bool = False
    error: bool = False
    quality: str = 'bad'    # 'good' | 'bad'
    timestamp: float = field(default_factory=time.time)


class PLCClient:
    """
    Modbus TCP client for SETEX 797TCE (CoDeSys V2).

    CoDeSys V2 exposes machine data as a Modbus slave (port 502).
    Tag addresses map directly to CoDeSys %MW addresses:
        Tag(address=0)  →  reads %MW0  (holding register 0)
        Tag(address=10) →  reads %MW10 (holding register 10)

    float32 values occupy two consecutive registers (%MW N and %MW N+1),
    big-endian word order: high word first.
    """

    def __init__(self):
        self._client: Optional[ModbusTcpClient] = None
        self._connected = False
        self._lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._tags: List[Tag] = []
        self._values: Dict[str, TagValue] = {}
        self._callbacks: List[Callable[[Dict[str, TagValue]], None]] = []

        self.ip = '192.168.1.220'   # SECOM-AK04 default
        self.port = 502
        self.timeout = 3.0
        self.poll_interval = 1.0

    # ── Tag management ──────────────────────────────────────────────────────

    def set_tags(self, tags: List[Tag]):
        self._tags = list(tags)
        self._values = {t.name: TagValue(name=t.name) for t in tags}

    def get_tag(self, name: str) -> Optional[Tag]:
        return next((t for t in self._tags if t.name == name), None)

    @property
    def tags(self) -> List[Tag]:
        return list(self._tags)

    # ── Connection ───────────────────────────────────────────────────────────

    def connect(self, ip: str = None, port: int = None) -> bool:
        if ip:
            self.ip = ip
        if port:
            self.port = port
        try:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = ModbusTcpClient(
                host=self.ip,
                port=self.port,
                timeout=self.timeout,
            )
            self._connected = bool(self._client.connect())
            log.info('Modbus %s:%s → %s', self.ip, self.port,
                     'connected' if self._connected else 'failed')
        except Exception as exc:
            log.warning('Connect error: %s', exc)
            self._connected = False
        return self._connected

    def disconnect(self):
        self.stop_polling()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Low-level Modbus reads ────────────────────────────────────────────────

    def _read_holding(self, address: int, count: int, slave: int) -> Optional[List[int]]:
        """FC3 – read holding registers (%MW). Returns list of uint16."""
        try:
            rr = self._client.read_holding_registers(address, count=count, **_slave_kwarg(slave))
            if rr.isError():
                return None
            return list(rr.registers)
        except Exception as exc:
            log.debug('FC3 err @%s: %s', address, exc)
            return None

    def _read_input(self, address: int, count: int, slave: int) -> Optional[List[int]]:
        """FC4 – read input registers (%IW). Returns list of uint16."""
        try:
            rr = self._client.read_input_registers(address, count=count, **_slave_kwarg(slave))
            if rr.isError():
                return None
            return list(rr.registers)
        except Exception as exc:
            log.debug('FC4 err @%s: %s', address, exc)
            return None

    def _read_coils(self, address: int, count: int, slave: int) -> Optional[List[bool]]:
        """FC1 – read coils (%MX). Returns list of bool."""
        try:
            rr = self._client.read_coils(address, count=count, **_slave_kwarg(slave))
            if rr.isError():
                return None
            return list(rr.bits[:count])
        except Exception as exc:
            log.debug('FC1 err @%s: %s', address, exc)
            return None

    # ── Tag decode ────────────────────────────────────────────────────────────

    def _decode_tag(self, tag: Tag) -> Optional[float]:
        s = tag.slave_id

        if tag.dtype == 'coil':
            bits = self._read_coils(tag.address, 1, s)
            return float(bits[0]) if bits is not None else None

        elif tag.dtype == 'uint16':
            regs = self._read_holding(tag.address, 1, s)
            if regs is None:
                return None
            return float(regs[0]) * tag.scale + tag.offset

        elif tag.dtype == 'int16':
            regs = self._read_holding(tag.address, 1, s)
            if regs is None:
                return None
            val = struct.unpack('>h', struct.pack('>H', regs[0]))[0]
            return float(val) * tag.scale + tag.offset

        elif tag.dtype == 'float32':
            regs = self._read_holding(tag.address, 2, s)
            if regs is None or len(regs) < 2:
                return None
            val = struct.unpack('>f', struct.pack('>HH', regs[0], regs[1]))[0]
            return float(val) * tag.scale + tag.offset

        elif tag.dtype == 'bool':
            # Bit inside a holding register (%MX equivalent via %MW)
            regs = self._read_holding(tag.address, 1, s)
            if regs is None:
                return None
            return float((regs[0] >> tag.bit) & 1)

        return None

    # ── Polling ──────────────────────────────────────────────────────────────

    def _poll_once(self) -> Dict[str, TagValue]:
        updated: Dict[str, TagValue] = {}
        for tag in self._tags:
            tv = TagValue(name=tag.name, timestamp=time.time())
            try:
                val = self._decode_tag(tag)
                if val is None:
                    tv.error = True
                    tv.quality = 'bad'
                    # individual register read failed — keep connection alive
                else:
                    tv.value = round(val, 4)
                    tv.quality = 'good'
                    tv.alarm = bool(
                        (tag.hi_alarm is not None and val > tag.hi_alarm) or
                        (tag.lo_alarm is not None and val < tag.lo_alarm)
                    )
            except OSError:
                # TCP-level socket error — mark disconnected so reconnect kicks in
                tv.error = True
                tv.quality = 'bad'
                self._connected = False
                log.warning('TCP error during poll [%s] — will reconnect', tag.name)
            except Exception as exc:
                tv.error = True
                tv.quality = 'bad'
                log.debug('poll [%s]: %s', tag.name, exc)
            updated[tag.name] = tv
        return updated

    def _poll_loop(self):
        while self._running:
            if not self._connected:
                log.info('Reconnecting to %s…', self.ip)
                self.connect()
                if not self._connected:
                    time.sleep(self.poll_interval)
                    continue
            updated = self._poll_once()
            self._values.update(updated)
            for cb in list(self._callbacks):
                try:
                    cb(updated)
                except Exception:
                    pass
            time.sleep(self.poll_interval)

    def start_polling(self):
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name='plc-poll')
        self._poll_thread.start()

    def stop_polling(self):
        self._running = False

    def add_data_callback(self, cb: Callable[[Dict[str, TagValue]], None]):
        self._callbacks.append(cb)

    def get_values(self) -> Dict[str, TagValue]:
        return dict(self._values)
