"""Corpus and PDF writer: the fixtures have to be trustworthy before scoring."""
import json
from pathlib import Path

from synth.corpus import VARIANTS, build_corpus
from src.textio import pdf_lines


def test_generated_pdf_keeps_its_own_values(tmp_path):
    gold = build_corpus(tmp_path, per_variant=1)
    for doc_id, fields in gold.items():
        lines = pdf_lines(tmp_path / f"{doc_id}.pdf")
        assert lines, doc_id
        assert fields["invoice_number"] in "\n".join(lines)
        assert fields["vendor"] in "\n".join(lines)


def test_header_and_city_are_separate_lines(tmp_path):
    build_corpus(tmp_path, per_variant=1, seed=3)
    lines = pdf_lines(tmp_path / "plain_00.pdf")
    # The vendor rule ("company name only") is checkable because the city sits on
    # its own line; if the writer merged them the rule would be untestable.
    assert lines[0] and not lines[0].endswith(", EU")
    assert ", EU" in lines[1]


def test_gold_matches_pdf_content(tmp_path):
    gold = build_corpus(tmp_path, per_variant=1, seed=11)
    for doc_id, fields in gold.items():
        text = "\n".join(pdf_lines(tmp_path / f"{doc_id}.pdf"))
        assert fields["subtotal"].replace(".", "").replace(",", "") in text.replace(".", "").replace(",", "")
        if fields["purchase_order"]:
            assert fields["purchase_order"] in text
        if fields["payment_terms"]:
            assert fields["payment_terms"] in text


def test_variants_cover_the_intended_cases(tmp_path):
    gold = build_corpus(tmp_path, per_variant=1)
    variants = {fields["variant"] for fields in gold.values()}
    assert variants == set(VARIANTS)
    absent_po = [f for f in gold.values() if f["purchase_order"] is None]
    absent_terms = [f for f in gold.values() if f["payment_terms"] is None]
    inconsistent = [f for f in gold.values() if f["consistent"] is False]
    assert absent_po and absent_terms and inconsistent


def test_stale_pdfs_do_not_survive_a_regeneration(tmp_path):
    build_corpus(tmp_path, per_variant=3)
    build_corpus(tmp_path, per_variant=1)
    assert len(list(tmp_path.glob("*.pdf"))) == len(VARIANTS)
    gold = json.loads((tmp_path / "gold.json").read_text(encoding="utf-8"))
    assert {p.stem for p in tmp_path.glob("*.pdf")} == set(gold)


def test_pdf_roundtrip_of_special_characters(tmp_path):
    from synth.pdfwrite import write_pdf
    write_pdf(tmp_path / "x.pdf", [(60, 700, 10, "Total: €1,234.56 (net) \\ 100%")])
    text = "\n".join(pdf_lines(tmp_path / "x.pdf"))
    assert "€1,234.56" in text
    assert "\\" in text and "(" in text and "%" in text
