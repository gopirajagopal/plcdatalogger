"""
SETEX 797TCE Monitor — PyQt5 main window
Dark industrial theme. Real-time Modbus TCP data via pyqtgraph.
"""

import struct
import time
from collections import deque
from typing import Dict, List

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSpinBox, QDoubleSpinBox,
    QSplitter, QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from plc_client import PLCClient, Tag, TagValue

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = '#12121e'
CARD_BG = '#1c1c2e'
PANEL   = '#16162a'
ACCENT  = '#10a37f'
ALARM   = '#e17055'
WARN    = '#fdcb6e'
MUTED   = '#636e72'
TEXT    = '#dfe6e9'
BORDER  = '#2d3436'
LED_ON  = '#00b894'
LED_OFF = '#e17055'

TREND_COLORS = ['#74b9ff', '#00b894', '#fdcb6e', '#e17055', '#a29bfe',
                '#fd79a8', '#55efc4', '#ffeaa7']

_BASE_STYLE = f"""
    QWidget       {{ background: {BG};     color: {TEXT}; font-size: 12px; }}
    QGroupBox     {{ border: 1px solid {BORDER}; border-radius: 6px; margin-top: 6px;
                     padding-top: 4px; color: {MUTED}; font-size: 11px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}
    QPushButton   {{ background: {PANEL};  color: {TEXT};   border: 1px solid {BORDER};
                     border-radius: 4px; padding: 4px 12px; }}
    QPushButton:hover {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
    QPushButton:pressed {{ background: #0a7a60; }}
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {CARD_BG}; color: {TEXT}; border: 1px solid {BORDER};
        border-radius: 4px; padding: 3px 6px; }}
    QTableWidget  {{ background: {CARD_BG}; gridline-color: {BORDER};
                     border: 1px solid {BORDER}; }}
    QHeaderView::section {{ background: {PANEL}; color: {MUTED};
                            border: none; padding: 4px 8px; }}
    QTabWidget::pane {{ border: 1px solid {BORDER}; }}
    QTabBar::tab    {{ background: {PANEL}; color: {MUTED}; padding: 6px 16px;
                       border: 1px solid {BORDER}; border-bottom: none; }}
    QTabBar::tab:selected {{ background: {CARD_BG}; color: {TEXT}; }}
    QScrollBar:vertical {{ background: {BG}; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; }}
    QSplitter::handle {{ background: {BORDER}; }}
    QLabel {{ background: transparent; }}
"""


# ── TagCard ───────────────────────────────────────────────────────────────────

