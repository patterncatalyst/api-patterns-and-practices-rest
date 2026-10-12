"""Deterministic quote formula, identical on both stacks so the Quarkus and
FastAPI responses are byte-for-byte comparable (see ../README.md):

    quote.currency = "USD"
    quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")

The amount is always rendered as a decimal STRING ("1250.00"), per
`#/$defs/Money` in the shared schema — never a JSON number.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from app.models import Cargo, CargoRequest, Money

_RATE_PER_KG = 2.50


def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = str(
        Decimal(str(total_weight_kg * _RATE_PER_KG)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    return Money(currency="USD", amount=amount)
