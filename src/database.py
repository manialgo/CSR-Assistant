"""
database.py — SQLite setup and deterministic account/ticket lookups.
No LLM calls here. Pure data access layer.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import DB_PATH
from src.models import AccountInfo, PlanInfo


# ── Bootstrap DB ─────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables and seed sample data if DB doesn't exist."""
    if DB_PATH.exists():
        return  # Already seeded

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()

    _create_tables(conn)
    _seed_data(conn)

    conn.commit()
    conn.close()
    print(f"[DB] Initialised and seeded at {DB_PATH}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS plans (
            plan_id       TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            type          TEXT NOT NULL,
            speed_mbps    INTEGER,
            data_gb       INTEGER,
            monthly_cost  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL,
            phone         TEXT NOT NULL,
            address       TEXT
        );

        CREATE TABLE IF NOT EXISTS accounts (
            account_id      TEXT PRIMARY KEY,
            customer_id     TEXT NOT NULL,
            plan_id         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            billing_due_day INTEGER NOT NULL DEFAULT 1,
            balance_due     REAL NOT NULL DEFAULT 0.0,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
        );

        CREATE TABLE IF NOT EXISTS billing_history (
            billing_id    TEXT PRIMARY KEY,
            account_id    TEXT NOT NULL,
            amount        REAL NOT NULL,
            due_date      TEXT NOT NULL,
            paid_date     TEXT,
            status        TEXT NOT NULL DEFAULT 'pending',
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id     TEXT PRIMARY KEY,
            account_id    TEXT NOT NULL,
            issue_type    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'open',
            created_at    TEXT NOT NULL,
            description   TEXT NOT NULL,
            resolution    TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        );
    """)


def _seed_data(conn: sqlite3.Connection) -> None:
    today = datetime.today()
    fmt = "%Y-%m-%d"

    # ── Plans ─────────────────────────────────────────────────────────────────
    plans = [
        ("PLN001", "Fiber 100",    "broadband", 100,  None, 29.99),
        ("PLN002", "Fiber 500",    "broadband", 500,  None, 49.99),
        ("PLN003", "Fiber 1000",   "broadband", 1000, None, 69.99),
        ("PLN004", "Mobile Basic", "mobile",    None, 5,    9.99),
        ("PLN005", "Mobile Plus",  "mobile",    None, 20,   19.99),
        ("PLN006", "Mobile Max",   "mobile",    None, 100,  34.99),
        ("PLN007", "Bundle 500",   "bundle",    500,  20,   59.99),
        ("PLN008", "Bundle Max",   "bundle",    1000, 100,  89.99),
    ]
    conn.executemany(
        "INSERT INTO plans VALUES (?,?,?,?,?,?)", plans
    )

    # ── Customers ─────────────────────────────────────────────────────────────
    customers = [
        ("CUST001", "Arjun Mehta",     "arjun.mehta@email.com",     "+91-9876543210", "12 MG Road, Bengaluru"),
        ("CUST002", "Priya Sharma",    "priya.sharma@email.com",    "+91-9876543211", "45 Anna Nagar, Chennai"),
        ("CUST003", "Rahul Verma",     "rahul.verma@email.com",     "+91-9876543212", "7 Connaught Place, Delhi"),
        ("CUST004", "Sneha Iyer",      "sneha.iyer@email.com",      "+91-9876543213", "22 FC Road, Pune"),
        ("CUST005", "Vikram Nair",     "vikram.nair@email.com",     "+91-9876543214", "88 Park Street, Kolkata"),
        ("CUST006", "Meera Pillai",    "meera.pillai@email.com",    "+91-9876543215", "3 Marine Drive, Mumbai"),
        ("CUST007", "Karthik Rajan",   "karthik.rajan@email.com",   "+91-9876543216", "15 Jubilee Hills, Hyderabad"),
        ("CUST008", "Divya Krishnan",  "divya.krishnan@email.com",  "+91-9876543217", "9 Civil Lines, Jaipur"),
        ("CUST009", "Aditya Gupta",    "aditya.gupta@email.com",    "+91-9876543218", "34 Salt Lake, Kolkata"),
        ("CUST010", "Ananya Reddy",    "ananya.reddy@email.com",    "+91-9876543219", "67 Banjara Hills, Hyderabad"),
    ]
    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?)", customers
    )

    # ── Accounts ─────────────────────────────────────────────────────────────
    accounts = [
        ("ACC001", "CUST001", "PLN002", "active",    15, 0.0),    # Good standing
        ("ACC002", "CUST002", "PLN005", "active",    1,  19.99),   # Bill due
        ("ACC003", "CUST003", "PLN007", "active",    10, 0.0),
        ("ACC004", "CUST004", "PLN001", "suspended", 5,  89.97),   # 3 months overdue
        ("ACC005", "CUST005", "PLN006", "active",    20, 34.99),
        ("ACC006", "CUST006", "PLN003", "active",    1,  0.0),
        ("ACC007", "CUST007", "PLN008", "active",    25, 0.0),
        ("ACC008", "CUST008", "PLN004", "active",    10, 9.99),
        ("ACC009", "CUST009", "PLN002", "active",    15, 0.0),
        ("ACC010", "CUST010", "PLN005", "cancelled", 1,  0.0),
    ]
    conn.executemany(
        "INSERT INTO accounts VALUES (?,?,?,?,?,?)", accounts
    )

    # ── Billing history ───────────────────────────────────────────────────────
    billing = [
        ("BIL001", "ACC001", 49.99, (today - timedelta(days=30)).strftime(fmt), (today - timedelta(days=28)).strftime(fmt), "paid"),
        ("BIL002", "ACC001", 49.99, today.strftime(fmt), None, "pending"),
        ("BIL003", "ACC002", 19.99, today.strftime(fmt), None, "pending"),
        ("BIL004", "ACC004", 29.99, (today - timedelta(days=90)).strftime(fmt), None, "overdue"),
        ("BIL005", "ACC004", 29.99, (today - timedelta(days=60)).strftime(fmt), None, "overdue"),
        ("BIL006", "ACC004", 29.99, (today - timedelta(days=30)).strftime(fmt), None, "overdue"),
        ("BIL007", "ACC005", 34.99, today.strftime(fmt), None, "pending"),
        ("BIL008", "ACC003", 59.99, (today - timedelta(days=30)).strftime(fmt), (today - timedelta(days=25)).strftime(fmt), "paid"),
        ("BIL009", "ACC008", 9.99,  today.strftime(fmt), None, "pending"),
        ("BIL010", "ACC009", 49.99, (today - timedelta(days=30)).strftime(fmt), (today - timedelta(days=27)).strftime(fmt), "paid"),
    ]
    conn.executemany(
        "INSERT INTO billing_history VALUES (?,?,?,?,?,?)", billing
    )

    # ── Support tickets ───────────────────────────────────────────────────────
    tickets = [
        ("TKT001", "ACC001", "connection_issue",  "resolved", (today - timedelta(days=15)).strftime(fmt),
         "Intermittent connection drops in the evening between 7-9 PM.",
         "Engineer visit confirmed line noise. Cable replaced. Issue resolved."),

        ("TKT002", "ACC002", "billing_dispute",   "open",     (today - timedelta(days=3)).strftime(fmt),
         "Customer disputes ₹500 charge on current bill. Claims it's a duplicate.",
         None),

        ("TKT003", "ACC003", "plan_change",       "resolved", (today - timedelta(days=10)).strftime(fmt),
         "Requested upgrade from Fiber 500 to Bundle 500.",
         "Plan upgraded. Prorated credit applied for remaining days."),

        ("TKT004", "ACC004", "payment_issue",     "open",     (today - timedelta(days=90)).strftime(fmt),
         "Customer unable to pay. Account suspended after 3 missed payments.",
         None),

        ("TKT005", "ACC005", "roaming_charges",   "open",     (today - timedelta(days=2)).strftime(fmt),
         "Unexpected roaming charges of ₹1200 while traveling to UAE.",
         None),

        ("TKT006", "ACC007", "slow_speed",        "in_progress", (today - timedelta(days=5)).strftime(fmt),
         "Download speeds consistently below 200 Mbps on 1000 Mbps plan.",
         "Remote diagnostics run. Engineer visit scheduled."),

        ("TKT007", "ACC008", "sim_issue",         "resolved", (today - timedelta(days=7)).strftime(fmt),
         "SIM card not recognised after phone update.",
         "Network reset resolved the issue remotely."),

        ("TKT008", "ACC009", "billing_dispute",   "open",     today.strftime(fmt),
         "Bill amount increased by ₹200 compared to last month with no plan change.",
         None),

        ("TKT009", "ACC006", "connection_issue",  "open",     (today - timedelta(days=1)).strftime(fmt),
         "Complete internet outage. All devices affected. Router lights normal.",
         None),

        ("TKT010", "ACC010", "cancellation",      "resolved", (today - timedelta(days=20)).strftime(fmt),
         "Customer requested account cancellation.",
         "Account cancelled. Final bill settled. Port-out completed."),
    ]
    conn.executemany(
        "INSERT INTO tickets VALUES (?,?,?,?,?,?,?)", tickets
    )


# ── Public query functions ────────────────────────────────────────────────────

def get_account(account_id: str) -> Optional[AccountInfo]:
    """
    Fetch full account context for a given account_id.
    Returns None if account not found.
    """
    conn = _connect()
    try:
        row = conn.execute("""
            SELECT
                a.account_id, a.status, a.billing_due_day, a.balance_due,
                c.name, c.email, c.phone,
                p.plan_id, p.name as plan_name, p.type,
                p.speed_mbps, p.data_gb, p.monthly_cost
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
            JOIN plans p     ON a.plan_id = p.plan_id
            WHERE a.account_id = ?
        """, (account_id,)).fetchone()

        if not row:
            return None

        # Compute next billing date
        today = datetime.today()
        try:
            next_bill = today.replace(day=row["billing_due_day"])
            if next_bill < today:
                # Move to next month
                if today.month == 12:
                    next_bill = next_bill.replace(year=today.year + 1, month=1)
                else:
                    next_bill = next_bill.replace(month=today.month + 1)
        except ValueError:
            next_bill = today  # Fallback for invalid day (e.g. Feb 30)

        # Recent tickets (last 5)
        ticket_rows = conn.execute("""
            SELECT ticket_id, issue_type, status, created_at, description, resolution
            FROM tickets
            WHERE account_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        """, (account_id,)).fetchall()

        tickets = [dict(t) for t in ticket_rows]

        plan = PlanInfo(
            plan_id=row["plan_id"],
            name=row["plan_name"],
            type=row["type"],
            speed_mbps=row["speed_mbps"],
            data_gb=row["data_gb"],
            monthly_cost=row["monthly_cost"],
        )

        return AccountInfo(
            account_id=row["account_id"],
            customer_name=row["name"],
            email=row["email"],
            phone=row["phone"],
            plan=plan,
            account_status=row["status"],
            billing_due_date=next_bill.strftime("%Y-%m-%d"),
            balance_due=row["balance_due"],
            recent_tickets=tickets,
        )

    finally:
        conn.close()


def get_recent_billing(account_id: str, limit: int = 3) -> list:
    """Return last N billing records for an account."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT billing_id, amount, due_date, paid_date, status
            FROM billing_history
            WHERE account_id = ?
            ORDER BY due_date DESC
            LIMIT ?
        """, (account_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def account_exists(account_id: str) -> bool:
    """Quick existence check without fetching full account."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()