class TagCard(QFrame):
    """Compact live-value card for a single tag."""

    def __init__(self, tag: Tag, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.setFixedSize(170, 105)
        self._setup()

    def _setup(self):
        self.setStyleSheet(
            f'QFrame {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px; }}'
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 6)
        lay.setSpacing(1)

        self._name_lbl = QLabel(self.tag.description or self.tag.name)
        self._name_lbl.setStyleSheet(f'color: {MUTED}; font-size: 10px; font-weight: 600;')
        self._name_lbl.setWordWrap(True)

        self._val_lbl = QLabel('—')
        self._val_lbl.setStyleSheet(f'color: {TEXT}; font-size: 24px; font-weight: bold;')
        self._val_lbl.setAlignment(Qt.AlignLeft)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        self._unit_lbl = QLabel(self.tag.unit)
        self._unit_lbl.setStyleSheet(f'color: {MUTED}; font-size: 10px;')
        self._qual_lbl = QLabel('•')
        self._qual_lbl.setStyleSheet(f'color: {MUTED}; font-size: 16px;')
        self._qual_lbl.setAlignment(Qt.AlignRight)
        foot.addWidget(self._unit_lbl)
        foot.addStretch()
        foot.addWidget(self._qual_lbl)

        lay.addWidget(self._name_lbl)
        lay.addWidget(self._val_lbl)
        lay.addLayout(foot)

    def refresh(self, tv: TagValue):
        if tv.quality == 'bad' or tv.error:
            self._val_lbl.setText('ERR')
            self._val_lbl.setStyleSheet(f'color: {MUTED}; font-size: 24px; font-weight: bold;')
            self._qual_lbl.setStyleSheet(f'color: {ALARM}; font-size: 16px;')
            self.setStyleSheet(
                f'QFrame {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px; }}'
            )
            return

        if self.tag.dtype in ('bool', 'coil'):
            on = tv.value > 0.5
            text  = 'ON'  if on else 'OFF'
            color = LED_ON if on else MUTED
        else:
            text  = f'{tv.value:.1f}' if abs(tv.value) < 9999 else f'{int(tv.value)}'
            color = ALARM if tv.alarm else TEXT

        self._val_lbl.setText(text)
        self._val_lbl.setStyleSheet(f'color: {color}; font-size: 24px; font-weight: bold;')
        self._qual_lbl.setStyleSheet(f'color: {ACCENT}; font-size: 16px;')

        border = ALARM if tv.alarm else BORDER
        width  = '2px'  if tv.alarm else '1px'
        self.setStyleSheet(
            f'QFrame {{ background: {CARD_BG}; border: {width} solid {border}; border-radius: 8px; }}'
        )


# ── TrendChart ────────────────────────────────────────────────────────────────

class TrendChart(QWidget):
    HISTORY = 300  # seconds of data at 1 s poll

    def __init__(self, tags: List[Tag], parent=None):
        super().__init__(parent)
        self._tags = [t for t in tags if t.trend and t.dtype not in ('bool', 'coil')]
        self._bufs: Dict[str, deque] = {
            t.name: deque([float('nan')] * self.HISTORY, maxlen=self.HISTORY)
            for t in self._tags
        }
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._x = list(range(-self.HISTORY + 1, 1))
        self._setup()

    def _setup(self):
        pg.setConfigOptions(antialias=True, background=BG, foreground=TEXT)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget()
        self._plot.showGrid(x=True, y=True, alpha=0.12)
        self._plot.setLabel('bottom', 'Time (s ago)')
        self._plot.setLabel('left', 'Value')
        legend = self._plot.addLegend(offset=(-10, 10))
        legend.setLabelTextColor(TEXT)

        for i, tag in enumerate(self._tags):
            color = TREND_COLORS[i % len(TREND_COLORS)]
            curve = self._plot.plot(
                self._x,
                list(self._bufs[tag.name]),
                name=tag.description or tag.name,
                pen=pg.mkPen(color, width=2),
                connect='finite',
            )
            self._curves[tag.name] = curve

        lay.addWidget(self._plot)

    def push(self, name: str, value: float):
        if name in self._bufs:
            self._bufs[name].append(value)

    def refresh(self):
        for name, curve in self._curves.items():
            curve.setData(self._x, list(self._bufs[name]))


# ── AlarmTable ────────────────────────────────────────────────────────────────

class AlarmTable(QWidget):
    MAX_ROWS = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(['Time', 'Tag', 'Message'])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._table)

    def add_event(self, tag_name: str, message: str):
        row = 0
        self._table.insertRow(0)
        ts = time.strftime('%H:%M:%S')
        for col, val in enumerate([ts, tag_name, message]):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(ALARM))
            self._table.setItem(0, col, item)
        if self._table.rowCount() > self.MAX_ROWS:
            self._table.removeRow(self.MAX_ROWS)


# ── ScannerWidget ─────────────────────────────────────────────────────────────

