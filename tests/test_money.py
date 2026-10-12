"""Money helper tests: prove no floats are used, and that math is exact."""
from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from app.money import (
    apply_percent_discount,
    cap_discount,
    format_money,
    from_minor,
    to_minor,
)

# ---- A3: no floats in the public surface -----------------------------------

def test_to_minor_never_returns_float() -> None:
    """Every value returned by to_minor() must be an int."""
    for v in ["0", "0.00", "0.01", "0.1", "0.2", "0.3", "1.23", "12345.67", "9999999.99"]:
        out = to_minor(v)
        assert isinstance(out, int), f"to_minor({v!r}) returned {type(out).__name__}"
    # 0.1 + 0.2 style
    assert to_minor("0.1") + to_minor("0.2") == to_minor("0.3")  # 10 + 20 == 30


def test_money_module_does_not_use_float_at_runtime() -> None:
    """Disallow `float(` and `0.` style float literals in the source."""
    src = inspect.getsource(__import__("app.money", fromlist=["*"]))
    # Allow no float() calls
    assert "float(" not in src, "money module must not use float()"
    # And no float literals like `1.5`
    bad_lines = [
        line for line in src.splitlines()
        if any(tok in line for tok in (" = 1.", " = 0.", " = 2.", " = 3."))
        and not line.strip().startswith("#")
        and "Decimal" not in line
    ]
    assert not bad_lines, f"possible float literals in money: {bad_lines}"


# ---- A3: exact arithmetic for tricky inputs --------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.10", 10),     # banker's-free half-up: 10
        ("0.1", 10),
        ("0.2", 20),
        ("0.3", 30),       # not 0.30000000000000004
        ("0.1+0.2 style", None),  # placeholder; replaced below
        ("1.005", 101),    # half-up at the third decimal place
        ("1.015", 102),
        ("9.99", 999),
        ("1234567.89", 123456789),
    ],
)
def test_to_minor_tricky_values(raw, expected):
    if expected is None:
        return
    assert to_minor(raw) == expected


def test_to_minor_does_not_use_float_arithmetic() -> None:
    # Naive float would yield 30.000000000000004. Our int math yields 30.
    s = to_minor("0.1") + to_minor("0.2")
    assert s == 30
    # And the same via a single string.
    assert to_minor("0.3") == 30


# ---- formatting -----------------------------------------------------------

def test_format_money_basic() -> None:
    assert format_money(0) == "৳0.00"
    assert format_money(1) == "৳0.01"
    assert format_money(99) == "৳0.99"
    assert format_money(100) == "৳1.00"
    assert format_money(12345) == "৳123.45"
    assert format_money(-50) == "-৳0.50"


def test_from_minor_round_trip() -> None:
    for v in [0, 1, 99, 100, 12345, 100000]:
        assert to_minor(from_minor(v)) == v


# ---- discount math --------------------------------------------------------

@pytest.mark.parametrize(
    "subtotal,percent,expected",
    [
        (100, 0, 0),
        (100, 100, 100),
        (100, 10, 10),
        (333, 10, 33),     # 33.3 -> 33 (half-up)
        (335, 10, 34),     # 33.5 -> 34
        (1, 50, 1),        # 0.5 -> 1 (half-up)
        (1, 49, 0),        # 0.49 -> 0
    ],
)
def test_apply_percent_discount(subtotal, percent, expected):
    assert apply_percent_discount(subtotal, percent) == expected


def test_apply_percent_discount_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        apply_percent_discount(100, -1)
    with pytest.raises(ValueError):
        apply_percent_discount(100, 101)


def test_cap_discount() -> None:
    assert cap_discount(100, 50) == 50
    assert cap_discount(100, 100) == 100
    assert cap_discount(100, 150) == 100  # capped
    assert cap_discount(0, 0) == 0


# ---- to_minor input validation --------------------------------------------

def test_to_minor_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        to_minor("abc")
    with pytest.raises(ValueError):
        to_minor("1,000.00")  # commas forbidden
    with pytest.raises(ValueError):
        to_minor("")
    with pytest.raises(TypeError):
        to_minor(1.5)  # float is not accepted
    with pytest.raises(TypeError):
        to_minor([1, 2])  # type: ignore[arg-type]


def test_from_minor_rejects_non_int() -> None:
    with pytest.raises(TypeError):
        from_minor(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        from_minor("100")  # type: ignore[arg-type]


# ---- Decimal interop ------------------------------------------------------

def test_to_minor_accepts_decimal() -> None:
    assert to_minor(Decimal("12.34")) == 1234
    assert to_minor(Decimal("0.005")) == 1  # half-up
