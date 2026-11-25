"""Field schema: what a valid value looks like, and what to do with an invalid one.

The schema is the product contract, so it has to be strict enough to reject
garbage and permissive enough to accept the formats real invoices use. Anything
the normaliser cannot make canonical becomes ``None`` rather than a guess.
"""
import re

from .textio import normalize_currency, normalize_date, normalize_money

MONEY = "money"
DATE = "date"
CURRENCY = "currency"
IDENTIFIER = "identifier"
TEXT = "text"

MONEY_SHAPE = r"(?<![\d.])\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{2})?(?![\d.])"
DATE_SHAPE = r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}"
TERMS_SHAPE = r"\bnet\s*\d+|\bdue on receipt\b|\d+/\d+\s*net\s*\d+"

# "Shape" is the value pattern a field can have. It is used twice: to reject a
# predicted value that merely looks like text (the footer is not payment terms),
# and to notice that a value is printed even though the model answered null.
SHAPES = {
    "invoice_number": r"INV-\d{4}-\d{4}",
    "invoice_date": DATE_SHAPE,
    "currency": r"\b(EUR|USD|GBP)\b|[€$£]",
    "subtotal": MONEY_SHAPE,
    "tax": MONEY_SHAPE,
    "total": MONEY_SHAPE,
    "purchase_order": r"PO-\d{5}",
    "payment_terms": TERMS_SHAPE,
}

SPECS = {
    "invoice_number": {
        "kind": IDENTIFIER,
        "pattern": r"INV-\d{4}-\d{4}",
        "required": True,
        "keywords": ["invoice no", "invoice number", "invoice #", "inv", "document no"],
    },
    "invoice_date": {
        "kind": DATE,
        "required": True,
        "keywords": ["invoice date", "date", "issued", "issue date"],
    },
    "vendor": {
        "kind": TEXT,
        "required": True,
        "keywords": ["vendor", "from", "seller", "supplier"],
    },
    "currency": {
        "kind": CURRENCY,
        "required": True,
        "keywords": ["currency", "eur", "usd", "gbp", "€", "$", "£"],
    },
    "subtotal": {
        "kind": MONEY,
        "required": True,
        "keywords": ["subtotal", "sub total", "net", "excl"],
    },
    "tax": {
        "kind": MONEY,
        "required": True,
        "keywords": ["tax", "vat", "gst"],
    },
    "total": {
        "kind": MONEY,
        "required": True,
        "keywords": ["total", "balance due", "amount due", "grand total"],
    },
    "purchase_order": {
        "kind": IDENTIFIER,
        "pattern": r"PO-\d{5}",
        "required": False,
        "keywords": ["purchase order", "po", "po no", "po number"],
    },
    "payment_terms": {
        "kind": TEXT,
        # Not free text: "Payment within the stated terms. Thank you." is a
        # footer sentence, not a payment term, and it must not pass as one.
        "pattern": TERMS_SHAPE,
        "required": False,
        "keywords": ["terms", "net 30", "net 14", "net 60", "due"],
    },
}

FIELD_ORDER = list(SPECS)


def normalize(field: str, raw) -> str | None:
    if raw is None:
        return None
    text = str(raw) if not isinstance(raw, (int, float)) else f"{float(raw):.2f}"
    text = text.strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "unknown", "-"}:
        return None
    spec = SPECS[field]
    kind = spec["kind"]
    if kind == MONEY:
        return normalize_money(text)
    if kind == DATE:
        return normalize_date(text)
    if kind == CURRENCY:
        return normalize_currency(text)
    if kind == IDENTIFIER:
        match = re.search(spec["pattern"], text, flags=re.IGNORECASE)
        return match.group(0).upper() if match else None
    if spec.get("pattern"):
        # A patterned text field accepts only values of that shape; anything
        # else is not this field, however plausible it reads.
        return text if re.search(spec["pattern"], text, flags=re.IGNORECASE) else None
    return re.sub(r"\s+", " ", text).strip() or None


def validate(field: str, value: str | None) -> str | None:
    """Return an error string, or None when the value passes."""
    spec = SPECS[field]
    if value is None:
        return "missing" if spec["required"] else None
    if spec["kind"] == IDENTIFIER and not re.fullmatch(spec["pattern"], value, flags=re.IGNORECASE):
        return f"does not match {spec['pattern']}"
    if spec.get("pattern") and not re.search(spec["pattern"], value, flags=re.IGNORECASE):
        return f"does not match {spec['pattern']}"
    if field == "invoice_date":
        year = int(value[:4])
        if not 2000 <= year <= 2100:
            return "date out of range"
    if field == "vendor" and len(value) < 3:
        return "too short"
    return None


def arithmetic_check(values: dict[str, str | None], tolerance: float = 0.02) -> dict:
    """Subtotal + tax should equal total. Returns the verdict and the delta."""
    needed = [values.get("subtotal"), values.get("tax"), values.get("total")]
    if any(v is None for v in needed):
        return {"ok": None, "delta": None, "reason": "missing inputs"}
    subtotal, tax, total = (float(v) for v in needed)
    delta = round(subtotal + tax - total, 2)
    return {
        "ok": abs(delta) <= tolerance,
        "delta": delta,
        "reason": "" if abs(delta) <= tolerance else "subtotal + tax != total",
    }
