from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading
from openai import OpenAI

import database
import dhl_shipping
import openai_costs
import openai_org_usage
import packing_inventory as inventory


def _iso_ebay(dt: datetime) -> str:
    # eBay Trading API commonly accepts e.g. 2026-01-08T12:00:00.000Z
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _env_required(name: str) -> str:
    v = _env(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def build_ebay_trading() -> Trading:
    return Trading(
        config_file=None,
        appid=_env_required("EBAY_APP_ID"),
        devid=_env_required("EBAY_DEV_ID"),
        certid=_env_required("EBAY_CERT_ID"),
        token=_env_required("EBAY_TOKEN"),
        siteid=_env("EBAY_SITE_ID", "3"),  # default: UK
    )


def build_openai() -> Optional[OpenAI]:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def sync_orders(api: Trading, conn, *, days: int = 30) -> int:
    """
    Pull recent orders (seller) from eBay and upsert into SQLite.
    """
    start = datetime.now(timezone.utc) - timedelta(days=days)
    end = datetime.now(timezone.utc)

    page = 1
    total_upserted = 0
    while True:
        request = {
            "OrderRole": "Seller",
            "OrderStatus": "All",
            "CreateTimeFrom": _iso_ebay(start),
            "CreateTimeTo": _iso_ebay(end),
            "Pagination": {"EntriesPerPage": 100, "PageNumber": page},
            "DetailLevel": "ReturnAll",
        }

        resp = api.execute("GetOrders", request)
        data = resp.dict()

        orders = _as_list((data.get("OrderArray") or {}).get("Order"))
        if not orders:
            break

        for o in orders:
            order_id = o.get("OrderID")
            if not order_id:
                continue

            # Basic totals
            total = o.get("Total") or {}
            total_value = total.get("value")
            currency = total.get("_currencyID") or total.get("currencyID")

            # Transactions -> pick first for basic item info
            txs = _as_list(((o.get("TransactionArray") or {}).get("Transaction")))
            first_tx = txs[0] if txs else {}
            item = first_tx.get("Item") or {}
            item_id = item.get("ItemID")
            item_title = item.get("Title")
            qty = first_tx.get("QuantityPurchased") or o.get("QuantityPurchased")

            buyer_username = o.get("BuyerUserID") or (first_tx.get("Buyer") or {}).get("UserID")

            shipping_address = o.get("ShippingAddress") or {}
            buyer_email = (o.get("Buyer") or {}).get("Email") or None

            database.upsert_order(
                conn,
                database.OrderUpsert(
                    ebay_order_id=str(order_id),
                    buyer_username=str(buyer_username) if buyer_username else None,
                    buyer_email=str(buyer_email) if buyer_email else None,
                    item_id=str(item_id) if item_id else None,
                    item_title=str(item_title) if item_title else None,
                    quantity=int(qty) if qty else None,
                    total_value=float(total_value) if total_value is not None else None,
                    currency=str(currency) if currency else None,
                    sold_at=o.get("CreatedTime"),
                    shipping_address=shipping_address if isinstance(shipping_address, dict) else {"raw": shipping_address},
                ),
            )
            total_upserted += 1

        # Pagination
        pag = data.get("PaginationResult") or {}
        total_pages = int(pag.get("TotalNumberOfPages") or 1)
        if page >= total_pages:
            break
        page += 1

    return total_upserted


def sync_messages(api: Trading, conn, *, days: int = 30) -> int:
    """
    Pull recent messages and upsert into SQLite.
    """
    start = datetime.now(timezone.utc) - timedelta(days=days)
    end = datetime.now(timezone.utc)

    page = 1
    total_upserted = 0
    while True:
        request = {
            "DetailLevel": "ReturnMessages",
            "StartTime": _iso_ebay(start),
            "EndTime": _iso_ebay(end),
            "Pagination": {"EntriesPerPage": 100, "PageNumber": page},
        }

        resp = api.execute("GetMyMessages", request)
        data = resp.dict()

        msgs = _as_list((data.get("Messages") or {}).get("Message"))
        if not msgs:
            break

        for m in msgs:
            msg_id = m.get("MessageID")
            if not msg_id:
                continue
            sender = (m.get("Sender") or {}).get("UserID") or m.get("Sender")
            subject = m.get("Subject")
            body = m.get("Text") or m.get("Body") or ""
            received_at = m.get("ReceiveDate")

            # Best-effort link to an order
            ebay_order_id = None
            if m.get("ExternalMessageID"):
                ebay_order_id = str(m.get("ExternalMessageID"))

            database.upsert_message(
                conn,
                ebay_message_id=str(msg_id),
                ebay_order_id=ebay_order_id,
                from_user=str(sender) if sender else None,
                subject=str(subject) if subject else None,
                body=str(body) if body else None,
                received_at=str(received_at) if received_at else None,
                status="unread",
            )
            total_upserted += 1

        pag = data.get("PaginationResult") or {}
        total_pages = int(pag.get("TotalNumberOfPages") or 1)
        if page >= total_pages:
            break
        page += 1

    return total_upserted


def _record_openai_usage(conn, *, model: str, resp, meta: dict) -> None:
    try:
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        est = openai_costs.estimate_cost_usd(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        database.insert_openai_usage(
            conn,
            model=model,
            endpoint="chat.completions",
            prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
            completion_tokens=int(completion_tokens) if completion_tokens is not None else None,
            total_tokens=int(total_tokens) if total_tokens is not None else None,
            estimated_cost_usd=float(est) if est is not None else None,
            meta=meta,
        )
    except Exception:
        pass


def draft_reply(conn, openai: OpenAI, *, message_row, order_row: Optional[Any]) -> str:
    """
    Create a buyer-friendly response draft (do not auto-send).
    """
    item_title = (order_row["item_title"] if order_row else None) or ""
    buyer = (message_row["from_user"] or "") if message_row else ""
    subject = (message_row["subject"] or "") if message_row else ""
    body = (message_row["body"] or "") if message_row else ""

    prompt = f"""
You are helping me respond to an eBay buyer message professionally and concisely.

Item title: {item_title}
Buyer username: {buyer}
Subject: {subject}
Message:
{body}

Write a helpful reply. If the buyer asks something unknown, ask a clarifying question instead of making up details.
Keep it polite and short.
"""

    model = _env("OPENAI_TEXT_MODEL", "gpt-4o-mini")
    resp = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful eBay seller assistant."},
            {"role": "user", "content": prompt.strip()},
        ],
        temperature=0.3,
        max_tokens=300,
    )
    _record_openai_usage(conn, model=model, resp=resp, meta={"purpose": "draft_reply"})
    return resp.choices[0].message.content.strip()


