"""
Siemens S7 PLC Client — Boiler Data Acquisition
Uses python-snap7 to communicate with Siemens S7-300/400/1200/1500 PLCs.
"""

import struct
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime

try:
    import snap7
    from snap7.util import get_real, get_int, get_bool, get_dword, get_word
    SNAP7_AVAILABLE = True
except ImportError:
    SNAP7_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PLCTag:
    """Defines a single PLC data point to read."""
    name: str
    description: str
    db_number: int
    offset: int          # byte offset within the DB
    bit_offset: int = 0  # for BOOL types
    data_type: str = "REAL"   # REAL, INT, WORD, DWORD, BOOL
    unit: str = ""
    min_val: float = 0.0
    max_val: float = 100.0
    alarm_low: Optional[float] = None
    alarm_high: Optional[float] = None


@dataclass
class TagValue:
    """Holds a read value and metadata."""
    tag: PLCTag
    value: float = 0.0
    raw_bytes: bytes = b''
    timestamp: datetime = field(default_factory=datetime.now)
    quality: str = "GOOD"  # GOOD, BAD, UNCERTAIN
    alarm: str = ""        # "", "LOW", "HIGH"


# ─── Default Boiler Tags (DB1) ───────────────────────────────────
DEFAULT_BOILER_TAGS: List[PLCTag] = [
    PLCTag("steam_pressure",     "Steam Pressure",         db_number=1, offset=0,  data_type="REAL", unit="bar",  min_val=0, max_val=20,  alarm_low=2.0,  alarm_high=16.0),
    PLCTag("steam_temperature",  "Steam Temperature",      db_number=1, offset=4,  data_type="REAL", unit="°C",   min_val=0, max_val=250, alarm_low=100,  alarm_high=220),
    PLCTag("water_level",        "Water Level",            db_number=1, offset=8,  data_type="REAL", unit="%",    min_val=0, max_val=100, alarm_low=20,   alarm_high=90),
    PLCTag("feed_water_temp",    "Feed Water Temperature", db_number=1, offset=12, data_type="REAL", unit="°C",   min_val=0, max_val=120, alarm_high=105),
    PLCTag("flue_gas_temp",      "Flue Gas Temperature",   db_number=1, offset=16, data_type="REAL", unit="°C",   min_val=0, max_val=400, alarm_high=350),
    PLCTag("steam_flow",         "Steam Flow Rate",        db_number=1, offset=20, data_type="REAL", unit="T/hr", min_val=0, max_val=30),
    PLCTag("fuel_consumption",   "Fuel Consumption",       db_number=1, offset=24, data_type="REAL", unit="kg/hr",min_val=0, max_val=500),
    PLCTag("o2_percentage",      "O₂ Percentage",          db_number=1, offset=28, data_type="REAL", unit="%",    min_val=0, max_val=21,  alarm_low=2.0,  alarm_high=10.0),
    PLCTag("burner_status",      "Burner ON/OFF",          db_number=1, offset=32, data_type="BOOL", bit_offset=0, unit=""),
    PLCTag("feed_pump_status",   "Feed Pump Running",      db_number=1, offset=32, data_type="BOOL", bit_offset=1, unit=""),
    PLCTag("blowdown_valve",     "Blowdown Valve Open",    db_number=1, offset=32, data_type="BOOL", bit_offset=2, unit=""),
    PLCTag("alarm_active",       "Alarm Active",           db_number=1, offset=32, data_type="BOOL", bit_offset=3, unit=""),
    PLCTag("running_hours",      "Running Hours",          db_number=1, offset=34, data_type="DWORD", unit="hrs", min_val=0, max_val=999999),
    PLCTag("cycle_count",        "Cycle Count",            db_number=1, offset=38, data_type="DWORD", unit="",    min_val=0, max_val=999999),
]


