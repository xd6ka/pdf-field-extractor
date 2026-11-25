"""Evaluate extraction against gold: field-level P/R/F1, hallucinations, grounding.

Every number is computed from the same predicate: after normalisation, does the
predicted value equal the gold value exactly? That keeps the report from grading
itself on "close enough" when the downstream use is a database row.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.extract import extract  # noqa: E402
from src.schema import FIELD_ORDER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def evaluate_doc(doc_path: Path, gold_doc: dict, *, model: str, repairs: int) -> dict:
    result = extract(doc_path, model=model, repairs=repairs)
    per_field = {}
    for field in FIELD_ORDER:
        expected = gold_doc.get(field)
        got = result["values"][field]
        per_field[field] = {
            "expected": expected,
            "got": got,
            "correct": got == expected,
            "absent_gold": expected is None,
            "predicted": got is not None,
        }
    return {
        "document": doc_path.name,
        "variant": gold_doc.get("variant"),
        "values": result["values"],
        "fields": per_field,
        "errors": result["errors"],
        "ungrounded": result["ungrounded"],
        "arithmetic": result["arithmetic"],
        "seconds": result["seconds"],
        "calls": result["calls"],
        "trace": result["trace"],
    }


def summarize(rows: list[dict], gold: dict, seconds: float) -> dict:
    field_stats = {}
    for field in FIELD_ORDER:
        tp = fp = fn = tn = 0
        for row in rows:
            cell = row["fields"][field]
            if cell["absent_gold"]:
                if cell["predicted"]:
                    fp += 1
                else:
                    tn += 1
            elif cell["correct"]:
                tp += 1
            else:
                fn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * tp / (2 * tp + fp + fn)) if tp + fp + fn else None
        field_stats[field] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": None if precision is None else round(precision, 3),
            "recall": None if recall is None else round(recall, 3),
            "f1": None if f1 is None else round(f1, 3),
            "support": tp + fn,
        }

    micro_tp = sum(s["tp"] for s in field_stats.values())
    micro_fp = sum(s["fp"] for s in field_stats.values())
    micro_fn = sum(s["fn"] for s in field_stats.values())
    micro_f1 = 2 * micro_tp / (2 * micro_tp + micro_fp + micro_fn) if micro_tp else 0.0

    docs_exact = sum(1 for row in rows if all(cell["correct"] for cell in row["fields"].values()))
    absent_cells = sum(s["fp"] + s["tn"] for s in field_stats.values())
    hallucinations = sum(s["fp"] for s in field_stats.values())
    predicted = sum(1 for row in rows for cell in row["fields"].values() if cell["predicted"])
    ungrounded = sum(len(row["ungrounded"]) for row in rows)
    schema_clean = sum(1 for row in rows if not row["errors"])
    inconsistent = [row for row in rows if gold[row["document"][:-4]].get("consistent") is False]
    consistent = [row for row in rows if gold[row["document"][:-4]].get("consistent") is not False]
    detected = sum(1 for row in inconsistent if row["arithmetic"]["ok"] is False)
    false_alarms = sum(1 for row in consistent if row["arithmetic"]["ok"] is False)
    latencies = [row["seconds"] for row in rows]

    return {
        "documents": len(rows),
        "fields": field_stats,
        "micro": {
            "tp": micro_tp, "fp": micro_fp, "fn": micro_fn,
            "precision": round(micro_tp / (micro_tp + micro_fp), 3) if micro_tp + micro_fp else None,
            "recall": round(micro_tp / (micro_tp + micro_fn), 3) if micro_tp + micro_fn else None,
            "f1": round(micro_f1, 3),
        },
        "doc_exact_match": docs_exact,
        "doc_exact_rate": round(docs_exact / len(rows), 3),
        "hallucination_rate": round(hallucinations / absent_cells, 3) if absent_cells else None,
        "absent_cells": absent_cells,
        "grounded_rate": round((predicted - ungrounded) / predicted, 3) if predicted else None,
        "ungrounded_values": ungrounded,
        "schema_clean_rate": round(schema_clean / len(rows), 3),
        "arithmetic": {
            "inconsistent_docs": len(inconsistent),
            "detected": detected,
            "false_alarms": false_alarms,
            "consistent_docs": len(consistent),
        },
        "mean_seconds": round(statistics.mean(latencies), 2),
        "median_seconds": round(statistics.median(latencies), 2),
        "mean_calls": round(statistics.mean(row["calls"] for row in rows), 2),
        "wall_seconds": round(seconds, 1),
        "model": config.MODEL,
        "max_repairs": config.MAX_REPAIRS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data" / "corpus"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--repairs", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(ROOT / "eval" / "reports" / "extract.json"))
    args = parser.parse_args()

    if args.model:
        config.MODEL = args.model
    if args.repairs is not None:
        config.MAX_REPAIRS = args.repairs
    corpus = Path(args.corpus)
    gold = json.loads((corpus / "gold.json").read_text(encoding="utf-8"))
    docs = sorted(corpus.glob("*.pdf"))
    if args.limit:
        docs = docs[: args.limit]

    started = time.perf_counter()
    rows = []
    for doc in docs:
        row = evaluate_doc(doc, gold[doc.stem], model=config.MODEL, repairs=config.MAX_REPAIRS)
        rows.append(row)
        wrong = [f for f, cell in row["fields"].items() if not cell["correct"]]
        print(f"{'OK  ' if not wrong else 'FAIL'} {doc.stem:16} {row['seconds']:5.1f}s "
              f"calls={row['calls']} wrong={','.join(wrong) or '-'}")
    summary = summarize(rows, gold, time.perf_counter() - started)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "rows": [{k: v for k, v in r.items() if k != "trace"} for r in rows],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== summary ===")
    for key in ("documents", "doc_exact_match", "doc_exact_rate", "hallucination_rate",
                "grounded_rate", "schema_clean_rate", "mean_seconds", "median_seconds", "mean_calls",
                "wall_seconds"):
        print(f"{key}: {summary[key]}")
    print("micro:", summary["micro"])
    print("arithmetic:", summary["arithmetic"])
    print("\nper field:")
    for field, stats in summary["fields"].items():
        print(f"  {field:15} P={stats['precision']} R={stats['recall']} F1={stats['f1']} support={stats['support']}")
    print("\nreport:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