def _print_divider() -> None:
    print("-" * 60)


def show_dashboard(conn) -> None:
    pending = database.list_orders(conn, status="pending", limit=50)
    packed = database.list_orders(conn, status="packed", limit=20)
    unread = database.list_messages(conn, status="unread", limit=50)
    drafted = database.list_messages(conn, status="drafted", limit=20)

    print("=" * 60)
    print("eBay Account Dashboard")
    print("=" * 60)
    print()

    print(f"SOLD ITEMS PENDING SHIPMENT ({len(pending)})")
    _print_divider()
    for i, o in enumerate(pending, 1):
        print(f"{i}. {o['item_title'] or '(no title)'}")
        print(f"   OrderID: {o['ebay_order_id']}  Buyer: {o['buyer_username'] or '(unknown)'}  Total: {o['total_value'] or ''} {o['currency'] or ''}")
        if o["sold_at"]:
            print(f"   Sold: {o['sold_at']}")
    if not pending:
        print("(none)")
    print()

    print(f"PACKED (NOT MARKED SHIPPED) ({len(packed)})")
    _print_divider()
    for i, o in enumerate(packed, 1):
        pkg = database.get_package(conn, o["ebay_order_id"])
        pkg_str = ""
        if pkg:
            pkg_str = f" {pkg['weight_kg']}kg {pkg['length_cm']}x{pkg['width_cm']}x{pkg['height_cm']}cm"
        print(f"{i}. {o['item_title'] or '(no title)'}  OrderID: {o['ebay_order_id']}{pkg_str}")
    if not packed:
        print("(none)")
    print()

    print(f"UNREAD MESSAGES ({len(unread)})")
    _print_divider()
    for i, m in enumerate(unread, 1):
        print(f"{i}. From: {m['from_user'] or '(unknown)'}  Subject: {m['subject'] or ''}")
        excerpt = (m["body"] or "").replace("\n", " ")
        print(f"   {excerpt[:160]}{'...' if len(excerpt) > 160 else ''}")
    if not unread:
        print("(none)")
    print()

    print(f"DRAFTED (NOT SENT) ({len(drafted)})")
    _print_divider()
    for i, m in enumerate(drafted, 1):
        print(f"{i}. From: {m['from_user'] or '(unknown)'}  Subject: {m['subject'] or ''}")
        draft = (m["draft_response"] or "").replace("\n", " ")
        print(f"   Draft: {draft[:160]}{'...' if len(draft) > 160 else ''}")
    if not drafted:
        print("(none)")
    print()

    lows = inventory.low_stock(conn)
    print(f"PACKING MATERIALS LOW STOCK ({len(lows)})")
    _print_divider()
    for r in lows:
        print(f"- {r['kind']}: {r['name']} (qty={r['qty']} threshold={r['reorder_threshold']})")
    if not lows:
        print("(none)")

    print()


