"""Retrieval, grounding and the repair trigger — the pipeline's own logic, no model."""
from pathlib import Path

from synth.corpus import build_corpus
from src.extract import _printed_but_missing, find_source
from src.retrieve import document_view, evidence_for, score_line
from src.textio import pdf_lines


def test_evidence_prefers_the_line_that_names_the_field():
    lines = ["Northwind Freight", "Invoice no. INV-2024-9011", "Previous balance $1,848.90",
             "Balance due $4,622.25", "Ship to Sierra Components Ltd"]
    top = [line for _, line in evidence_for("total", lines, limit=3)]
    assert "Balance due $4,622.25" in top
    assert "Previous balance" not in top[0]


def test_keywords_outrank_unrelated_lines():
    assert score_line("Subtotal (excl. VAT) $10.00", ["subtotal"]) > score_line("Thank you", ["subtotal"])


def test_evidence_falls_back_to_the_head_of_the_document():
    lines = ["Alpha", "Beta", "Gamma"]
    chosen = evidence_for("vendor", lines, limit=2)
    assert chosen and chosen[0][0] == 0


def test_document_view_respects_the_budget():
    lines = [f"line {index} with some text" for index in range(200)]
    view = document_view(lines, max_chars=200)
    assert len(view) <= 220
    assert view.count("\n") < len(lines)


def test_grounding_matches_a_date_printed_in_another_format():
    assert find_source("2024-11-18", ["Invoice date 18.11.2024"]) == 0
    assert find_source("2024-11-18", ["Invoice date 19.11.2024"]) is None


def test_grounding_matches_money_with_thousands_separator():
    assert find_source("4622.25", ["Total $4,622.25"]) == 0
    assert find_source("4622.25", ["Total $4,622.30"]) is None


def test_grounding_says_no_for_an_invented_value():
    assert find_source("Net 30", ["Payment within the stated terms. Thank you."]) is None


def test_repair_triggers_only_when_the_value_is_actually_printed():
    lines = ["Purchase order PO-83148", "Total $4,622.25"]
    assert _printed_but_missing("purchase_order", lines) is True
    assert _printed_but_missing("payment_terms", lines) is False


def test_repair_trigger_is_false_for_a_field_without_a_shape():
    assert _printed_but_missing("vendor", ["Northwind Freight"]) is False


def test_corpus_pipeline_end_to_end_without_a_model(tmp_path):
    gold = build_corpus(tmp_path, per_variant=1)
    for doc_id in gold:
        assert pdf_lines(Path(tmp_path) / f"{doc_id}.pdf")
