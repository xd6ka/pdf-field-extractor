"""Line-level evidence selection.

Every field gets a few candidate lines instead of the whole document. Two
reasons: a 3B model with twelve numbered lines and a question about one field
does better than with forty lines, and the candidate line becomes the citation
that lets the eval say "grounded" instead of "looks plausible".
"""
from .schema import SPECS


def score_line(line: str, keywords: list[str]) -> int:
    lowered = line.lower()
    hits = 0
    for keyword in keywords:
        if keyword and keyword.lower() in lowered:
            hits += 2 if len(keyword) > 4 else 1
    return hits


def evidence_for(field: str, lines: list[str], limit: int = 4) -> list[tuple[int, str]]:
    """Top lines for a field, plus the document header lines as context."""
    keywords = SPECS[field]["keywords"]
    ranked = sorted(
        ((score_line(line, keywords), index, line) for index, line in enumerate(lines)),
        key=lambda item: (-item[0], item[1]),
    )
    chosen = [(index, line) for score, index, line in ranked if score > 0][:limit]
    if not chosen:
        # No keyword anywhere: give the model the head of the document rather
        # than nothing, and let it answer null if the value truly is absent.
        chosen = [(index, line) for index, line in enumerate(lines[:limit])]
    return chosen


def document_view(lines: list[str], max_chars: int = 1400) -> str:
    body, used = [], 0
    for index, line in enumerate(lines):
        row = f"[{index}] {line}"
        if used + len(row) > max_chars:
            break
        body.append(row)
        used += len(row)
    return "\n".join(body)