class SiemensPLCClient:
    """Wrapper around snap7 for Siemens S7 PLC communication."""

    def __init__(self, ip: str, rack: int = 0, slot: int = 1, tcp_port: int = 102):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.tcp_port = tcp_port
        self.client: Optional[object] = None
        self.connected = False
        self.tags: List[PLCTag] = list(DEFAULT_BOILER_TAGS)
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    def connect(self) -> bool:
        """Connect to the PLC."""
        if not SNAP7_AVAILABLE:
            self._last_error = "python-snap7 library not installed"
            logger.error(self._last_error)
            return False
        try:
            self.client = snap7.client.Client()
            self.client.set_connection_params(self.ip, self.rack, self.slot)
            self.client.connect(self.ip, self.rack, self.slot, self.tcp_port)
            self.connected = self.client.get_connected()
            if self.connected:
                logger.info(f"Connected to PLC at {self.ip}")
                self._last_error = ""
            else:
                self._last_error = f"Failed to connect to {self.ip}"
            return self.connected
        except Exception as e:
            self._last_error = str(e)
            self.connected = False
            logger.error(f"Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from the PLC."""
        if self.client and self.connected:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.connected = False
        self.client = None
        logger.info("Disconnected from PLC")

    def is_connected(self) -> bool:
        """Check live connection status."""
        if not self.client:
            return False
        try:
            return self.client.get_connected()
        except Exception:
            self.connected = False
            return False

    def _read_db(self, db_number: int, start: int, size: int) -> Optional[bytearray]:
        """Read a data block area."""
        if not self.is_connected():
            return None
        try:
            return self.client.db_read(db_number, start, size)
        except Exception as e:
            self._last_error = f"DB read error: {e}"
            logger.error(self._last_error)
            return None

    def _parse_value(self, data: bytearray, tag: PLCTag, base_offset: int = 0) -> float:
        """Parse a value from raw bytes based on tag data type."""
        off = tag.offset - base_offset
        if tag.data_type == "REAL":
            return get_real(data, off)
        elif tag.data_type == "INT":
            return float(get_int(data, off))
        elif tag.data_type == "WORD":
            return float(get_word(data, off))
        elif tag.data_type == "DWORD":
            return float(get_dword(data, off))
        elif tag.data_type == "BOOL":
            return 1.0 if get_bool(data, off, tag.bit_offset) else 0.0
        else:
            return 0.0

    def read_tag(self, tag: PLCTag) -> TagValue:
        """Read a single tag from the PLC."""
        size_map = {"REAL": 4, "INT": 2, "WORD": 2, "DWORD": 4, "BOOL": 1}
        size = size_map.get(tag.data_type, 4)
        data = self._read_db(tag.db_number, tag.offset, size)
        tv = TagValue(tag=tag, timestamp=datetime.now())
        if data is None:
            tv.quality = "BAD"
            return tv
        try:
            tv.value = self._parse_value(data, tag, base_offset=tag.offset)
            tv.raw_bytes = bytes(data)
            tv.quality = "GOOD"
            # Check alarms
            if tag.data_type != "BOOL":
                if tag.alarm_high is not None and tv.value >= tag.alarm_high:
                    tv.alarm = "HIGH"
                elif tag.alarm_low is not None and tv.value <= tag.alarm_low:
                    tv.alarm = "LOW"
        except Exception as e:
            tv.quality = "BAD"
            self._last_error = f"Parse error for {tag.name}: {e}"
        return tv

    def read_all_tags(self) -> List[TagValue]:
        """Read all configured tags in an optimized batch."""
        if not self.tags:
            return []

        # Group tags by DB number for batch reads
        db_groups: Dict[int, List[PLCTag]] = {}
        for tag in self.tags:
            db_groups.setdefault(tag.db_number, []).append(tag)

        results: List[TagValue] = []
        now = datetime.now()

        for db_num, tags in db_groups.items():
            # Calculate the byte range to read
            min_offset = min(t.offset for t in tags)
            max_end = max(t.offset + (4 if t.data_type in ("REAL", "DWORD") else 2 if t.data_type in ("INT", "WORD") else 1) for t in tags)
            size = max_end - min_offset

            data = self._read_db(db_num, min_offset, size)

            for tag in tags:
                tv = TagValue(tag=tag, timestamp=now)
                if data is None:
                    tv.quality = "BAD"
                else:
                    try:
                        tv.value = self._parse_value(data, tag, base_offset=min_offset)
                        tv.quality = "GOOD"
                        if tag.data_type != "BOOL":
                            if tag.alarm_high is not None and tv.value >= tag.alarm_high:
                                tv.alarm = "HIGH"
                            elif tag.alarm_low is not None and tv.value <= tag.alarm_low:
                                tv.alarm = "LOW"
                    except Exception as e:
                        tv.quality = "BAD"
                        self._last_error = f"Parse error for {tag.name}: {e}"
                results.append(tv)

        return results

    def get_cpu_info(self) -> Dict[str, str]:
        """Get PLC CPU information."""
        if not self.is_connected():
            return {"error": "Not connected"}
        try:
            info = self.client.get_cpu_info()
            return {
                "module_type": info.ModuleTypeName.decode().strip(),
                "serial_number": info.SerialNumber.decode().strip(),
                "as_name": info.ASName.decode().strip(),
                "module_name": info.ModuleName.decode().strip(),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_cpu_state(self) -> str:
        """Get PLC CPU state (RUN / STOP / UNKNOWN)."""
        if not self.is_connected():
            return "DISCONNECTED"
        try:
            state = self.client.get_cpu_state()
            return {0: "UNKNOWN", 4: "STOP", 8: "RUN"}.get(state, f"UNKNOWN({state})")
        except Exception:
            return "UNKNOWN"

    def set_tags(self, tags: List[PLCTag]):
        """Replace the tag list."""
        self.tags = list(tags)


class SimulatedPLCClient(SiemensPLCClient):
    """Simulated PLC for testing without a real PLC."""

    def __init__(self, ip: str = "127.0.0.1", **kwargs):
        super().__init__(ip, **kwargs)
        self._sim_values: Dict[str, float] = {}
        self._tick = 0
        import random
        self._rng = random

    def connect(self) -> bool:
        self.connected = True
        self._last_error = ""
        # Initialize simulated values
        for tag in self.tags:
            if tag.data_type == "BOOL":
                self._sim_values[tag.name] = float(self._rng.choice([0, 1]))
            elif tag.data_type == "DWORD":
                self._sim_values[tag.name] = float(self._rng.randint(1000, 50000))
            else:
                mid = (tag.min_val + tag.max_val) / 2
                spread = (tag.max_val - tag.min_val) * 0.15
                self._sim_values[tag.name] = mid + self._rng.uniform(-spread, spread)
        logger.info(f"Simulated PLC connected at {self.ip}")
        return True

    def disconnect(self):
        self.connected = False
        logger.info("Simulated PLC disconnected")

    def is_connected(self) -> bool:
        return self.connected

    def read_all_tags(self) -> List[TagValue]:
        import math
        self._tick += 1
        now = datetime.now()
        results = []
        for tag in self.tags:
            tv = TagValue(tag=tag, timestamp=now, quality="GOOD")
            if tag.data_type == "BOOL":
                # Toggle occasionally
                if self._rng.random() < 0.05:
                    self._sim_values[tag.name] = 1.0 - self._sim_values.get(tag.name, 0)
                tv.value = self._sim_values.get(tag.name, 0)
            elif tag.data_type == "DWORD":
                self._sim_values[tag.name] = self._sim_values.get(tag.name, 0) + self._rng.choice([0, 0, 0, 1])
                tv.value = self._sim_values[tag.name]
            else:
                # Smooth random walk with sinusoidal component
                prev = self._sim_values.get(tag.name, (tag.min_val + tag.max_val) / 2)
                noise = self._rng.gauss(0, (tag.max_val - tag.min_val) * 0.005)
                sine = math.sin(self._tick * 0.02) * (tag.max_val - tag.min_val) * 0.02
                new_val = prev + noise + sine * 0.3
                new_val = max(tag.min_val, min(tag.max_val, new_val))
                self._sim_values[tag.name] = new_val
                tv.value = round(new_val, 2)
                # Alarm check
                if tag.alarm_high is not None and tv.value >= tag.alarm_high:
                    tv.alarm = "HIGH"
                elif tag.alarm_low is not None and tv.value <= tag.alarm_low:
                    tv.alarm = "LOW"
            results.append(tv)
        return results

    def get_cpu_info(self) -> Dict[str, str]:
        return {
            "module_type": "CPU 1214C DC/DC/DC (Simulated)",
            "serial_number": "SIM-00000001",
            "as_name": "BoilerPLC_Sim",
            "module_name": "S7-1200",
        }

    def get_cpu_state(self) -> str:
        return "RUN" if self.connected else "STOP"
