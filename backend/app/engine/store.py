"""
Data + config access layer for the rules engine.

Loads config/scoring.yaml + config/next_actions.yaml and opens the SQLite
database read-only. All row access goes through here so the scoring code has a
single, typed surface over the SAP/ETQ tables.
"""

import os
import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

# Repo root = three parents up from backend/app/engine/store.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = Path(os.getenv("VENDORLENS_CONFIG_DIR", _REPO_ROOT / "config"))
_DB_PATH = Path(os.getenv("VENDORLENS_DB", _REPO_ROOT / "data" / "vendorlens.db"))


class Store:
    def __init__(self, db_path=_DB_PATH, config_dir=_CONFIG_DIR):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with open(Path(config_dir) / "scoring.yaml") as f:
            self.scoring = yaml.safe_load(f)
        with open(Path(config_dir) / "next_actions.yaml") as f:
            self.next_actions = yaml.safe_load(f)["matrix"]
        row = self.conn.execute("SELECT value FROM meta WHERE key='as_of_date'").fetchone()
        self.as_of = date.fromisoformat(row["value"])

    # -- raw fetchers -------------------------------------------------------
    def _q(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def vendors(self):
        return self._q("SELECT * FROM vendors ORDER BY vendor_code")

    def vendor(self, vc):
        rows = self._q("SELECT * FROM vendors WHERE vendor_code=?", (vc,))
        return rows[0] if rows else None

    def deliveries(self, vc):
        """PO requested date joined to GRN posting date, for delivery banding."""
        return self._q(
            """SELECT g.grn_number, p.po_number, p.requested_delivery_date,
                      g.posting_date, p.qty
               FROM goods_receipts g JOIN purchase_orders p ON g.po_number = p.po_number
               WHERE p.vendor_code = ? ORDER BY g.posting_date""", (vc,))

    def inspection_lots(self, vc):
        return self._q(
            """SELECT l.* FROM inspection_lots l
               JOIN goods_receipts g ON l.grn_number = g.grn_number
               JOIN purchase_orders p ON g.po_number = p.po_number
               WHERE p.vendor_code = ? ORDER BY l.ud_date""", (vc,))

    def work_orders(self, vc):
        return self._q("SELECT * FROM work_orders WHERE vendor_code=? ORDER BY planned_completion", (vc,))

    def service_entries(self, vc):
        return self._q("SELECT * FROM service_entries WHERE vendor_code=? ORDER BY service_date", (vc,))

    def ncr_capa(self, vc):
        return self._q("SELECT * FROM ncr_capa WHERE vendor_code=? ORDER BY raised_date", (vc,))

    def compliance_docs(self, vc):
        return self._q("SELECT * FROM compliance_docs WHERE vendor_code=? ORDER BY expiry_date", (vc,))

    def hse_incidents(self, vc):
        return self._q("SELECT * FROM hse_incidents WHERE vendor_code=? ORDER BY incident_date", (vc,))


@lru_cache(maxsize=1)
def get_store():
    return Store()
