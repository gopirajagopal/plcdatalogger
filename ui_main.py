"""
Boiler PLC Monitor — PyQt5 UI
Real-time data acquisition and visualization for Siemens S7 PLCs.
"""

import sys
import csv
import os
from datetime import datetime
from collections import deque
from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QGroupBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QStatusBar, QMessageBox, QFileDialog, QFrame, QSplitter,
    QCheckBox, QTextEdit, QSizePolicy, QAction, QMenuBar, QToolBar,
    QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QBrush, QPen

import numpy as np

try:
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background='w', foreground='k')
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

from plc_client import (
    SiemensPLCClient, SimulatedPLCClient, TagValue, PLCTag,
    DEFAULT_BOILER_TAGS, SNAP7_AVAILABLE
)


# ─── Color Constants ──────────────────────────────────────────────
COLOR_BG         = "#f8f9fa"
COLOR_CARD_BG    = "#ffffff"
COLOR_PRIMARY    = "#1a73e8"
COLOR_SUCCESS    = "#0d9488"
COLOR_DANGER     = "#dc2626"
COLOR_WARNING    = "#f59e0b"
COLOR_TEXT       = "#1f2937"
COLOR_TEXT_LIGHT = "#6b7280"
COLOR_BORDER     = "#e5e7eb"
COLOR_ACCENT     = "#4f46e5"

TREND_COLORS = [
    "#1a73e8", "#dc2626", "#0d9488", "#f59e0b",
    "#7c3aed", "#ec4899", "#06b6d4", "#84cc16",
]

HISTORY_LENGTH = 300  # data points to keep for trending