def _prompt(prompt: str) -> str:
    return input(prompt).strip()


def _prompt_float(prompt: str) -> float:
    while True:
        s = _prompt(prompt)
        try:
            return float(s)
        except ValueError:
            print("Enter a number.")


def _prompt_int(prompt: str) -> int:
    while True:
        s = _prompt(prompt)
        try:
            return int(s)
        except ValueError:
            print("Enter an integer.")


def pack_order(conn) -> None:
    pending = database.list_orders(conn, status="pending", limit=50)
    if not pending:
        print("No pending orders.")
        return

    print("Select an order to pack:")
    for i, o in enumerate(pending, 1):
        print(f"{i}. {o['item_title'] or '(no title)'}  OrderID: {o['ebay_order_id']}")

    idx = _prompt_int("Order number: ")
    if idx < 1 or idx > len(pending):
        print("Invalid selection.")
        return

    order = pending[idx - 1]

    weight_kg = _prompt_float("Packed weight (kg): ")
    length_cm = _prompt_float("Packed length (cm): ")
    width_cm = _prompt_float("Packed width (cm): ")
    height_cm = _prompt_float("Packed height (cm): ")

    parcel = dhl_shipping.Parcel(weight_kg=weight_kg, length_cm=length_cm, width_cm=width_cm, height_cm=height_cm)
    try:
        band, rate = dhl_shipping.quote(parcel)
    except dhl_shipping.DHLValidationError as e:
        print(f"DHL tier validation failed: {e}")
        return

    print()
    print(f"DHL tier: {band.name}")
    print(f"Recommended service: {rate.service}  Price: £{rate.price_gbp:.2f}")
    print("Services: depot_to_depot | servicepoint_to_depot | door_to_depot")
    preferred = _prompt("Preferred service (blank = recommended): ")
    if preferred:
        try:
            _, rate = dhl_shipping.quote(parcel, preferred_service=preferred)
        except dhl_shipping.DHLValidationError as e:
            print(f"Cannot use that service: {e}")
            return

    database.upsert_package(
        conn,
        ebay_order_id=order["ebay_order_id"],
        weight_kg=weight_kg,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        dhl_service=rate.service,
        dhl_price_gbp=rate.price_gbp,
        collection_type=rate.service,
    )
    database.set_order_status(conn, order["ebay_order_id"], "packed")

    # Inventory: suggest a box based on packed dims
    inventory.ensure_defaults(conn)
    suggested = inventory.suggest_box(conn, inventory.ItemDims(length_cm=length_cm, width_cm=width_cm, height_cm=height_cm))
    if suggested:
        print()
        print(f"Suggested box: {suggested.name} (qty={suggested.qty})")
        use_it = _prompt("Use this box? (y/n): ").lower()
        if use_it == "y":
            inventory.adjust_qty(conn, kind="box", name=suggested.name, delta=-1)
    print("Packed order saved.")


