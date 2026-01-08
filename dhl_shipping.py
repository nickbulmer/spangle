from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class DHLValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Parcel:
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float

    def normalized_dims(self) -> tuple[float, float, float]:
        dims = sorted([self.length_cm, self.width_cm, self.height_cm], reverse=True)
        return dims[0], dims[1], dims[2]


@dataclass(frozen=True)
class DHLRate:
    service: str  # depot_to_depot | servicepoint_to_depot | door_to_depot
    price_gbp: float


@dataclass(frozen=True)
class DHLBand:
    name: str
    min_weight_exclusive: float
    max_weight_inclusive: float
    max_dims_cm: tuple[float, float, float]  # (L,W,H) but treated as sortable
    depot_to_depot_gbp: Optional[float]
    servicepoint_to_depot_gbp: Optional[float]
    door_to_depot_gbp: Optional[float]

    def fits(self, parcel: Parcel) -> bool:
        if parcel.weight_kg <= self.min_weight_exclusive:
            return False
        if parcel.weight_kg > self.max_weight_inclusive:
            return False
        pL, pW, pH = parcel.normalized_dims()
        bL, bW, bH = sorted(list(self.max_dims_cm), reverse=True)
        return pL <= bL and pW <= bW and pH <= bH


# Your provided DHL tier rules/prices (GBP inc. VAT)
BANDS: list[DHLBand] = [
    DHLBand(
        name="1-5kg",
        min_weight_exclusive=0.0,
        max_weight_inclusive=5.0,
        max_dims_cm=(35.0, 35.0, 35.0),
        depot_to_depot_gbp=2.79,
        servicepoint_to_depot_gbp=4.90,
        door_to_depot_gbp=7.09,
    ),
    DHLBand(
        name="5-10kg",
        min_weight_exclusive=5.0,
        max_weight_inclusive=10.0,
        max_dims_cm=(60.0, 60.0, 60.0),
        depot_to_depot_gbp=2.79,
        servicepoint_to_depot_gbp=4.90,
        door_to_depot_gbp=7.09,
    ),
    DHLBand(
        name="10-20kg",
        min_weight_exclusive=10.0,
        max_weight_inclusive=20.0,
        max_dims_cm=(60.0, 60.0, 60.0),
        depot_to_depot_gbp=4.90,
        servicepoint_to_depot_gbp=None,  # temporarily unavailable
        door_to_depot_gbp=13.90,
    ),
    DHLBand(
        name="20-30kg",
        min_weight_exclusive=20.0,
        max_weight_inclusive=30.0,
        max_dims_cm=(120.0, 70.0, 70.0),
        depot_to_depot_gbp=8.80,
        servicepoint_to_depot_gbp=None,  # temporarily unavailable
        door_to_depot_gbp=17.89,
    ),
]


def quote(parcel: Parcel, preferred_service: Optional[str] = None) -> tuple[DHLBand, DHLRate]:
    """
    Returns (band, rate) for the parcel.

    - If preferred_service is provided, returns that service if available.
    - Otherwise returns the cheapest available service for the matching band.
    """
    if parcel.weight_kg <= 0:
        raise DHLValidationError("weight_kg must be > 0")
    if parcel.length_cm <= 0 or parcel.width_cm <= 0 or parcel.height_cm <= 0:
        raise DHLValidationError("length_cm/width_cm/height_cm must be > 0")

    matching = [b for b in BANDS if b.fits(parcel)]
    if not matching:
        raise DHLValidationError(
            "Parcel does not fit any DHL tier. Check weight (<=30kg) and max dimensions."
        )

    # Prefer the smallest band that fits (should be unique by weight, but keep safe)
    band = matching[0]

    service_prices: dict[str, Optional[float]] = {
        "depot_to_depot": band.depot_to_depot_gbp,
        "servicepoint_to_depot": band.servicepoint_to_depot_gbp,
        "door_to_depot": band.door_to_depot_gbp,
    }

    if preferred_service:
        price = service_prices.get(preferred_service)
        if price is None:
            raise DHLValidationError(f"Preferred service '{preferred_service}' unavailable for band {band.name}")
        return band, DHLRate(service=preferred_service, price_gbp=price)

    available = [(svc, p) for svc, p in service_prices.items() if p is not None]
    svc, p = sorted(available, key=lambda x: x[1])[0]
    return band, DHLRate(service=svc, price_gbp=float(p))


def build_collection_request_payload(
    *,
    parcel: Parcel,
    rate: DHLRate,
    receiver_name: str,
    receiver_address: dict,
    reference: str,
    collection_type: str,
    sender_name: str,
    sender_address: dict,
    sender_phone: str,
) -> dict:
    """
    DHL API varies by product/region. This function builds a *generic* payload that can be
    adapted to your DHL booking endpoint/provider.
    """
    return {
        "provider": "DHL",
        "service": rate.service,
        "collection_type": collection_type,  # e.g. 'door_to_depot'
        "price_gbp": rate.price_gbp,
        "reference": reference,
        "parcel": {
            "weight_kg": parcel.weight_kg,
            "length_cm": parcel.length_cm,
            "width_cm": parcel.width_cm,
            "height_cm": parcel.height_cm,
        },
        "sender": {
            "name": sender_name,
            "address": sender_address,
            "phone": sender_phone,
        },
        "receiver": {
            "name": receiver_name,
            "address": receiver_address,
        },
    }


def request_collection_via_http(payload: dict) -> dict:
    """
    Optional integration point.

    To enable, set environment variables:
    - DHL_API_URL (your provider endpoint)
    - DHL_API_KEY (if required)

    If you don't have an API endpoint, use the returned payload to book manually.
    """
    import os

    import requests

    url = os.getenv("DHL_API_URL")
    if not url:
        raise RuntimeError("DHL_API_URL not set. Set it to enable HTTP booking, or use manual booking.")

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("DHL_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.content else {"ok": True}