class ScannerWidget(QWidget):
    """Read raw Modbus holding registers to discover the register map."""

    def __init__(self, client: PLCClient, parent=None):
        super().__init__(parent)
        self._client = client
        self._setup()

    def _setup(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        note = QLabel(
            '⚠  Use this scanner to discover the SETEX Modbus register map. '
            'Read blocks of registers, compare raw values with machine display, '
            'then add matching addresses to config.json.'
        )
        note.setWordWrap(True)
        note.setStyleSheet(f'color: {WARN}; font-size: 11px; padding: 4px;')
        lay.addWidget(note)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel('Start (MW):'))
        self._start = QSpinBox(); self._start.setRange(0, 65534); self._start.setValue(0)
        self._start.setFixedWidth(80)
        ctrl.addWidget(self._start)
        ctrl.addWidget(QLabel('Count:'))
        self._count = QSpinBox(); self._count.setRange(1, 125); self._count.setValue(50)
        self._count.setFixedWidth(60)
        ctrl.addWidget(self._count)
        ctrl.addWidget(QLabel('Slave:'))
        self._slave = QSpinBox(); self._slave.setRange(1, 247); self._slave.setValue(1)
        self._slave.setFixedWidth(50)
        ctrl.addWidget(self._slave)
        self._scan_btn = QPushButton('Read Registers')
        self._scan_btn.clicked.connect(self._do_scan)
        ctrl.addWidget(self._scan_btn)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ['Addr (%MW)', 'Raw uint16', 'Signed int16', 'Float32 (w/ next)', 'Hex']
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self._table)

    def _do_scan(self):
        if not self._client.connected:
            self._scan_btn.setText('Not connected')
            return
        start = self._start.value()
        count = self._count.value()
        slave = self._slave.value()
        regs = self._client._read_holding(start, count, slave)
        if regs is None:
            self._scan_btn.setText('Read failed')
            return
        self._scan_btn.setText('Read Registers')
        self._table.setRowCount(len(regs))
        for i, raw in enumerate(regs):
            addr    = start + i
            signed  = struct.unpack('>h', struct.pack('>H', raw))[0]
            fval    = '—'
            if i + 1 < len(regs):
                f = struct.unpack('>f', struct.pack('>HH', regs[i], regs[i + 1]))[0]
                fval = f'{f:.4f}' if abs(f) < 1e6 else '—'
            hexval = f'0x{raw:04X}'
            for col, val in enumerate([str(addr), str(raw), str(signed), fval, hexval]):
                item = QTableWidgetItem(val)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if raw != 0:
                    item.setForeground(QColor(TEXT))
                else:
                    item.setForeground(QColor(MUTED))
                self._table.setItem(i, col, item)


# ── ConnectionBar ─────────────────────────────────────────────────────────────

class ConnectionBar(QWidget):
    def __init__(self, client: PLCClient, parent=None):
        super().__init__(parent)
        self._client = client
        self.setFixedHeight(48)
        self.setStyleSheet(f'background: {PANEL}; border-bottom: 1px solid {BORDER};')
        self._setup()

    def _setup(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)

        # Logo / title
        title = QLabel('SETEX 797TCE Monitor')
        title.setStyleSheet(f'color: {TEXT}; font-size: 14px; font-weight: bold;')
        lay.addWidget(title)

        sub = QLabel('SECOM-AK04')
        sub.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        lay.addWidget(sub)
        lay.addStretch()

        lay.addWidget(QLabel('IP:'))
        self._ip_edit = QLineEdit(self._client.ip)
        self._ip_edit.setFixedWidth(130)
        lay.addWidget(self._ip_edit)

        lay.addWidget(QLabel('Port:'))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(self._client.port)
        self._port_spin.setFixedWidth(70)
        lay.addWidget(self._port_spin)

        lay.addWidget(QLabel('Poll (s):'))
        self._poll_spin = QDoubleSpinBox()
        self._poll_spin.setRange(0.2, 60.0)
        self._poll_spin.setSingleStep(0.5)
        self._poll_spin.setValue(self._client.poll_interval)
        self._poll_spin.setFixedWidth(65)
        lay.addWidget(self._poll_spin)

        self._conn_btn = QPushButton('Connect')
        self._conn_btn.setFixedWidth(90)
        self._conn_btn.clicked.connect(self._toggle)
        lay.addWidget(self._conn_btn)

        self._led = QLabel('●')
        self._led.setStyleSheet(f'color: {LED_OFF}; font-size: 18px;')
        lay.addWidget(self._led)

        self._status_lbl = QLabel('Disconnected')
        self._status_lbl.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        self._status_lbl.setFixedWidth(110)
        lay.addWidget(self._status_lbl)

    def _toggle(self):
        if self._client.connected:
            self._client.disconnect()
            self._conn_btn.setText('Connect')
            self._led.setStyleSheet(f'color: {LED_OFF}; font-size: 18px;')
            self._status_lbl.setText('Disconnected')
        else:
            ip   = self._ip_edit.text().strip()
            port = self._port_spin.value()
            self._client.poll_interval = self._poll_spin.value()
            self._conn_btn.setText('Connecting…')
            ok = self._client.connect(ip, port)
            if ok:
                self._conn_btn.setText('Disconnect')
                self._led.setStyleSheet(f'color: {LED_ON}; font-size: 18px;')
                self._status_lbl.setText('Connected')
                self._client.start_polling()
            else:
                self._conn_btn.setText('Connect')
                self._led.setStyleSheet(f'color: {ALARM}; font-size: 18px;')
                self._status_lbl.setText('Failed')

    def sync_status(self, connected: bool):
        if connected:
            self._conn_btn.setText('Disconnect')
            self._led.setStyleSheet(f'color: {LED_ON}; font-size: 18px;')
            self._status_lbl.setText('Connected')
        else:
            self._conn_btn.setText('Connect')
            self._led.setStyleSheet(f'color: {LED_OFF}; font-size: 18px;')
            self._status_lbl.setText('Disconnected')