# ─── Status LED Widget ───────────────────────────────────────────
class StatusLED(QWidget):
    def __init__(self, size=14, parent=None):
        super().__init__(parent)
        self._color = QColor("#9ca3af")
        self.setFixedSize(size, size)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(QPen(self._color.darker(130), 1))
        margin = 1
        p.drawEllipse(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)
        # highlight
        p.setBrush(QBrush(QColor(255, 255, 255, 80)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(3, 2, self.width() // 3, self.height() // 3)
        p.end()


# ─── Gauge Card Widget ───────────────────────────────────────────
class GaugeCard(QFrame):
    """A compact card showing a single analog value with bar gauge."""

    def __init__(self, tag: PLCTag, parent=None):
        super().__init__(parent)
        self.tag = tag
        self._value = 0.0
        self._alarm = ""
        self._quality = "GOOD"

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            GaugeCard {{
                background: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        self.setMinimumSize(180, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title
        self.lbl_title = QLabel(tag.description)
        self.lbl_title.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.lbl_title.setStyleSheet(f"color: {COLOR_TEXT_LIGHT}; border: none;")
        layout.addWidget(self.lbl_title)

        # Value row
        h = QHBoxLayout()
        h.setSpacing(4)
        self.lbl_value = QLabel("—")
        self.lbl_value.setFont(QFont("Consolas", 18, QFont.Bold))
        self.lbl_value.setStyleSheet(f"color: {COLOR_TEXT}; border: none;")
        h.addWidget(self.lbl_value)

        self.lbl_unit = QLabel(tag.unit)
        self.lbl_unit.setFont(QFont("Segoe UI", 9))
        self.lbl_unit.setStyleSheet(f"color: {COLOR_TEXT_LIGHT}; border: none;")
        self.lbl_unit.setAlignment(Qt.AlignBottom)
        h.addWidget(self.lbl_unit)
        h.addStretch()

        self.led = StatusLED(10)
        h.addWidget(self.led)
        layout.addLayout(h)

        # Bar gauge
        if tag.data_type != "BOOL":
            self.bar = QFrame()
            self.bar.setFixedHeight(6)
            self.bar.setStyleSheet(f"background: {COLOR_BORDER}; border-radius: 3px; border: none;")
            layout.addWidget(self.bar)

            self.bar_fill = QFrame(self.bar)
            self.bar_fill.setFixedHeight(6)
            self.bar_fill.setStyleSheet(f"background: {COLOR_PRIMARY}; border-radius: 3px; border: none;")
            self.bar_fill.setGeometry(0, 0, 0, 6)

            # Range label
            self.lbl_range = QLabel(f"{tag.min_val} — {tag.max_val}")
            self.lbl_range.setFont(QFont("Segoe UI", 7))
            self.lbl_range.setStyleSheet(f"color: {COLOR_TEXT_LIGHT}; border: none;")
            self.lbl_range.setAlignment(Qt.AlignRight)
            layout.addWidget(self.lbl_range)
        else:
            self.bar = None
            self.bar_fill = None

    def update_value(self, tv: TagValue):
        self._value = tv.value
        self._alarm = tv.alarm
        self._quality = tv.quality

        if self._quality == "BAD":
            self.lbl_value.setText("ERR")
            self.lbl_value.setStyleSheet(f"color: {COLOR_DANGER}; border: none;")
            self.led.set_color(COLOR_DANGER)
            return

        if self.tag.data_type == "BOOL":
            is_on = tv.value > 0.5
            self.lbl_value.setText("ON" if is_on else "OFF")
            color = COLOR_SUCCESS if is_on else COLOR_TEXT_LIGHT
            self.lbl_value.setStyleSheet(f"color: {color}; border: none;")
            self.led.set_color(COLOR_SUCCESS if is_on else "#9ca3af")
        else:
            self.lbl_value.setText(f"{tv.value:.1f}")
            if tv.alarm == "HIGH":
                color = COLOR_DANGER
            elif tv.alarm == "LOW":
                color = COLOR_WARNING
            else:
                color = COLOR_TEXT
            self.lbl_value.setStyleSheet(f"color: {color}; border: none;")
            self.led.set_color(COLOR_SUCCESS if not tv.alarm else (COLOR_DANGER if tv.alarm == "HIGH" else COLOR_WARNING))

            # Update bar
            if self.bar_fill:
                rng = self.tag.max_val - self.tag.min_val
                pct = max(0, min(1, (tv.value - self.tag.min_val) / rng)) if rng > 0 else 0
                w = int(self.bar.width() * pct)
                bar_color = COLOR_DANGER if tv.alarm == "HIGH" else (COLOR_WARNING if tv.alarm == "LOW" else COLOR_PRIMARY)
                self.bar_fill.setFixedWidth(max(0, w))
                self.bar_fill.setStyleSheet(f"background: {bar_color}; border-radius: 3px; border: none;")


# ─── Alarm Log Widget ────────────────────────────────────────────
class AlarmLog(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            AlarmLog {{
                background: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel("Alarm Log")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        lbl.setStyleSheet(f"color: {COLOR_TEXT}; border: none;")
        layout.addWidget(lbl)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 8))
        self.text.setStyleSheet(f"border: 1px solid {COLOR_BORDER}; border-radius: 4px; background: #fafafa;")
        layout.addWidget(self.text)

        self._entries: List[str] = []
        self._active_alarms: set = set()

    def process_values(self, values: List[TagValue]):
        for tv in values:
            key = tv.tag.name
            if tv.alarm and key not in self._active_alarms:
                self._active_alarms.add(key)
                ts = tv.timestamp.strftime("%H:%M:%S")
                color = "red" if tv.alarm == "HIGH" else "#b45309"
                entry = f'<span style="color:{color}; font-weight:bold;">[{ts}] {tv.alarm} ALARM — {tv.tag.description}: {tv.value:.1f} {tv.tag.unit}</span>'
                self._entries.append(entry)
                self.text.append(entry)
            elif not tv.alarm and key in self._active_alarms:
                self._active_alarms.discard(key)
                ts = tv.timestamp.strftime("%H:%M:%S")
                entry = f'<span style="color:{COLOR_SUCCESS};">[{ts}] CLEARED — {tv.tag.description}: {tv.value:.1f} {tv.tag.unit}</span>'
                self._entries.append(entry)
                self.text.append(entry)

    @property
    def active_count(self) -> int:
        return len(self._active_alarms)


# ─── Main Window ─────────────────────────────────────────────────
class BoilerMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Boiler PLC Monitor — Siemens S7")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)

        # State
        self.plc_client: Optional[SiemensPLCClient] = None
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_plc)
        self.trend_data: Dict[str, deque] = {}
        self.time_data: deque = deque(maxlen=HISTORY_LENGTH)
        self.gauge_cards: Dict[str, GaugeCard] = {}
        self.trend_curves: Dict[str, object] = {}
        self._tick = 0

        # Apply palette
        self.setStyleSheet(f"""
            QMainWindow {{ background: {COLOR_BG}; }}
            QTabWidget::pane {{ border: 1px solid {COLOR_BORDER}; border-radius: 6px; background: {COLOR_BG}; }}
            QTabBar::tab {{ padding: 8px 16px; font-size: 11px; font-weight: 600; color: {COLOR_TEXT_LIGHT}; border: none; border-bottom: 2px solid transparent; }}
            QTabBar::tab:selected {{ color: {COLOR_PRIMARY}; border-bottom: 2px solid {COLOR_PRIMARY}; }}
            QTabBar::tab:hover {{ color: {COLOR_TEXT}; }}
        """)

        self._build_ui()
        self._update_status("Ready — Enter PLC IP and connect")

    # ── Build UI ──────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        # ─ Connection Bar ─
        conn_frame = QFrame()
        conn_frame.setStyleSheet(f"""
            QFrame {{ background: {COLOR_CARD_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 4px; }}
        """)
        conn_layout = QHBoxLayout(conn_frame)
        conn_layout.setContentsMargins(12, 6, 12, 6)
        conn_layout.setSpacing(10)

        self.conn_led = StatusLED(12)
        conn_layout.addWidget(self.conn_led)

        conn_layout.addWidget(self._label("PLC IP:", bold=True))
        self.ip_input = QLineEdit("192.168.0.1")
        self.ip_input.setFixedWidth(160)
        self.ip_input.setPlaceholderText("e.g. 192.168.0.1")
        self.ip_input.setStyleSheet(self._input_style())
        conn_layout.addWidget(self.ip_input)

        conn_layout.addWidget(self._label("Rack:", bold=True))
        self.rack_spin = QSpinBox()
        self.rack_spin.setRange(0, 7)
        self.rack_spin.setValue(0)
        self.rack_spin.setFixedWidth(60)
        self.rack_spin.setStyleSheet(self._input_style())
        conn_layout.addWidget(self.rack_spin)

        conn_layout.addWidget(self._label("Slot:", bold=True))
        self.slot_spin = QSpinBox()
        self.slot_spin.setRange(0, 31)
        self.slot_spin.setValue(1)
        self.slot_spin.setFixedWidth(60)
        self.slot_spin.setStyleSheet(self._input_style())
        conn_layout.addWidget(self.slot_spin)

        conn_layout.addWidget(self._label("Poll (ms):", bold=True))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(100, 10000)
        self.poll_spin.setValue(1000)
        self.poll_spin.setSingleStep(100)
        self.poll_spin.setFixedWidth(80)
        self.poll_spin.setStyleSheet(self._input_style())
        conn_layout.addWidget(self.poll_spin)

        self.chk_simulate = QCheckBox("Simulate")
        self.chk_simulate.setFont(QFont("Segoe UI", 9))
        self.chk_simulate.setChecked(not SNAP7_AVAILABLE)
        conn_layout.addWidget(self.chk_simulate)

        conn_layout.addStretch()

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setFixedSize(110, 32)
        self.btn_connect.setStyleSheet(self._btn_style(COLOR_PRIMARY))
        self.btn_connect.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.btn_connect)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setFixedSize(100, 32)
        self.btn_export.setStyleSheet(self._btn_style("#6b7280"))
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_export.setEnabled(False)
        conn_layout.addWidget(self.btn_export)

        root.addWidget(conn_frame)

        # ─ Tab Widget ─
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab 1: Dashboard
        self._build_dashboard_tab()

        # Tab 2: Trend Charts
        self._build_trend_tab()

        # Tab 3: Data Table
        self._build_table_tab()

        # Tab 4: PLC Info
        self._build_info_tab()

        # ─ Status Bar ─
        self.statusBar().setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_LIGHT};")

    # ── Dashboard Tab ─────────────────────────────────────────────
    def _build_dashboard_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(8)

        # Gauge cards grid
        self.gauge_grid = QGridLayout()
        self.gauge_grid.setSpacing(8)

        analog_tags = [t for t in DEFAULT_BOILER_TAGS if t.data_type != "BOOL"]
        bool_tags = [t for t in DEFAULT_BOILER_TAGS if t.data_type == "BOOL"]
        counter_tags = [t for t in DEFAULT_BOILER_TAGS if t.data_type == "DWORD"]
        # Separate analogs from counters
        pure_analog = [t for t in analog_tags if t.data_type not in ("DWORD",)]

        col = 0
        row = 0
        cols_per_row = 4
        for tag in pure_analog:
            card = GaugeCard(tag)
            self.gauge_cards[tag.name] = card
            self.gauge_grid.addWidget(card, row, col)
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1

        layout.addLayout(self.gauge_grid)

        # Status indicators row
        status_frame = QFrame()
        status_frame.setStyleSheet(f"QFrame {{ background: {COLOR_CARD_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.setSpacing(20)

        for tag in bool_tags:
            card = GaugeCard(tag)
            card.setMinimumSize(140, 80)
            self.gauge_cards[tag.name] = card
            status_layout.addWidget(card)

        for tag in counter_tags:
            card = GaugeCard(tag)
            card.setMinimumSize(140, 80)
            self.gauge_cards[tag.name] = card
            status_layout.addWidget(card)

        status_layout.addStretch()
        layout.addWidget(status_frame)

        # Alarm log
        self.alarm_log = AlarmLog()
        self.alarm_log.setMaximumHeight(180)
        layout.addWidget(self.alarm_log)

        self.tabs.addTab(page, "Dashboard")

    # ── Trend Tab ─────────────────────────────────────────────────
    def _build_trend_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)

        if not PYQTGRAPH_AVAILABLE:
            layout.addWidget(QLabel("pyqtgraph not installed — trend charts unavailable.\npip install pyqtgraph"))
            self.trend_plot = None
            self.tabs.addTab(page, "Trends")
            return

        # Controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(self._label("Visible Tags:", bold=True))
        self.trend_checks: Dict[str, QCheckBox] = {}
        analog_tags = [t for t in DEFAULT_BOILER_TAGS if t.data_type not in ("BOOL", "DWORD")]
        for i, tag in enumerate(analog_tags):
            cb = QCheckBox(tag.description)
            cb.setChecked(i < 4)
            cb.setFont(QFont("Segoe UI", 8))
            cb.setStyleSheet(f"color: {TREND_COLORS[i % len(TREND_COLORS)]};")
            cb.stateChanged.connect(self._update_trend_visibility)
            self.trend_checks[tag.name] = cb
            ctrl.addWidget(cb)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Plot
        self.trend_plot = pg.PlotWidget()
        self.trend_plot.setLabel('bottom', 'Time', units='s')
        self.trend_plot.setLabel('left', 'Value')
        self.trend_plot.showGrid(x=True, y=True, alpha=0.15)
        self.trend_plot.addLegend(offset=(10, 10))

        for i, tag in enumerate(analog_tags):
            color = TREND_COLORS[i % len(TREND_COLORS)]
            curve = self.trend_plot.plot([], [], pen=pg.mkPen(color=color, width=2), name=tag.description)
            self.trend_curves[tag.name] = curve
            self.trend_data[tag.name] = deque(maxlen=HISTORY_LENGTH)
            curve.setVisible(i < 4)

        layout.addWidget(self.trend_plot, 1)
        self.tabs.addTab(page, "Trends")

    # ── Table Tab ─────────────────────────────────────────────────
    def _build_table_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)

        self.data_table = QTableWidget()
        self.data_table.setColumnCount(8)
        self.data_table.setHorizontalHeaderLabels([
            "Tag Name", "Description", "Value", "Unit", "Quality",
            "Alarm", "Range", "Timestamp"
        ])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setStyleSheet(f"""
            QTableWidget {{ border: 1px solid {COLOR_BORDER}; border-radius: 6px; gridline-color: {COLOR_BORDER}; font-size: 11px; }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QHeaderView::section {{ background: #f3f4f6; font-weight: 600; font-size: 10px; padding: 6px; border: none; border-bottom: 1px solid {COLOR_BORDER}; }}
        """)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.data_table.setSelectionBehavior(QTableWidget.SelectRows)

        # Pre-fill rows
        self.data_table.setRowCount(len(DEFAULT_BOILER_TAGS))
        for i, tag in enumerate(DEFAULT_BOILER_TAGS):
            self.data_table.setItem(i, 0, QTableWidgetItem(tag.name))
            self.data_table.setItem(i, 1, QTableWidgetItem(tag.description))
            self.data_table.setItem(i, 2, QTableWidgetItem("—"))
            self.data_table.setItem(i, 3, QTableWidgetItem(tag.unit))
            self.data_table.setItem(i, 4, QTableWidgetItem("—"))
            self.data_table.setItem(i, 5, QTableWidgetItem(""))
            self.data_table.setItem(i, 6, QTableWidgetItem(f"{tag.min_val} – {tag.max_val}"))
            self.data_table.setItem(i, 7, QTableWidgetItem(""))

        layout.addWidget(self.data_table, 1)
        self.tabs.addTab(page, "Data Table")

    # ── PLC Info Tab ──────────────────────────────────────────────
    def _build_info_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)

        grp = QGroupBox("PLC Information")
        grp.setFont(QFont("Segoe UI", 10, QFont.Bold))
        grp.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {COLOR_BORDER}; border-radius: 8px; margin-top: 12px; padding: 16px; background: {COLOR_CARD_BG}; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 8px; color: {COLOR_TEXT}; }}
        """)
        g = QGridLayout(grp)
        g.setSpacing(8)

        labels = ["Module Type", "Serial Number", "AS Name", "Module Name", "CPU State", "IP Address", "Rack", "Slot"]
        self.info_labels: Dict[str, QLabel] = {}
        for i, lbl in enumerate(labels):
            g.addWidget(self._label(f"{lbl}:", bold=True), i, 0)
            val = QLabel("—")
            val.setFont(QFont("Consolas", 10))
            val.setStyleSheet(f"color: {COLOR_TEXT};")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info_labels[lbl.lower().replace(" ", "_")] = val
            g.addWidget(val, i, 1)

        layout.addWidget(grp)
        layout.addStretch()
        self.tabs.addTab(page, "PLC Info")

    # ── Connection ────────────────────────────────────────────────
    def _toggle_connection(self):
        if self.plc_client and self.plc_client.is_connected():
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Error", "Please enter a PLC IP address.")
            return

        rack = self.rack_spin.value()
        slot = self.slot_spin.value()
        simulate = self.chk_simulate.isChecked()

        self._update_status(f"Connecting to {ip} (rack={rack}, slot={slot})...")
        QApplication.processEvents()

        if simulate:
            self.plc_client = SimulatedPLCClient(ip, rack=rack, slot=slot)
        else:
            if not SNAP7_AVAILABLE:
                QMessageBox.warning(self, "Missing Library",
                    "python-snap7 is not installed.\n\nInstall it with:\n  pip install python-snap7\n\nOr enable 'Simulate' mode to test the UI.")
                return
            self.plc_client = SiemensPLCClient(ip, rack=rack, slot=slot)

        ok = self.plc_client.connect()
        if not ok:
            QMessageBox.critical(self, "Connection Failed",
                f"Could not connect to PLC at {ip}\n\n{self.plc_client.last_error}")
            self.plc_client = None
            return

        # Update UI state
        self.conn_led.set_color(COLOR_SUCCESS)
        self.btn_connect.setText("Disconnect")
        self.btn_connect.setStyleSheet(self._btn_style(COLOR_DANGER))
        self.ip_input.setEnabled(False)
        self.rack_spin.setEnabled(False)
        self.slot_spin.setEnabled(False)
        self.chk_simulate.setEnabled(False)
        self.btn_export.setEnabled(True)

        # Clear trend data
        self.time_data.clear()
        for d in self.trend_data.values():
            d.clear()
        self._tick = 0

        # Fetch PLC info
        self._refresh_plc_info()

        # Start polling
        self.poll_timer.start(self.poll_spin.value())
        mode = "SIMULATED" if simulate else "LIVE"
        self._update_status(f"Connected to {ip} [{mode}] — Polling every {self.poll_spin.value()}ms")

    def _disconnect(self):
        self.poll_timer.stop()
        if self.plc_client:
            self.plc_client.disconnect()
            self.plc_client = None

        self.conn_led.set_color("#9ca3af")
        self.btn_connect.setText("Connect")
        self.btn_connect.setStyleSheet(self._btn_style(COLOR_PRIMARY))
        self.ip_input.setEnabled(True)
        self.rack_spin.setEnabled(True)
        self.slot_spin.setEnabled(True)
        self.chk_simulate.setEnabled(True)
        self.btn_export.setEnabled(False)
        self._update_status("Disconnected")

    # ── Polling ───────────────────────────────────────────────────
    def _poll_plc(self):
        if not self.plc_client or not self.plc_client.is_connected():
            self._disconnect()
            return

        values = self.plc_client.read_all_tags()
        self._tick += 1
        self.time_data.append(self._tick)

        # Update gauge cards
        for tv in values:
            card = self.gauge_cards.get(tv.tag.name)
            if card:
                card.update_value(tv)

        # Update trend data
        for tv in values:
            if tv.tag.name in self.trend_data:
                self.trend_data[tv.tag.name].append(tv.value)

        # Update trend curves
        if self.trend_plot and PYQTGRAPH_AVAILABLE:
            t_arr = list(self.time_data)
            for name, curve in self.trend_curves.items():
                if name in self.trend_data and len(self.trend_data[name]) > 0:
                    curve.setData(t_arr[-len(self.trend_data[name]):], list(self.trend_data[name]))

        # Update data table
        for i, tv in enumerate(values):
            if i < self.data_table.rowCount():
                self.data_table.item(i, 2).setText(
                    f"{tv.value:.2f}" if tv.tag.data_type not in ("BOOL",) else ("ON" if tv.value > 0.5 else "OFF")
                )
                self.data_table.item(i, 4).setText(tv.quality)
                alarm_item = self.data_table.item(i, 5)
                alarm_item.setText(tv.alarm)
                if tv.alarm == "HIGH":
                    alarm_item.setBackground(QColor("#fef2f2"))
                    alarm_item.setForeground(QColor(COLOR_DANGER))
                elif tv.alarm == "LOW":
                    alarm_item.setBackground(QColor("#fffbeb"))
                    alarm_item.setForeground(QColor("#b45309"))
                else:
                    alarm_item.setBackground(QColor("white"))
                    alarm_item.setForeground(QColor(COLOR_TEXT))
                self.data_table.item(i, 7).setText(tv.timestamp.strftime("%H:%M:%S.%f")[:-3])

        # Alarms
        self.alarm_log.process_values(values)

        # Status bar
        active = self.alarm_log.active_count
        alarm_txt = f" | {active} active alarm(s)" if active else ""
        self.statusBar().showMessage(
            f"Polling #{self._tick} — {len(values)} tags{alarm_txt} — {datetime.now().strftime('%H:%M:%S')}"
        )

    # ── PLC Info ──────────────────────────────────────────────────
    def _refresh_plc_info(self):
        if not self.plc_client:
            return
        info = self.plc_client.get_cpu_info()
        state = self.plc_client.get_cpu_state()

        mapping = {
            "module_type": info.get("module_type", "—"),
            "serial_number": info.get("serial_number", "—"),
            "as_name": info.get("as_name", "—"),
            "module_name": info.get("module_name", "—"),
            "cpu_state": state,
            "ip_address": self.plc_client.ip,
            "rack": str(self.plc_client.rack),
            "slot": str(self.plc_client.slot),
        }
        for key, val in mapping.items():
            lbl = self.info_labels.get(key)
            if lbl:
                lbl.setText(val)

    # ── Export CSV ────────────────────────────────────────────────
    def _export_csv(self):
        if not self.plc_client:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", f"boiler_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return

        values = self.plc_client.read_all_tags()
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Tag Name", "Description", "Value", "Unit", "Quality", "Alarm", "Timestamp"])
                for tv in values:
                    writer.writerow([
                        tv.tag.name, tv.tag.description,
                        f"{tv.value:.2f}" if tv.tag.data_type != "BOOL" else ("ON" if tv.value > 0.5 else "OFF"),
                        tv.tag.unit, tv.quality, tv.alarm,
                        tv.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    ])
            self._update_status(f"Exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    # ── Trend Visibility ──────────────────────────────────────────
    def _update_trend_visibility(self):
        for name, cb in self.trend_checks.items():
            curve = self.trend_curves.get(name)
            if curve:
                curve.setVisible(cb.isChecked())

    # ── Helpers ───────────────────────────────────────────────────
    def _label(self, text: str, bold=False) -> QLabel:
        lbl = QLabel(text)
        weight = QFont.Bold if bold else QFont.Normal
        lbl.setFont(QFont("Segoe UI", 9, weight))
        lbl.setStyleSheet(f"color: {COLOR_TEXT}; border: none;")
        return lbl

    def _input_style(self) -> str:
        return f"""
            font-size: 11px; font-family: Consolas;
            border: 1px solid {COLOR_BORDER}; border-radius: 4px;
            padding: 4px 8px; background: white; color: {COLOR_TEXT};
        """

    def _btn_style(self, bg: str) -> str:
        return f"""
            QPushButton {{
                background: {bg}; color: white; border: none; border-radius: 6px;
                font-size: 11px; font-weight: 600; font-family: 'Segoe UI';
            }}
            QPushButton:hover {{ background: {bg}; opacity: 0.9; }}
            QPushButton:disabled {{ background: #d1d5db; }}
        """

    def _update_status(self, msg: str):
        self.statusBar().showMessage(msg)

    def closeEvent(self, event):
        self.poll_timer.stop()
        if self.plc_client:
            self.plc_client.disconnect()
        event.accept()
