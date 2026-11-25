"""Corpus generator: invoices and receipts with known gold values.

The point is not realism for its own sake. Each layout variant isolates one
thing a document extractor can get wrong:

* ``plain``      - one label per line, value on the same line;
* ``columns``    - label column and value column at separate x positions;
* ``distractor`` - a second date, a previous balance, a ship-to party;
* ``aliases``    - "Subtotal (excl. VAT)", "Balance due", "Net 30";
* ``no_po``      - purchase order genuinely absent (abstention target);
* ``no_terms``   - payment terms genuinely absent;
* ``inconsistent`` - total does not equal subtotal + tax (the validator's target).

Gold is written as ``gold.json``: the values, and for every field an explicit
``present`` flag, because "absent" is a claim the extractor has to get right too.
"""
import json
import random
from pathlib import Path

from .pdfwrite import write_pdf

FIELDS = [
    "invoice_number",
    "invoice_date",
    "vendor",
    "currency",
    "subtotal",
    "tax",
    "total",
    "purchase_order",
    "payment_terms",
]

VENDORS = [
    ("Northwind Freight", "Hamburg"),
    ("Northwind Freight Services", "Bremen"),
    ("Baltic Paper Works", "Gdansk"),
    ("Sierra Components Ltd", "Lisbon"),
    ("Meridian Optics", "Trieste"),
]

TERMS = ["Net 30", "Net 14", "Due on receipt", "2/10 net 30"]

CURRENCIES = [("EUR", "€"), ("USD", "$"), ("GBP", "£")]


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _layout(variant: str, rng: random.Random) -> tuple[list[tuple[float, float, float, str]], dict]:
    """Return (pdf lines, gold fields) for one document."""
    vendor, city = rng.choice(VENDORS)
    currency_code, symbol = rng.choice(CURRENCIES)
    year = rng.choice([2024, 2025])
    number = f"INV-{year}-{rng.randint(1000, 9999)}"
    day = rng.randint(1, 28)
    month = rng.randint(1, 12)
    date_iso = f"{year}-{month:02d}-{day:02d}"
    date_display = f"{day:02d}.{month:02d}.{year}"

    subtotal = round(rng.uniform(120, 4800), 2)
    rate = rng.choice([0.0, 0.07, 0.19, 0.21])
    tax = round(subtotal * rate, 2)
    total = round(subtotal + tax, 2)
    consistent = True
    if variant == "inconsistent":
        total = round(total + rng.choice([-35.0, 12.5, 90.0]), 2)
        consistent = False

    po = f"PO-{rng.randint(10000, 99999)}"
    terms = rng.choice(TERMS)

    present = {field: True for field in FIELDS}
    if variant == "no_po":
        present["purchase_order"] = False
    if variant == "no_terms":
        present["payment_terms"] = False
    if rate == 0.0:
        # A zero-tax document is not a missing field: the value is 0.00 and the
        # answer "absent" is wrong, which is exactly the distinction we score.
        present["tax"] = True

    gold = {
        "invoice_number": number,
        "invoice_date": date_iso,
        "vendor": vendor,
        "currency": currency_code,
        "subtotal": f"{subtotal:.2f}",
        "tax": f"{tax:.2f}",
        "total": f"{total:.2f}",
        "purchase_order": po if present["purchase_order"] else None,
        "payment_terms": terms if present["payment_terms"] else None,
        "present": present,
        "consistent": consistent,
        "variant": variant,
    }

    lines: list[tuple[float, float, float, str]] = []

    def put(x: float, y: float, text: str, size: float = 10.0) -> None:
        lines.append((x, y, size, text))

    put(60, 790, vendor, 14.0)
    put(60, 772, f"{city}, EU", 9.0)
    put(430, 790, "INVOICE", 12.0)

    if variant in {"columns", "aliases", "distractor"}:
        label_x, value_x = 60, 300
        row_y = 720
        put(label_x, row_y, "Invoice no.")
        put(value_x, row_y, number)
        put(label_x, row_y - 18, "Invoice date")
        put(value_x, row_y - 18, date_display)
        put(label_x, row_y - 36, "Currency")
        put(value_x, row_y - 36, currency_code)
        if present["purchase_order"]:
            put(label_x, row_y - 54, "Purchase order")
            put(value_x, row_y - 54, po)
        if present["payment_terms"]:
            put(label_x, row_y - 72, "Payment terms")
            put(value_x, row_y - 72, terms)
        table_y = 560
        sub_label = "Subtotal (excl. VAT)" if variant == "aliases" else "Subtotal"
        put(label_x, table_y, sub_label)
        put(value_x, table_y, f"{symbol}{_money(subtotal)}")
        put(label_x, table_y - 18, "VAT" if variant == "aliases" else "Tax")
        put(value_x, table_y - 18, f"{symbol}{_money(tax)}")
        put(label_x, table_y - 36, "Balance due" if variant == "aliases" else "Total")
        put(value_x, table_y - 36, f"{symbol}{_money(total)}")
        if variant == "distractor":
            put(label_x, table_y - 72, "Previous balance")
            put(value_x, table_y - 72, f"{symbol}{_money(round(subtotal * 0.4, 2))}")
            put(label_x, table_y - 90, "Discount")
            put(value_x, table_y - 90, f"{symbol}0.00")
            put(label_x, 470, "Ship to")
            put(value_x, 470, "Sierra Components Ltd, Lisbon")
            put(label_x, 452, "Delivered on")
            put(value_x, 452, f"{day:02d}.{month:02d}.{year}")
    else:
        y = 720
        put(60, y, f"Invoice no.: {number}")
        put(60, y - 18, f"Invoice date: {date_display}" if variant != "plain" else f"Date: {date_display}")
        put(60, y - 36, f"Currency: {currency_code}")
        if present["purchase_order"]:
            put(60, y - 54, f"Purchase order: {po}")
        if present["payment_terms"]:
            put(60, y - 72, f"Payment terms: {terms}")
        put(60, 560, f"Subtotal: {symbol}{_money(subtotal)}")
        put(60, 542, f"Tax: {symbol}{_money(tax)}")
        put(60, 524, f"Total: {symbol}{_money(total)}")
        if variant == "distractor":
            put(60, 506, f"Previous balance: {symbol}{_money(round(subtotal * 0.4, 2))}")
            put(60, 488, "Ship to: Sierra Components Ltd, Lisbon")

    put(60, 120, "Payment within the stated terms. Thank you.", 8.0)
    return lines, gold


VARIANTS = ["plain", "columns", "distractor", "aliases", "no_po", "no_terms", "inconsistent"]


def build_corpus(root: Path, *, per_variant: int = 3, seed: int = 7) -> dict:
    """Write the PDFs plus ``gold.json`` into ``root`` and return the gold map."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # A different per_variant count renames every document, so stale PDFs from a
    # previous run would silently mismatch the new gold map.
    for stale in root.glob("*.pdf"):
        stale.unlink()
    rng = random.Random(seed)
    gold: dict[str, dict] = {}
    for variant in VARIANTS:
        for _ in range(per_variant):
            lines, fields = _layout(variant, rng)
            doc_id = f"{variant}_{len(gold):02d}"
            write_pdf(root / f"{doc_id}.pdf", lines)
            gold[doc_id] = fields
    (root / "gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return gold
