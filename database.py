from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db_path(db_path: str | Path = "ebay_data.db") -> Path:
    return Path(db_path)


def connect(db_path: str | Path = "ebay_data.db") -> sqlite3.Connection:
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Initializes schema (idempotent).
    """
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ebay_order_id TEXT NOT NULL UNIQUE,
            buyer_username TEXT,
            buyer_email TEXT,
            item_id TEXT,
            item_title TEXT,
            quantity INTEGER,
            total_value REAL,
            currency TEXT,
            sold_at TEXT,
            shipping_address_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            last_seen_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_sold_at ON orders(sold_at);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ebay_order_id TEXT NOT NULL UNIQUE,
            weight_kg REAL,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            dhl_service TEXT,
            dhl_price_gbp REAL,
            collection_type TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(ebay_order_id) REFERENCES orders(ebay_order_id) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ebay_message_id TEXT NOT NULL UNIQUE,
            ebay_order_id TEXT,
            from_user TEXT,
            subject TEXT,
            body TEXT,
            received_at TEXT,
            status TEXT NOT NULL DEFAULT 'unread',
            draft_response TEXT,
            sent_at TEXT,
            last_seen_at TEXT NOT NULL,
            FOREIGN KEY(ebay_order_id) REFERENCES orders(ebay_order_id) ON DELETE SET NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL, -- 'box' | 'material'
            name TEXT NOT NULL,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            qty INTEGER NOT NULL DEFAULT 0,
            reorder_threshold INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            UNIQUE(kind, name)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_kind ON inventory_items(kind);")

    conn.commit()


@dataclass(frozen=True)
class OrderUpsert:
    ebay_order_id: str
    buyer_username: Optional[str] = None
    buyer_email: Optional[str] = None
    item_id: Optional[str] = None
    item_title: Optional[str] = None
    quantity: Optional[int] = None
    total_value: Optional[float] = None
    currency: Optional[str] = None
    sold_at: Optional[str] = None
    shipping_address: Optional[dict[str, Any]] = None


def upsert_order(conn: sqlite3.Connection, order: OrderUpsert) -> None:
    now = _utc_now_iso()
    shipping_address_json = json.dumps(order.shipping_address, ensure_ascii=False) if order.shipping_address else None

    conn.execute(
        """
        INSERT INTO orders (
            ebay_order_id, buyer_username, buyer_email, item_id, item_title, quantity,
            total_value, currency, sold_at, shipping_address_json, status, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT status FROM orders WHERE ebay_order_id = ?), 'pending'), ?)
        ON CONFLICT(ebay_order_id) DO UPDATE SET
            buyer_username=excluded.buyer_username,
            buyer_email=excluded.buyer_email,
            item_id=excluded.item_id,
            item_title=excluded.item_title,
            quantity=excluded.quantity,
            total_value=excluded.total_value,
            currency=excluded.currency,
            sold_at=excluded.sold_at,
            shipping_address_json=excluded.shipping_address_json,
            last_seen_at=excluded.last_seen_at;
        """,
        (
            order.ebay_order_id,
            order.buyer_username,
            order.buyer_email,
            order.item_id,
            order.item_title,
            order.quantity,
            order.total_value,
            order.currency,
            order.sold_at,
            shipping_address_json,
            order.ebay_order_id,
            now,
        ),
    )
    conn.commit()


def set_order_status(conn: sqlite3.Connection, ebay_order_id: str, status: str) -> None:
    conn.execute("UPDATE orders SET status=? WHERE ebay_order_id=?", (status, ebay_order_id))
    conn.commit()


def list_orders(conn: sqlite3.Connection, *, status: Optional[str] = None, limit: int = 50) -> list[sqlite3.Row]:
    if status:
        cur = conn.execute(
            "SELECT * FROM orders WHERE status=? ORDER BY (sold_at IS NULL) ASC, sold_at DESC, id DESC LIMIT ?",
            (status, limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM orders ORDER BY (sold_at IS NULL) ASC, sold_at DESC, id DESC LIMIT ?",
            (limit,),
        )
    return list(cur.fetchall())


def get_order(conn: sqlite3.Connection, ebay_order_id: str) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM orders WHERE ebay_order_id=?", (ebay_order_id,))
    return cur.fetchone()


def upsert_package(
    conn: sqlite3.Connection,
    *,
    ebay_order_id: str,
    weight_kg: float,
    length_cm: float,
    width_cm: float,
    height_cm: float,
    dhl_service: Optional[str] = None,
    dhl_price_gbp: Optional[float] = None,
    collection_type: Optional[str] = None,
) -> None:
    now = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO packages (
            ebay_order_id, weight_kg, length_cm, width_cm, height_cm,
            dhl_service, dhl_price_gbp, collection_type,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ebay_order_id) DO UPDATE SET
            weight_kg=excluded.weight_kg,
            length_cm=excluded.length_cm,
            width_cm=excluded.width_cm,
            height_cm=excluded.height_cm,
            dhl_service=excluded.dhl_service,
            dhl_price_gbp=excluded.dhl_price_gbp,
            collection_type=excluded.collection_type,
            updated_at=excluded.updated_at;
        """,
        (
            ebay_order_id,
            weight_kg,
            length_cm,
            width_cm,
            height_cm,
            dhl_service,
            dhl_price_gbp,
            collection_type,
            now,
            now,
        ),
    )
    conn.commit()


