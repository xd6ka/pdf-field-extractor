"""Text layer access and normalisation shared by the pipeline and the eval."""
import re
from pathlib import Path

from pypdf import PdfReader


def pdf_lines(path: Path | str) -> list[str]:
    """Non-empty lines of a PDF's text layer, in page order."""
    reader = PdfReader(str(path))
    lines: list[str] = []
    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            stripped = raw.strip()
            if stripped:
                lines.append(stripped)
    return lines


def collapse(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


DATE_PATTERNS = [
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", "ymd"),
    (r"\b(\d{2})\.(\d{2})\.(\d{4})\b", "dmy"),
    (r"\b(\d{2})/(\d{2})/(\d{4})\b", "dmy"),
]


def normalize_date(value: str | None) -> str | None:
    """Return ISO date or None. Ambiguous input is not guessed."""
    if not value:
        return None
    for pattern, order in DATE_PATTERNS:
        match = re.search(pattern, value)
        if not match:
            continue
        a, b, c = match.groups()
        if order == "ymd":
            year, month, day = a, b, c
        else:
            day, month, year = a, b, c
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"
        return None
    return None


MONEY_RE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)(?![\d.])"
)


def normalize_money(value: str | None) -> str | None:
    """Return "1234.56" or None. Handles thousands separators and currency marks.

    A bare integer is a value ("0" is a real tax amount), a bare thousands group
    is not ("1,234" without decimals is ambiguous, so it is rejected).
    """
    if not value:
        return None
    cleaned = value.replace(" ", "").replace("\u00a0", "")
    match = MONEY_RE.search(cleaned)
    if not match:
        return None
    raw = match.group(1)
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", raw):
        raw = raw.replace(",", "").replace(".", "")
    # 1,234.56 and 1.234,56 both occur; the last separator decides.
    if "," in raw and "." in raw:
        decimal = "." if raw.rfind(".") > raw.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return f"{float(raw):.2f}"


def normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {"€": "EUR", "eur": "EUR", "euro": "EUR", "$": "USD", "usd": "USD",
               "£": "GBP", "gbp": "GBP", "pound": "GBP"}
    lowered = value.lower()
    for key, code in mapping.items():
        if key in lowered:
            return code
    return None