def draft_unread_messages(conn, openai: Optional[OpenAI]) -> None:
    unread = database.list_messages(conn, status="unread", limit=50)
    if not unread:
        print("No unread messages.")
        return
    if not openai:
        print("OPENAI_API_KEY not set; cannot draft. Set it and retry.")
        return

    for m in unread:
        order = None
        if m["ebay_order_id"]:
            order = database.get_order(conn, m["ebay_order_id"])

        print()
        _print_divider()
        print(f"From: {m['from_user'] or '(unknown)'}  Subject: {m['subject'] or ''}")
        print("Message:")
        print(m["body"] or "")
        print()
        draft = draft_reply(conn, openai, message_row=m, order_row=order)
        print("[Draft Reply]")
        print(draft)
        print()

        database.set_message_draft(conn, m["ebay_message_id"], draft)
        action = _prompt("Mark (k)eep as drafted, (d)one/handled, (s)kip: ").lower()
        if action == "d":
            database.set_message_status(conn, m["ebay_message_id"], "handled")
        elif action == "s":
            # revert to unread if user wants to skip
            database.set_message_status(conn, m["ebay_message_id"], "unread")


def build_dhl_collection(conn) -> None:
    packed = database.list_orders(conn, status="packed", limit=50)
    if not packed:
        print("No packed orders.")
        return

    print("Select a packed order to create DHL collection payload for:")
    for i, o in enumerate(packed, 1):
        print(f"{i}. {o['item_title'] or '(no title)'}  OrderID: {o['ebay_order_id']}")

    idx = _prompt_int("Order number: ")
    if idx < 1 or idx > len(packed):
        print("Invalid selection.")
        return

    order = packed[idx - 1]
    pkg = database.get_package(conn, order["ebay_order_id"])
    if not pkg:
        print("No package details saved for this order.")
        return

    parcel = dhl_shipping.Parcel(
        weight_kg=float(pkg["weight_kg"]),
        length_cm=float(pkg["length_cm"]),
        width_cm=float(pkg["width_cm"]),
        height_cm=float(pkg["height_cm"]),
    )
    _, rate = dhl_shipping.quote(parcel, preferred_service=pkg["dhl_service"] or None)

    receiver_address = {}
    try:
        receiver_address = json.loads(order["shipping_address_json"] or "{}")
    except Exception:
        receiver_address = {"raw": order["shipping_address_json"]}

    sender_name = _env("SENDER_NAME") or _prompt("Sender name: ")
    sender_phone = _env("SENDER_PHONE") or _prompt("Sender phone: ")
    sender_address = {
        "address1": _env("SENDER_ADDRESS1") or _prompt("Sender address line 1: "),
        "address2": _env("SENDER_ADDRESS2") or _prompt("Sender address line 2 (optional): "),
        "city": _env("SENDER_CITY") or _prompt("Sender city: "),
        "postcode": _env("SENDER_POSTCODE") or _prompt("Sender postcode: "),
        "country": _env("SENDER_COUNTRY", "GB"),
    }

    payload = dhl_shipping.build_collection_request_payload(
        parcel=parcel,
        rate=rate,
        receiver_name=order["buyer_username"] or "Buyer",
        receiver_address=receiver_address,
        reference=f"eBay:{order['ebay_order_id']}",
        collection_type=rate.service,
        sender_name=sender_name,
        sender_address=sender_address,
        sender_phone=sender_phone,
    )

    print()
    print("DHL collection request payload (generic):")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()
    do_http = _prompt("Send via HTTP now? (y/n): ").lower()
    if do_http == "y":
        try:
            resp = dhl_shipping.request_collection_via_http(payload)
            print("Booking response:")
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"HTTP booking failed: {e}")


