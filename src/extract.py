"""Document extraction: one JSON call for all fields, then a focused repair pass.

The repair pass is the agentic part. Deterministic validation says *which* field
is wrong and *why*; the retrieval layer says which lines could answer it; the
model only re-reads those lines. That is cheaper and more reliable than asking a
3B model to re-audit a whole document, and it keeps the failure attributable:
if the repair still fails, the trace shows the lines the model had.
"""
import re

from pathlib import Path

from . import config, llm
from .retrieve import document_view, evidence_for
from .schema import FIELD_ORDER, SHAPES, arithmetic_check, normalize, validate
from .textio import normalize_date, normalize_money, pdf_lines

SYSTEM = "You extract fields from invoices. You return JSON only, and null when a value is absent."

DOC_PROMPT = """Read the invoice below and return one JSON object with these keys:
{keys}

Rules:
- Use only the text between BEGIN and END. Nothing else.
- A value that is not written there is null. Never guess, never compute, never copy an example.
- invoice_number and purchase_order: full code, e.g. INV-2024-1234.
- invoice_date: YYYY-MM-DD.
- vendor: the company name only, as printed on the first line of the document. Do not append the city or country.
- currency: three-letter code (EUR, USD, GBP).
- subtotal, tax, total: digits with two decimals, no symbol, no thousands separator.
- tax 0.00 is a real value: write "0.00", never null.
- purchase_order: null when the document has none.
- payment_terms: the wording as printed, e.g. "Net 30".

BEGIN
{evidence}
END
"""

FIELD_PROMPT = """The field "{field}" could not be read reliably. Read only these lines from the invoice:

{evidence}

Return JSON: {{"value": "<value or null>"}}
Rules: {rules}
"""

FIELD_RULES = {
    "invoice_number": "full code as printed (INV-YYYY-NNNN).",
    "invoice_date": "date as YYYY-MM-DD.",
    "vendor": "the seller's name as printed, no address.",
    "currency": "three-letter code.",
    "subtotal": "digits with two decimals, no symbol.",
    "tax": "digits with two decimals, no symbol. 0.00 is a value, not a missing field.",
    "total": "digits with two decimals, no symbol.",
    "purchase_order": "full PO code, or null if the lines have none.",
    "payment_terms": "wording as printed, or null if the lines have none.",
}


def _first_pass(lines: list[str], model: str) -> tuple[dict, dict]:
    prompt = DOC_PROMPT.format(keys=", ".join(FIELD_ORDER), evidence=document_view(lines))
    reply = llm.chat(prompt, system=SYSTEM, model=model)
    parsed = llm.parse_object(reply["text"]) or {}
    return parsed, reply


def _repair(field: str, lines: list[str], model: str) -> tuple[str | None, dict]:
    evidence = "\n".join(f"[{index}] {line}" for index, line in evidence_for(field, lines, limit=4))
    prompt = FIELD_PROMPT.format(field=field, evidence=evidence, rules=FIELD_RULES[field])
    reply = llm.chat(prompt, system=SYSTEM, model=model)
    parsed = llm.parse_object(reply["text"]) or {}
    return normalize(field, parsed.get("value")), reply


def find_source(value: str | None, lines: list[str]) -> int | None:
    """Which line actually prints this value. Used as the grounding check."""
    if value is None:
        return None
    candidates = {value, value.replace(".", ",")}
    if _is_number(value):
        candidates.add(f"{float(value):,.2f}")
    for index, line in enumerate(lines):
        for candidate in candidates:
            if candidate and candidate in line:
                return index
        if _is_number(value) and normalize_money(line) == value and re.search(r"\d", line):
            return index
        if _looks_like_date(value) and normalize_date(line) == value:
            return index
    return None


def _looks_like_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _is_number(value: str) -> bool:
    try:
        float(value)
        return value.count(".") == 1
    except ValueError:
        return False


def _printed_but_missing(field: str, lines: list[str]) -> bool:
    """The document prints a value of this field's shape, yet the model said null.

    This is the recall counterpart of validation: it catches "the value is right
    there and the answer was null" without asking the model to check itself.
    """
    shape = SHAPES.get(field)
    if not shape:
        return False
    for _, line in evidence_for(field, lines, limit=4):
        if re.search(shape, line, flags=re.IGNORECASE):
            return True
    return False


def extract(path: Path | str, *, model: str | None = None, repairs: int | None = None) -> dict:
    """Extract one document. Returns values, validation, grounding and the trace."""
    model = model or config.MODEL
    max_repairs = config.MAX_REPAIRS if repairs is None else repairs
    lines = pdf_lines(path)
    raw, first = _first_pass(lines, model)
    values = {field: normalize(field, raw.get(field)) for field in FIELD_ORDER}
    errors = {field: validate(field, values[field]) for field in FIELD_ORDER}
    seconds = first["seconds"]
    calls = 1
    trace = [{"stage": "first_pass", "raw": first["text"][:400], "seconds": first["seconds"]}]

    # Repair only what validation rejects and what the document can plausibly
    # answer: a required field, or an optional one whose keywords are present.
    suspects = [field for field in FIELD_ORDER if errors[field]]
    gaps = [
        field for field in FIELD_ORDER
        if field not in suspects and values[field] is None and _printed_but_missing(field, lines)
    ]
    repaired = 0
    for field in suspects + gaps:
        if repaired >= max_repairs:
            break
        if field not in suspects and not _printed_but_missing(field, lines):
            continue
        value, reply = _repair(field, lines, model)
        seconds += reply["seconds"]
        calls += 1
        repaired += 1
        trace.append({"stage": f"repair:{field}", "raw": reply["text"][:300], "seconds": reply["seconds"]})
        if value is not None:
            values[field] = value
            errors[field] = validate(field, value)

    sources = {field: find_source(values[field], lines) for field in FIELD_ORDER}
    arithmetic = arithmetic_check(values)
    return {
        "document": Path(path).name,
        "values": values,
        "errors": {k: v for k, v in errors.items() if v},
        "sources": sources,
        "ungrounded": [f for f, s in sources.items() if values[f] is not None and s is None],
        "arithmetic": arithmetic,
        "seconds": round(seconds, 2),
        "calls": calls,
        "trace": trace,
    }
