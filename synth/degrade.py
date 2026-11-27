"""Degraded documents: what a text-only extractor loses when the page gets worse.

The clean corpus isolates layout decisions. This one isolates *document quality*,
one degradation at a time, using the same invoice and the same gold values so the
only variable is the page:

* ``spaced``   — every glyph separated ("S u b t o t a l"), the way a badly
  kerning-aware OCR engine or a letter-spaced scan returns text;
* ``wrapped``  — the amount is split across two lines ("€560." / "53"), a value
  that is printed but never contiguous;
* ``stamped``  — a PAID stamp plus an "original total" from a previous invoice,
  i.e. another number of the same shape on the page;
* ``tiny``     — 5.5 pt text and eight boilerplate footer lines: the value is in
  the text layer but the retrieval budget has more competition for it;
* ``rotated``  — /Rotate 90 on the page, text layer untouched: nothing changes if
  the pipeline reads bytes rather than pixels;
* ``no_text``  — rectangles instead of glyphs: a scan without OCR, where the
  correct answer is "nothing to read" and every field must come back null.

Gold is deliberately identical to the clean document: the degradation never
changes a value, so a wrong answer is the pipeline's, not the corpus's.
"""
import json
import random
from pathlib import Path

from .corpus import _layout
from .pdfwrite import write_pdf

BASE_VARIANT = "columns"
DEGRADATIONS = ["spaced", "wrapped", "stamped", "tiny", "rotated", "no_text"]


def spaced(lines):
    """One space between every character, as a kerning-blind OCR would return it."""
    return [(x, y, size, " ".join(text)) for x, y, size, text in lines]


def wrapped(lines):
    """Split every amount before its last two digits onto the line below.

    The rows underneath move down by the same amount, so the continuation is a
    line of its own rather than a fragment glued to the next row: the failure this
    measures is "the value is printed in two pieces", not "the page is broken".
    """
    def is_amount(text):
        return any(mark in text for mark in "€$£") and any(ch.isdigit() for ch in text) \
            and text[-2:].isdigit()

    out = []
    shift = 0
    for x, y, size, text in lines:
        y = y - shift
        if is_amount(text):
            out.append((x, y, size, text[:-2]))
            out.append((x, y - 13, size, text[-2:]))
            shift += 13
        else:
            out.append((x, y, size, text))
    return out


def stamped(lines):
    """A PAID overlay and a balance from an earlier invoice, above the table."""
    overlay = [
        (200, 640, 26, "PAID"),
        (60, 610, 9, "Original total: €9,999.99"),
        (60, 596, 9, "Balance carried forward: €1,234.00"),
    ]
    return list(lines) + overlay


def tiny(lines):
    """Shrink the type and add boilerplate: the table competes for the budget."""
    boiler = [
        (60, 96 - index * 9, 6, f"Clause {index + 1}: standard terms apply unless agreed otherwise in writing.")
        for index in range(8)
    ]
    return [(x, y, max(5.5, size * 0.55), text) for x, y, size, text in lines] + boiler


def build_degraded_corpus(root: Path, *, per_kind: int = 2, seed: int = 11) -> dict:
    """Write the degraded PDFs plus their ``gold.json`` and return the gold map."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.glob("*.pdf"):
        stale.unlink()
    rng = random.Random(seed)
    gold: dict[str, dict] = {}
    for kind in DEGRADATIONS:
        for _ in range(per_kind):
            lines, fields = _layout(BASE_VARIANT, rng)
            doc_id = f"degr-{kind}-{len(gold):02d}"
            if kind == "spaced":
                lines = spaced(lines)
            elif kind == "wrapped":
                lines = wrapped(lines)
            elif kind == "stamped":
                lines = stamped(lines)
            elif kind == "tiny":
                lines = tiny(lines)
            write_pdf(
                root / f"{doc_id}.pdf",
                lines,
                rotate=90 if kind == "rotated" else 0,
                bare=kind == "no_text",
            )
            # The degradation never changes a value: only the page does.
            gold[doc_id] = dict(fields, variant=f"degr_{kind}")
    (root / "gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return gold