def manage_inventory(conn) -> None:
    rows = database.list_inventory(conn)
    if not rows:
        print("No inventory rows found.")
        return

    print("Inventory:")
    for i, r in enumerate(rows, 1):
        dims = ""
        if r["kind"] == "box":
            dims = f" {r['length_cm']}x{r['width_cm']}x{r['height_cm']}cm"
        print(f"{i}. {r['kind']}: {r['name']}{dims}  qty={r['qty']}  threshold={r['reorder_threshold']}")

    print()
    idx = _prompt_int("Select item to edit (0 to exit): ")
    if idx == 0:
        return
    if idx < 1 or idx > len(rows):
        print("Invalid selection.")
        return

    r = rows[idx - 1]
    new_qty = _prompt_int(f"New qty for {r['name']}: ")
    new_thr = _prompt_int(f"New reorder threshold for {r['name']}: ")
    database.upsert_inventory_item(
        conn,
        kind=r["kind"],
        name=r["name"],
        qty=new_qty,
        reorder_threshold=new_thr,
        length_cm=r["length_cm"],
        width_cm=r["width_cm"],
        height_cm=r["height_cm"],
        notes=r["notes"],
    )
    print("Saved.")


def show_openai_usage(conn) -> None:
    days = int(_env("OPENAI_USAGE_DAYS", "30"))
    print()
    print("=" * 60)
    print(f"OpenAI usage & cost - last {days} days")
    print("=" * 60)

    # Prefer org endpoints
    try:
        s = openai_org_usage.usage_and_costs(days=days)
        print("Source: OpenAI org Usage/Costs API")
        if s.total_cost_usd is not None:
            print(f"Spend (USD): {s.total_cost_usd:.2f}")
        else:
            print("Spend (USD): (not available)")
        if s.total_tokens is not None:
            print(f"Tokens: {s.total_tokens} (input={s.total_input_tokens} output={s.total_output_tokens})")
        else:
            print("Tokens: (not available)")
        print()
        print("If this fails with 401/403, you may need an Admin API key (ADMIN_OPENAI_API_KEY).")
        return
    except Exception as e:
        print(f"API unavailable ({e}). Falling back to local estimate.")

    summary = database.openai_usage_summary(conn, days=days)
    print("Source: local token log (estimate)")
    print(f"Calls: {summary['calls']}")
    print(
        f"Tokens: {summary['total_tokens']} (prompt={summary['prompt_tokens']} completion={summary['completion_tokens']})"
    )
    print(f"Estimated cost (USD): {summary['estimated_cost_usd']:.6f}")
    print()
    print("Note: Local estimate uses a pricing table in openai_costs.py; edit it to match your billing for accuracy.")


def main() -> int:
    load_dotenv()

    conn = database.connect(_env("EBAY_DB_PATH", "ebay_data.db"))
    database.init_db(conn)
    inventory.ensure_defaults(conn)

    try:
        api = build_ebay_trading()
    except Exception as e:
        print(f"eBay credentials error: {e}")
        print("Set EBAY_APP_ID, EBAY_DEV_ID, EBAY_CERT_ID, EBAY_TOKEN (and optionally EBAY_SITE_ID=3 for UK).")
        return 2

    openai = build_openai()

    while True:
        print()
        print("Menu:")
        print("  1) Sync orders + messages from eBay")
        print("  2) Show dashboard")
        print("  3) Draft replies for unread messages (ChatGPT)")
        print("  4) Pack an order (enter weight/dims + DHL quote)")
        print("  5) Create DHL collection request payload")
        print("  6) Inventory (set box/material qty + reorder thresholds)")
        print("  7) OpenAI usage & cost (local estimate)")
        print("  0) Exit")

        choice = _prompt("> ")
        if choice == "0":
            return 0
        if choice == "1":
            days = int(_env("EBAY_SYNC_DAYS", "30"))
            try:
                o = sync_orders(api, conn, days=days)
                m = sync_messages(api, conn, days=days)
                print(f"Synced orders: {o}, messages: {m}")
            except ConnectionError as e:
                print(f"eBay API error: {e}")
        elif choice == "2":
            show_dashboard(conn)
        elif choice == "3":
            draft_unread_messages(conn, openai)
        elif choice == "4":
            pack_order(conn)
        elif choice == "5":
            build_dhl_collection(conn)
        elif choice == "6":
            manage_inventory(conn)
        elif choice == "7":
            show_openai_usage(conn)
        else:
            print("Unknown option.")


if __name__ == "__main__":
    raise SystemExit(main())

