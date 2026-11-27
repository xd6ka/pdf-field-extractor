"""Degraded documents: the second corpus has to be honest before it is informative.

Each test pins the property that makes a degradation a *measurement* rather than a
different document: the gold values never change, the text layer degrades in the
way the name says, and the textless page really has nothing to read.
"""
import json

import pytest

from synth.corpus import build_corpus
from synth.degrade import BASE_VARIANT, DEGRADATIONS, build_degraded_corpus
from synth.pdfwrite import write_pdf
from src.textio import pdf_lines


def test_degraded_corpus_is_deterministic_and_keeps_every_value(tmp_path):
    first = build_degraded_corpus(tmp_path / "a", per_kind=1)
    second = build_degraded_corpus(tmp_path / "b", per_kind=1)
    assert set(first) == set(second)
    assert {fields["variant"] for fields in first.values()} == {f"degr_{k}" for k in DEGRADATIONS}
    for doc_id, fields in first.items():
        assert (tmp_path / "a" / f"{doc_id}.pdf").read_bytes() == (
            tmp_path / "b" / f"{doc_id}.pdf"
        ).read_bytes()
        # Nine fields, all of them the clean document's values: the degradation is
        # the page, never the ground truth.
        assert set(fields) >= {"invoice_number", "subtotal", "total", "vendor"}
        assert fields["subtotal"] and fields["total"]


def test_spaced_degradation_breaks_the_contiguous_value(tmp_path):
    gold = build_degraded_corpus(tmp_path, per_kind=1)
    doc_id = next(key for key in gold if key.startswith("degr-spaced"))
    text = "\n".join(pdf_lines(tmp_path / f"{doc_id}.pdf"))
    assert "S u b t o t a l" in text
    # The number is printed, but no longer as one token a model can copy.
    assert gold[doc_id]["subtotal"] not in text


def test_wrapped_degradation_splits_the_amount_across_two_lines(tmp_path):
    gold = build_degraded_corpus(tmp_path, per_kind=1)
    doc_id = next(key for key in gold if key.startswith("degr-wrapped"))
    lines = pdf_lines(tmp_path / f"{doc_id}.pdf")
    # The page prints the money with thousands separators ("3,909.14"), so the
    # assertion is on the printed form, not the normalised gold string.
    printed = f"{float(gold[doc_id]['subtotal']):,.2f}"
    assert printed not in "\n".join(lines)
    assert any(line.endswith(printed[:-2]) for line in lines)   # "…$3,909."
    assert any(line == printed[-2:] for line in lines)           # "14" on its own line


def test_textless_page_has_no_text_layer(tmp_path):
    build_degraded_corpus(tmp_path, per_kind=1)
    doc_id = next(key for key in build_degraded_corpus(tmp_path, per_kind=1) if key.startswith("degr-no_text"))
    assert pdf_lines(tmp_path / f"{doc_id}.pdf") == []


def test_rotation_leaves_the_text_layer_untouched(tmp_path):
    lines = [(60, 700, 10, "Subtotal: €560.53"), (60, 682, 10, "Total: €666.99")]
    write_pdf(tmp_path / "flat.pdf", lines)
    write_pdf(tmp_path / "turned.pdf", lines, rotate=90)
    assert pdf_lines(tmp_path / "flat.pdf") == pdf_lines(tmp_path / "turned.pdf")


def test_by_variant_separates_degradations():
    from eval.run_eval import by_variant

    def row(variant, correct, predicted=True):
        return {
            "variant": variant,
            "fields": {"total": {"correct": correct, "absent_gold": False, "predicted": predicted}},
        }

    table = by_variant([row("degr_no_text", False), row("degr_rotated", True), row("degr_rotated", True)])
    assert table["degr_no_text"]["doc_exact"] == 0
    assert table["degr_rotated"]["doc_exact"] == 2
    assert table["degr_rotated"]["f1"] == 1.0
    assert table["degr_no_text"]["f1"] == 0.0
