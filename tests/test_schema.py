"""Normalisation and schema: the layer that decides what counts as a value."""
import pytest

from src.schema import SHAPES, arithmetic_check, normalize, validate
from src.textio import normalize_currency, normalize_date, normalize_money


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("€1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("$0.00", "0.00"),
        ("0", "0.00"),
        ("560.53", "560.53"),
        ("  12 345,60 ", "12345.60"),
    ],
)
def test_money_formats(raw, expected):
    assert normalize_money(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "no total"])
def test_money_rejects_non_values(raw):
    assert normalize_money(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("03.09.2025", "2025-09-03"),
        ("14/01/2024", "2024-01-14"),
        ("2024-11-18", "2024-11-18"),
    ],
)
def test_date_formats(raw, expected):
    assert normalize_date(raw) == expected


def test_date_rejects_impossible_month():
    assert normalize_date("45.13.2025") is None


@pytest.mark.parametrize("raw,expected", [("€", "EUR"), ("EUR", "EUR"), ("$", "USD"), ("£", "GBP"), ("pound", "GBP")])
def test_currency(raw, expected):
    assert normalize_currency(raw) == expected


def test_identifier_requires_the_full_code():
    assert normalize("invoice_number", "INV-2024-1234") == "INV-2024-1234"
    assert normalize("invoice_number", "1234") is None


def test_footer_is_not_payment_terms():
    # The sentence is printed in the document and contains "terms"; it is still
    # not a payment term. This is the line between grounded and correct.
    assert normalize("payment_terms", "Payment within the stated terms. Thank you.") is None
    assert normalize("payment_terms", "Net 30") == "Net 30"
    assert normalize("payment_terms", "2/10 net 30") == "2/10 net 30"


def test_null_words_normalise_to_none():
    for raw in ("null", "N/A", "-", "unknown"):
        assert normalize("purchase_order", raw) is None


def test_required_field_missing_is_an_error():
    assert validate("total", None) == "missing"
    assert validate("purchase_order", None) is None


def test_zero_tax_is_a_value_not_a_missing_field():
    assert validate("tax", "0.00") is None
    assert normalize("tax", "0") == "0.00"


def test_arithmetic_check():
    ok = arithmetic_check({"subtotal": "100.00", "tax": "19.00", "total": "119.00"})
    assert ok["ok"] is True and ok["delta"] == 0.0
    bad = arithmetic_check({"subtotal": "100.00", "tax": "19.00", "total": "130.00"})
    assert bad["ok"] is False and bad["delta"] == -11.0
    missing = arithmetic_check({"subtotal": None, "tax": "19.00", "total": "119.00"})
    assert missing["ok"] is None


def test_every_field_has_a_shape_where_one_is_meaningful():
    for field in ("invoice_number", "invoice_date", "currency", "subtotal", "tax", "total",
                  "purchase_order", "payment_terms"):
        assert field in SHAPES