def get_package(conn: sqlite3.Connection, ebay_order_id: str) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM packages WHERE ebay_order_id=?", (ebay_order_id,))
    return cur.fetchone()


def upsert_message(
    conn: sqlite3.Connection,
    *,
    ebay_message_id: str,
    ebay_order_id: Optional[str] = None,
    from_user: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    received_at: Optional[str] = None,
    status: str = "unread",
) -> None:
    now = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO messages (
            ebay_message_id, ebay_order_id, from_user, subject, body,
            received_at, status, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ebay_message_id) DO UPDATE SET
            ebay_order_id=excluded.ebay_order_id,
            from_user=excluded.from_user,
            subject=excluded.subject,
            body=excluded.body,
            received_at=excluded.received_at,
            last_seen_at=excluded.last_seen_at;
        """,
        (ebay_message_id, ebay_order_id, from_user, subject, body, received_at, status, now),
    )
    conn.commit()


def set_message_draft(conn: sqlite3.Connection, ebay_message_id: str, draft_response: str) -> None:
    conn.execute(
        "UPDATE messages SET draft_response=?, status='drafted' WHERE ebay_message_id=?",
        (draft_response, ebay_message_id),
    )
    conn.commit()


def set_message_status(conn: sqlite3.Connection, ebay_message_id: str, status: str) -> None:
    conn.execute("UPDATE messages SET status=? WHERE ebay_message_id=?", (status, ebay_message_id))
    conn.commit()


def list_messages(conn: sqlite3.Connection, *, status: Optional[str] = None, limit: int = 50) -> list[sqlite3.Row]:
    if status:
        cur = conn.execute(
            "SELECT * FROM messages WHERE status=? ORDER BY (received_at IS NULL) ASC, received_at DESC, id DESC LIMIT ?",
            (status, limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM messages ORDER BY (received_at IS NULL) ASC, received_at DESC, id DESC LIMIT ?",
            (limit,),
        )
    return list(cur.fetchall())


def upsert_inventory_item(
    conn: sqlite3.Connection,
    *,
    kind: str,
    name: str,
    qty: int,
    reorder_threshold: int = 0,
    length_cm: Optional[float] = None,
    width_cm: Optional[float] = None,
    height_cm: Optional[float] = None,
    notes: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inventory_items (kind, name, length_cm, width_cm, height_cm, qty, reorder_threshold, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(kind, name) DO UPDATE SET
            length_cm=excluded.length_cm,
            width_cm=excluded.width_cm,
            height_cm=excluded.height_cm,
            qty=excluded.qty,
            reorder_threshold=excluded.reorder_threshold,
            notes=excluded.notes;
        """,
        (kind, name, length_cm, width_cm, height_cm, qty, reorder_threshold, notes),
    )
    conn.commit()


def list_inventory(conn: sqlite3.Connection, *, kind: Optional[str] = None) -> list[sqlite3.Row]:
    if kind:
        cur = conn.execute("SELECT * FROM inventory_items WHERE kind=? ORDER BY name ASC", (kind,))
    else:
        cur = conn.execute("SELECT * FROM inventory_items ORDER BY kind ASC, name ASC")
    return list(cur.fetchall())

