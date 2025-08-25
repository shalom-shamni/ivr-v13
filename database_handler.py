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
    class Config:  # fallback
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

        # details
        cur.execute('''
            CREATE TABLE IF NOT EXISTS customer_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER UNIQUE,
                num_children INTEGER,
                children_birth_years TEXT,
                spouse1_workplaces INTEGER,
                spouse2_workplaces INTEGER,
                additional_info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
            )
        ''')

        # calls
        cur.execute('''
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL,
                phone_number TEXT,
                customer_id INTEGER,
                pbx_num TEXT,
                pbx_did TEXT,
                call_type TEXT,
                call_status TEXT,
                extension_id TEXT,
                extension_path TEXT,
                call_data TEXT,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME,
                duration INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')

        # receipts
        cur.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                call_id TEXT,
                receipt_data TEXT NOT NULL,
                icount_doc_id TEXT,
                icount_doc_num TEXT,
                icount_response TEXT,
                amount DECIMAL(10,2),
                description TEXT,
                status TEXT DEFAULT 'pending',
                client_contact_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id),
                FOREIGN KEY (call_id) REFERENCES calls (call_id)
            )
        ''')

        # messages
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                call_id TEXT,
                message_file TEXT,
                message_text TEXT,
                message_duration INTEGER,
                status TEXT DEFAULT 'new',
                priority TEXT DEFAULT 'normal',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                FOREIGN KEY (customer_id) REFERENCES customers (id),
                FOREIGN KEY (call_id) REFERENCES calls (call_id)
            )
        ''')

        # annual reports
        cur.execute('''
            CREATE TABLE IF NOT EXISTS annual_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                report_year INTEGER,
                report_data TEXT,
                report_file TEXT,
                status TEXT DEFAULT 'requested',
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                generated_at DATETIME,
                sent_at DATETIME,
                UNIQUE(customer_id, report_year),
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')

        # contacts (address book for receipt targets)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                name TEXT,
                phone TEXT,
                email TEXT,
                tz_id TEXT,
                business_name TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(customer_id, phone),
                FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
            )
        ''')

        # indices
        cur.execute('CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone_number)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_calls_call_id ON calls (call_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_calls_phone ON calls (phone_number)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_receipts_customer ON receipts (customer_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_messages_customer ON messages (customer_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_reports_customer ON annual_reports (customer_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts (customer_id)')

        # gentle migrations for existing DBs that predate new columns
        try:
            self._ensure_column(conn, 'customers', 'business_name', 'TEXT')
            self._ensure_column(conn, 'customers', 'tz_id', 'TEXT')
            self._ensure_column(conn, 'customers', 'owner_age', 'INTEGER')
            self._ensure_column(conn, 'customers', 'gender', 'TEXT')
            self._ensure_column(conn, 'receipts', 'client_contact_id', 'INTEGER')
            self._ensure_column(conn, 'calls', 'updated_at', 'DATETIME DEFAULT CURRENT_TIMESTAMP')
        except Exception as e:
            logger.warning(f"migrations: {e}")

        conn.commit()
        conn.close()
        logger.info("מאגר הנתונים אותחל/שודרג בהצלחה")

    # ---------- customers ----------
    def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM customers WHERE phone_number = ?', (phone_number,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_customer_by_id(self, customer_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_customer(self, phone_number: str, name: str = None, email: str = None) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        start_date = datetime.now().date()
        months = int(getattr(Config, 'DEFAULT_SUBSCRIPTION_MONTHS', 12))
        end_date = start_date + timedelta(days=30*months)
        cur.execute('''
            INSERT INTO customers (phone_number, name, email, subscription_start_date, subscription_end_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (phone_number, name, email, start_date, end_date))
        customer_id = cur.lastrowid
        # create empty details row
        cur.execute('INSERT INTO customer_details (customer_id) VALUES (?)', (customer_id,))
        conn.commit()
        conn.close()
        logger.info(f"נוצר לקוח חדש: {phone_number} (ID: {customer_id})")
        return customer_id

    def update_customer(self, customer_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed = {
            'name','email','subscription_start_date','subscription_end_date','is_active',
            'business_name','tz_id','owner_age','gender'
        }
        set_clauses, values = [], []
        for k, v in kwargs.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                values.append(v)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = ?")
        values.append(datetime.now())
        values.append(customer_id)
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE customers SET {', '.join(set_clauses)} WHERE id = ?", values)
        ok = cur.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    def is_subscription_active(self, customer: Dict) -> bool:
        if not customer or not customer.get('subscription_end_date'):
            return False
        try:
            end_date = datetime.strptime(str(customer['subscription_end_date']), '%Y-%m-%d').date()
        except Exception:
            try:
                end_date = datetime.fromisoformat(str(customer['subscription_end_date'])).date()
            except Exception:
                return False
        return end_date >= datetime.now().date()

    # profile helpers
    def is_profile_complete(self, customer: Dict) -> bool:
        if not customer:
            return False
        basic_ok = all([
            customer.get('tz_id'),
            (customer.get('owner_age') is not None),
            customer.get('gender')
        ])
        details = self.get_customer_details(customer['id'])
        kids_ok = details is not None and (details.get('num_children') is not None)
        return basic_ok and kids_ok

    def update_customer_profile(self, customer_id: int, **kwargs) -> bool:
        allowed = {'name','business_name','tz_id','owner_age','gender','email'}
        payload = {k:v for k,v in kwargs.items() if k in allowed}
        return self.update_customer(customer_id, **payload)

    # ---------- details ----------
    def get_customer_details(self, customer_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM customer_details WHERE customer_id = ?', (customer_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_customer_details(self, customer_id: int, **kwargs) -> bool:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM customer_details WHERE customer_id = ?', (customer_id,))
        exists = cur.fetchone()
        allowed = {'num_children','children_birth_years','spouse1_workplaces','spouse2_workplaces','additional_info'}
        if exists:
            set_clauses, values = [], []
            for k, v in kwargs.items():
                if k in allowed:
                    set_clauses.append(f"{k} = ?")
                    values.append(v)
            if set_clauses:
                set_clauses.append("updated_at = ?")
                values.append(datetime.now())
                values.append(customer_id)
                cur.execute(f"UPDATE customer_details SET {', '.join(set_clauses)} WHERE customer_id = ?", values)
                ok = cur.rowcount > 0
            else:
                ok = False
        else:
            columns = ['customer_id']
            values = [customer_id]
            for k, v in kwargs.items():
                if k in allowed:
                    columns.append(k)
                    values.append(v)
            placeholders = ', '.join(['?'] * len(values))
            cur.execute(f"INSERT INTO customer_details ({', '.join(columns)}) VALUES ({placeholders})", values)
            ok = cur.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    # ---------- calls ----------
    def log_call(self, call_params: Dict) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        customer_id = None
        if call_params.get('PBXphone'):
            cust = self.get_customer_by_phone(call_params['PBXphone'])
            if cust:
                customer_id = cust['id']
        cur.execute('''
            INSERT OR REPLACE INTO calls 
            (call_id, phone_number, customer_id, pbx_num, pbx_did, call_type, call_status, extension_id, extension_path, call_data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            call_params.get('PBXcallId'),
            call_params.get('PBXphone'),
            customer_id,
            call_params.get('PBXnum'),
            call_params.get('PBXdid'),
            call_params.get('PBXcallType'),
            call_params.get('PBXcallStatus'),
            call_params.get('PBXextensionId'),
            call_params.get('PBXextensionPath'),
            json.dumps(call_params, ensure_ascii=False)
        ))
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def update_call_data(self, call_id: str, new_data: Dict) -> bool:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT call_data FROM calls WHERE call_id = ?', (call_id,))
        row = cur.fetchone()
        if row:
            existing = json.loads(row['call_data'] or '{}')
            existing.update(new_data)
            cur.execute(
                'UPDATE calls SET call_data = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?',
                (json.dumps(existing, ensure_ascii=False), call_id)
            )
            ok = cur.rowcount > 0
        else:
            ok = False
        conn.commit()
        conn.close()
        return ok

    # ---------- receipts ----------
    def create_receipt(self, customer_id: int, call_id: str, receipt_data: Dict) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO receipts (customer_id, call_id, receipt_data, amount, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            customer_id,
            call_id,
            json.dumps(receipt_data, ensure_ascii=False),
            receipt_data.get('amount', 0),
            receipt_data.get('description', '')
        ))
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid

    def update_receipt(self, receipt_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed = {
            'icount_doc_id', 'icount_doc_num', 'icount_response',
            'amount', 'description', 'status', 'client_contact_id'
        }
        set_clauses, values = [], []
        for k, v in kwargs.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                values.append(v)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = ?")
        values.append(datetime.now())
        values.append(receipt_id)
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE receipts SET {', '.join(set_clauses)} WHERE id = ?", values)
        ok = cur.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    # ---------- messages ----------
    def save_message(self, customer_id: int, call_id: str,
                     message_file: str = None, message_text: str = None,
                     duration: int = None) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO messages (customer_id, call_id, message_file, message_text, message_duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer_id, call_id, message_file, message_text, duration))
        mid = cur.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"נשמרה הודעה חדשה: ID {mid}")
        return mid

    # ---------- annual reports ----------
    def request_annual_report(self, customer_id: int, report_year: int = None) -> int:
        if not report_year:
            report_year = datetime.now().year - 1
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO annual_reports (customer_id, report_year, status, requested_at)
            VALUES (?, ?, 'requested', ?)
        ''', (customer_id, report_year, datetime.now()))
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"נתבקש דיווח שנתי: לקוח {customer_id}, שנה {report_year}")
        return rid

    # ---------- contacts (address book) ----------
    def upsert_contact(self, customer_id: int, phone: str, name: str = None, tz_id: str = None,
                       business_name: str = None, email: str = None, notes: str = None) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM contacts WHERE customer_id=? AND phone=?', (customer_id, phone))
        row = cur.fetchone()
        if row:
            cur.execute('''
                UPDATE contacts
                   SET name = COALESCE(?, name),
                       tz_id = COALESCE(?, tz_id),
                       business_name = COALESCE(?, business_name),
                       email = COALESCE(?, email),
                       notes = COALESCE(?, notes),
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
            ''', (name, tz_id, business_name, email, notes, row['id']))
            cid = row['id']
        else:
            cur.execute('''
                INSERT INTO contacts (customer_id, phone, name, tz_id, business_name, email, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (customer_id, phone, name, tz_id, business_name, email, notes))
            cid = cur.lastrowid
        conn.commit()
        conn.close()
        return cid

    def get_contact_by_phone(self, customer_id: int, phone: str) -> Optional[Dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('SELECT * FROM contacts WHERE customer_id=? AND phone=?', (customer_id, phone))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_contacts(self, customer_id: int, limit: int = 20) -> List[Dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM contacts WHERE customer_id=? ORDER BY updated_at DESC LIMIT ?',
            (customer_id, limit)
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---------- CSV export helpers ----------
    def export_table_to_csv(self, table: str, out_path: str) -> int:
        """ייצוא טבלה גולמית לקובץ CSV. מחזיר מספר שורות שנכתבו."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM {table}')
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(col_names)
            for r in rows:
                writer.writerow([r[c] for c in col_names])
        conn.close()
        return len(rows)

    def export_receipts_with_phone_csv(self, out_path: str) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT r.*, c.phone_number AS issuer_phone
            FROM receipts r
            JOIN customers c ON c.id = r.customer_id
            ORDER BY r.created_at DESC
        ''')
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(col_names)
            for r in rows:
                writer.writerow([r[c] for c in col_names])
        conn.close()
        return len(rows)

    def export_contacts_csv(self, customer_id: int, out_path: str) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM contacts WHERE customer_id=? ORDER BY updated_at DESC', (customer_id,))
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(col_names)
            for r in rows:
                writer.writerow([r[c] for c in col_names])
        conn.close()
        return len(rows)

    # ---------- close ----------
    def close(self):
        # nothing to close explicitly – connections are short-lived
        pass
