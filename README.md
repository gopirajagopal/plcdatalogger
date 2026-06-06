# Boiler PLC Monitor — Siemens S7

Real-time data acquisition and visualization for Siemens S7 PLCs (S7-300/400/1200/1500) used in factory boilers for dyeing operations.

## Features

- **Live Data Acquisition** — Reads boiler parameters via Siemens S7 protocol (snap7)
- **Dashboard** — Gauge cards with bar indicators, status LEDs, alarm thresholds
- **Trend Charts** — Real-time scrolling charts for analog values (pyqtgraph)
- **Data Table** — Tabular view of all tags with quality and alarm status
- **PLC Info** — CPU module type, serial number, state
- **Alarm Log** — High/Low alarm detection with timestamped log
- **CSV Export** — Export current snapshot to CSV
- **Simulation Mode** — Test the UI without a real PLC

## Default Boiler Tags (DB1)

| Tag | Description | Unit | Alarm Low | Alarm High |
|-----|------------|------|-----------|------------|
| steam_pressure | Steam Pressure | bar | 2.0 | 16.0 |
| steam_temperature | Steam Temperature | °C | 100 | 220 |
| water_level | Water Level | % | 20 | 90 |
| feed_water_temp | Feed Water Temperature | °C | — | 105 |
| flue_gas_temp | Flue Gas Temperature | °C | — | 350 |
| steam_flow | Steam Flow Rate | T/hr | — | — |
| fuel_consumption | Fuel Consumption | kg/hr | — | — |
| o2_percentage | O₂ Percentage | % | 2.0 | 10.0 |
| burner_status | Burner ON/OFF | — | — | — |
| feed_pump_status | Feed Pump Running | — | — | — |
| blowdown_valve | Blowdown Valve Open | — | — | — |
| alarm_active | Alarm Active | — | — | — |
| running_hours | Running Hours | hrs | — | — |
| cycle_count | Cycle Count | — | — | — |

## Setup

```bash
cd plc_monitor
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Simulation Mode

If `python-snap7` is not installed or you want to test without a PLC, check the **Simulate** checkbox before connecting. The app will generate realistic simulated boiler data.

## Build Executable

```bash
build.bat
```

This will:
1. Install dependencies
2. Build a standalone `.exe` using PyInstaller
3. Create a `.zip` archive in `dist/BoilerPLCMonitor.zip`

Output:
- `dist/BoilerPLCMonitor/BoilerPLCMonitor.exe`
- `dist/BoilerPLCMonitor.zip`

## PLC Configuration

- **Protocol**: S7 (TCP port 102)
- **Default**: Rack 0, Slot 1 (adjust for your hardware)
- **Data Block**: DB1 (default — edit `plc_client.py` to change)

### Siemens PLC Slot Reference

| PLC Model | Rack | Slot |
|-----------|------|------|
| S7-300 | 0 | 2 |
| S7-400 | 0 | 2 or 3 |
| S7-1200 | 0 | 1 |
| S7-1500 | 0 | 1 |

## Customizing Tags

Edit the `DEFAULT_BOILER_TAGS` list in `plc_client.py` to match your PLC's data block layout:

```python
PLCTag("my_tag", "My Description", db_number=1, offset=0, data_type="REAL", unit="bar", alarm_high=10.0)
```

Supported data types: `REAL`, `INT`, `WORD`, `DWORD`, `BOOL`

## Requirements

- Python 3.8+
- PyQt5
- python-snap7 (for real PLC connection)
- pyqtgraph (for trend charts)
- numpy
