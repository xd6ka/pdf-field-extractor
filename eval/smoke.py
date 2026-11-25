"""Run the extractor on a couple of documents and print what came back."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract import extract

docs = sys.argv[1:] or ["data/corpus/plain_00.pdf", "data/corpus/columns_03.pdf"]
gold = json.loads(Path("data/corpus/gold.json").read_text(encoding="utf-8"))
for doc in docs:
    result = extract(doc)
    key = Path(doc).stem
    print("==", key)
    print("values:", json.dumps(result["values"], ensure_ascii=False))
    print("gold  :", json.dumps({k: gold[key][k] for k in gold[key] if k != "present"}, ensure_ascii=False))
    print("errors:", result["errors"], "| ungrounded:", result["ungrounded"], "| arith:", result["arithmetic"])
    print("seconds:", result["seconds"], "calls:", result["calls"])
