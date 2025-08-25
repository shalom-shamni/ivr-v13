#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sqlite3
import json
import logging
import csv
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


try:
from config import Config
except Exception:
class Config: # fallback
DATABASE_PATH = 'pbx_system.db'
DEFAULT_SUBSCRIPTION_MONTHS = 12


logger = logging.getLogger(__name__)




class DatabaseHandler:
"""מחלקה לטיפול במאגר הנתונים, כולל מיגרציות עדינות, אנשי קשר וייצוא CSV"""


def __init__(self, db_path: str = None):
self.db_path = db_path or Config.DATABASE_PATH
self.init_database()


# ---------- connection ----------
def get_connection(self):
conn = sqlite3.connect(self.db_path)
conn.row_factory = sqlite3.Row
return conn


# ---------- migrations helpers ----------
def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
cur = conn.cursor()
cur.execute(f"PRAGMA table_info({table})")
cols = [r[1] for r in cur.fetchall()]
return column in cols


def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, coldef: str):
if not self._column_exists(conn, table, column):
conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


# ---------- init & schema ----------
def init_database(self):
conn = self.get_connection()
cur = conn.cursor()


# customers
cur.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
phone_number TEXT UNIQUE NOT NULL,
name TEXT,
email TEXT,
business_name TEXT,
tz_id TEXT,
owner_age INTEGER,
gender TEXT,
subscription_start_date DATE,
subscription_end_date DATE,
is_active BOOLEAN DEFAULT 1,
created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
pass
