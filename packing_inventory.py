from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from itertools import permutations
from typing import Optional


@dataclass(frozen=True)
class ItemDims:
    length_cm: float
    width_cm: float
    height_cm: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.length_cm, self.width_cm, self.height_cm)


@dataclass(frozen=True)
class Box:
    name: str
    length_cm: float
    width_cm: float
    height_cm: float
    qty: int
    reorder_threshold: int

    def dims(self) -> tuple[float, float, float]:
        return (self.length_cm, self.width_cm, self.height_cm)


DEFAULT_BOXES: list[dict] = [
    {
        "kind": "box",
        "name": "Small_35x35x35",
        "length_cm": 35.0,
        "width_cm": 35.0,
        "height_cm": 35.0,
        "qty": 0,
        "reorder_threshold": 2,
        "notes": "DHL 1-5kg max size tier box",
    },
    {
        "kind": "box",
        "name": "Medium_60x60x60",
        "length_cm": 60.0,
        "width_cm": 60.0,
        "height_cm": 60.0,
        "qty": 0,
        "reorder_threshold": 2,
        "notes": "DHL 5-10kg and 10-20kg max size tier box",
    },
    {
        "kind": "box",
        "name": "Large_120x70x70",
        "length_cm": 120.0,
        "width_cm": 70.0,
        "height_cm": 70.0,
        "qty": 0,
        "reorder_threshold": 1,
        "notes": "DHL 20-30kg max size tier box",
    },
]

DEFAULT_MATERIALS: list[dict] = [
    {"kind": "material", "name": "PackingTape", "qty": 0, "reorder_threshold": 1, "notes": "rolls"},
    {"kind": "material", "name": "BubbleWrap", "qty": 0, "reorder_threshold": 1, "notes": "rolls"},
    {"kind": "material", "name": "VoidFill", "qty": 0, "reorder_threshold": 1, "notes": "bags/rolls"},
    {"kind": "material", "name": "FragileLabels", "qty": 0, "reorder_threshold": 1, "notes": "sheets"},
]


def ensure_defaults(conn: sqlite3.Connection) -> None:
    """
    Seeds default box/material rows (idempotent).
    """
    for row in [*DEFAULT_BOXES, *DEFAULT_MATERIALS]:
        conn.execute(
            """
            INSERT INTO inventory_items (kind, name, length_cm, width_cm, height_cm, qty, reorder_threshold, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, name) DO NOTHING;
            """,
            (
                row.get("kind"),
                row.get("name"),
                row.get("length_cm"),
                row.get("width_cm"),
                row.get("height_cm"),
                row.get("qty", 0),
                row.get("reorder_threshold", 0),
                row.get("notes"),
            ),
        )
    conn.commit()


def _fits(item: ItemDims, box_dims: tuple[float, float, float]) -> bool:
    for perm in permutations(item.as_tuple(), 3):
        if perm[0] <= box_dims[0] and perm[1] <= box_dims[1] and perm[2] <= box_dims[2]:
            return True
    return False


def list_boxes(conn: sqlite3.Connection) -> list[Box]:
    cur = conn.execute(
        "SELECT name, length_cm, width_cm, height_cm, qty, reorder_threshold FROM inventory_items WHERE kind='box' ORDER BY length_cm ASC, width_cm ASC, height_cm ASC"
    )
    boxes: list[Box] = []
    for r in cur.fetchall():
        boxes.append(
            Box(
                name=r["name"],
                length_cm=float(r["length_cm"] or 0),
                width_cm=float(r["width_cm"] or 0),
                height_cm=float(r["height_cm"] or 0),
                qty=int(r["qty"] or 0),
                reorder_threshold=int(r["reorder_threshold"] or 0),
            )
        )
    return boxes


def suggest_box(conn: sqlite3.Connection, item: ItemDims) -> Optional[Box]:
    """
    Returns the smallest (by volume) box that fits the item, if any.
    """
    candidates: list[Box] = []
    for b in list_boxes(conn):
        if b.length_cm <= 0 or b.width_cm <= 0 or b.height_cm <= 0:
            continue
        if _fits(item, b.dims()):
            candidates.append(b)

    if not candidates:
        return None
    return sorted(candidates, key=lambda b: (b.length_cm * b.width_cm * b.height_cm))[0]


def adjust_qty(conn: sqlite3.Connection, *, kind: str, name: str, delta: int) -> None:
    conn.execute(
        "UPDATE inventory_items SET qty = MAX(qty + ?, 0) WHERE kind=? AND name=?",
        (delta, kind, name),
    )
    conn.commit()


def set_qty(conn: sqlite3.Connection, *, kind: str, name: str, qty: int) -> None:
    conn.execute(
        "UPDATE inventory_items SET qty = ? WHERE kind=? AND name=?",
        (max(int(qty), 0), kind, name),
    )
    conn.commit()


def low_stock(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT * FROM inventory_items
        WHERE qty <= reorder_threshold
        ORDER BY kind ASC, name ASC
        """
    )
    return list(cur.fetchall())

