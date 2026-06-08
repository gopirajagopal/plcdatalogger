"""
SETEX 797TCE PLC Monitor
Entry point — loads config, builds PLCClient with tags, launches Qt window.
"""

import json
import logging
import sys
from pathlib import Path

from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QApplication

from plc_client import PLCClient, Tag
from ui_main import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(name)s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('main')


def load_config(path: str = 'config.json') -> dict:
    p = Path(path)
    if not p.exists():
        log.error('config.json not found next to executable — using defaults')
        return {}
    with p.open(encoding='utf-8') as f:
        return json.load(f)


def build_tags(tag_defs: list) -> list[Tag]:
    tags = []
    for d in tag_defs:
        try:
            tags.append(Tag(
                name        = d['name'],
                address     = int(d['address']),
                dtype       = d.get('dtype', 'uint16'),
                bit         = int(d.get('bit', 0)),
                unit        = d.get('unit', ''),
                description = d.get('description', d['name']),
                scale       = float(d.get('scale', 1.0)),
                offset      = float(d.get('offset', 0.0)),
                slave_id    = int(d.get('slave_id', 1)),
                hi_alarm    = d.get('hi_alarm'),
                lo_alarm    = d.get('lo_alarm'),
                trend       = bool(d.get('trend', True)),
            ))
        except Exception as e:
            log.warning('Skipping tag %s: %s', d.get('name', '?'), e)
    return tags


def dark_palette(app: QApplication) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window,          QColor('#12121e'))
    p.setColor(QPalette.WindowText,      QColor('#dfe6e9'))
    p.setColor(QPalette.Base,            QColor('#1c1c2e'))
    p.setColor(QPalette.AlternateBase,   QColor('#16162a'))
    p.setColor(QPalette.Text,            QColor('#dfe6e9'))
    p.setColor(QPalette.Button,          QColor('#16162a'))
    p.setColor(QPalette.ButtonText,      QColor('#dfe6e9'))
    p.setColor(QPalette.Highlight,       QColor('#10a37f'))
    p.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    p.setColor(QPalette.Link,            QColor('#74b9ff'))
    p.setColor(QPalette.ToolTipBase,     QColor('#1c1c2e'))
    p.setColor(QPalette.ToolTipText,     QColor('#dfe6e9'))
    return p


def main():
    cfg = load_config()

    client = PLCClient()
    conn   = cfg.get('connection', {})
    client.ip            = conn.get('ip',            '192.168.1.220')
    client.port          = int(conn.get('port',       502))
    client.timeout       = float(conn.get('timeout',  3.0))
    client.poll_interval = float(conn.get('poll_interval', 1.0))

    tags = build_tags(cfg.get('tags', []))
    if not tags:
        log.warning('No tags defined in config.json — add tags to see live data')
    client.set_tags(tags)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setPalette(dark_palette(app))

    win = MainWindow(client, cfg)
    win.show()

    # Auto-connect on start if configured
    if conn.get('auto_connect', False):
        ok = client.connect()
        if ok:
            client.start_polling()
            log.info('Auto-connected to %s', client.ip)

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