# ── MainWindow ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    REFRESH_MS = 500  # UI refresh interval

    def __init__(self, client: PLCClient, config: dict):
        super().__init__()
        self._client = client
        self._config = config
        self._alarm_states: Dict[str, bool] = {}
        self._cards: Dict[str, TagCard] = {}

        self.setWindowTitle('SETEX 797TCE Monitor — SECOM-AK04')
        self.resize(1280, 780)
        self.setStyleSheet(_BASE_STYLE)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.REFRESH_MS)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vlay = QVBoxLayout(root)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Connection bar
        self._conn_bar = ConnectionBar(self._client, self)
        vlay.addWidget(self._conn_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        vlay.addWidget(splitter, stretch=1)

        # Left: tag cards
        splitter.addWidget(self._build_card_panel())

        # Right: tabs
        self._tabs = QTabWidget()
        self._trend = TrendChart(self._client.tags, self)
        self._alarms = AlarmTable(self)
        self._scanner = ScannerWidget(self._client, self)

        self._tabs.addTab(self._trend,   '📈  Trend')
        self._tabs.addTab(self._alarms,  '🔔  Alarms')
        self._tabs.addTab(self._scanner, '🔍  Scanner')
        splitter.addWidget(self._tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet(f'background:{PANEL}; color:{MUTED}; font-size:11px;')
        self._sb_time = QLabel('Last update: —')
        self._sb_qual = QLabel('Tags: 0 / 0')
        sb.addWidget(self._sb_time)
        sb.addPermanentWidget(self._sb_qual)
        self.setStatusBar(sb)

    def _build_card_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(370)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f'QScrollArea {{ border: none; background: {BG}; }}')

        inner = QWidget()
        inner.setStyleSheet(f'background: {BG};')
        grid = QGridLayout(inner)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)

        col = 0
        row = 0
        for tag in self._client.tags:
            card = TagCard(tag, inner)
            self._cards[tag.name] = card
            grid.addWidget(card, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        scroll.setWidget(inner)
        return scroll

    # ── Refresh loop ──────────────────────────────────────────────────────────

    def _refresh(self):
        self._conn_bar.sync_status(self._client.connected)
        vals = self._client.get_values()
        if not vals:
            return

        good = sum(1 for v in vals.values() if v.quality == 'good')
        self._sb_qual.setText(f'Tags: {good} / {len(vals)}  good')
        self._sb_time.setText(f'Last update: {time.strftime("%H:%M:%S")}')

        for name, tv in vals.items():
            # Update card
            if name in self._cards:
                self._cards[name].refresh(tv)

            # Push to trend
            if tv.quality == 'good':
                self._trend.push(name, tv.value)

            # Alarm edge detect
            was_alarm = self._alarm_states.get(name, False)
            if tv.alarm and not was_alarm:
                tag = self._client.get_tag(name)
                desc = tag.description if tag else name
                self._alarms.add_event(name, f'{desc} = {tv.value:.2f} — threshold exceeded')
            self._alarm_states[name] = tv.alarm

        self._trend.refresh()
