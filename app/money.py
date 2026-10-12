"""Money helper: all money is integer minor units (paisa). No floats, ever.

Tests prove that the helper never uses float arithmetic for storage or computation.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MINOR_UNITS_PER_UNIT = 100  # 1 BDT = 100 paisa

# Characters we explicitly reject as money inputs to avoid surprises.
_FORBIDDEN_INPUT_CHARS = set(", \u00a0\t\n\r")


def to_minor(amount: int | str | Decimal) -> int:
    """Convert a money amount to integer minor units (paisa).

    Accepts: int (already minor units), str like "12.34" or "12", or Decimal.
    Uses Decimal under the hood but returns int.
    """
    if isinstance(amount, int) and not isinstance(amount, bool):
        return amount
    if isinstance(amount, Decimal):
        d = amount
    elif isinstance(amount, str):
        s = amount.strip()
        if any(c in _FORBIDDEN_INPUT_CHARS for c in s):
            raise ValueError(f"invalid money input: {amount!r}")
        try:
            d = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(f"invalid money input: {amount!r}") from exc
    else:
        raise TypeError(f"unsupported money type: {type(amount).__name__}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"invalid money input: {amount!r}")
    # Multiply by 100, then round half-up to nearest integer.
    minor = (d * MINOR_UNITS_PER_UNIT).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def from_minor(minor: int) -> Decimal:
    """Convert integer minor units back to Decimal (still no float)."""
    if not isinstance(minor, int) or isinstance(minor, bool):
        raise TypeError("from_minor requires int")
    return (Decimal(minor) / Decimal(MINOR_UNITS_PER_UNIT)).quantize(Decimal("0.01"))


def format_money(minor: int, symbol: str = "৳") -> str:
    """Format minor units as a human string with a currency symbol, e.g. "৳12.34"."""
    if not isinstance(minor, int) or isinstance(minor, bool):
        raise TypeError("format_money requires int")
    sign = "-" if minor < 0 else ""
    abs_minor = abs(minor)
    whole = abs_minor // MINOR_UNITS_PER_UNIT
    fraction = abs_minor % MINOR_UNITS_PER_UNIT
    return f"{sign}{symbol}{whole}.{fraction:02d}"


def apply_percent_discount(subtotal_minor: int, percent: int) -> int:
    """Apply a percent discount (0..100 inclusive) to a minor-unit subtotal.

    Uses banker's-free half-up rounding. Returns the discount amount in minor units.
    A percent outside 0..100 is invalid.
    """
    if not isinstance(percent, int) or isinstance(percent, bool):
        raise TypeError("percent must be int")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100 inclusive")
    if subtotal_minor < 0:
        raise ValueError("subtotal must be non-negative")
    # (subtotal * percent) / 100, with half-up rounding.
    d = (Decimal(subtotal_minor) * Decimal(percent) / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(d)


def cap_discount(subtotal_minor: int, discount_minor: int) -> int:
    """Cap a discount so it never exceeds the subtotal. Returns int minor units."""
    if subtotal_minor < 0:
        raise ValueError("subtotal must be non-negative")
    if discount_minor < 0:
        raise ValueError("discount must be non-negative")
    return min(discount_minor, subtotal_minor)
