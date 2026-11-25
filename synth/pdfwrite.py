"""Minimal PDF writer: one page, one base-14 font, absolute text positions.

Why not a PDF library: the corpus has to be reproducible byte-for-byte and the
layout has to be under this project's control, because the experiments below
measure what layout does to extraction accuracy. A writer we own is one
dependency less and one degree of freedom more.
"""
from pathlib import Path

PAGE_WIDTH = 595
PAGE_HEIGHT = 842


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[tuple[float, float, float, str]]) -> bytes:
    """``lines`` is (x, y, size, text); y counts up from the bottom of the page."""
    parts = ["BT"]
    for x, y, size, text in lines:
        parts.append(f"/F1 {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_escape(text)}) Tj")
    parts.append("ET")
    # cp1252 is what WinAnsiEncoding actually is; latin-1 would turn the euro
    # sign into "?" and quietly remove a currency from the corpus.
    return ("\n".join(parts) + "\n").encode("cp1252", errors="replace")


def write_pdf(path: Path | str, lines: list[tuple[float, float, float, str]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = _content_stream(lines)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{PAGE_WIDTH} {PAGE_HEIGHT}".encode()
            + b"] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))
    return path
