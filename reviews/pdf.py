from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 88) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    rows = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if len(trial) > width:
            rows.append(current)
            current = word
        else:
            current = trial
    rows.append(current)
    return rows


def write_simple_pdf(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap(line))
    lines = wrapped[:28]
    ops = [
        "BT",
        "/F1 18 Tf",
        "50 740 Td",
        f"({_escape(title)}) Tj",
        "/F1 12 Tf",
    ]
    for line in lines:
        ops.append("0 -18 Td")
        ops.append(f"({_escape(line)}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", "replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        ),
        b"4 0 obj << /Length "
        + str(len(stream)).encode("ascii")
        + b" >> stream\n"
        + stream
        + b"\nendstream\nendobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

    header = b"%PDF-1.4\n"
    body = b""
    offsets = []
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        body += obj
        pos += len(obj)

    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode("ascii")
    trailer = (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{pos}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(header + body + xref + trailer)


def _font(size: int):
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def make_pipeline_figure(path: Path, title: str, stages: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1100
    height = 280
    image = Image.new("RGB", (width, height), "#f4f7fa")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 48), fill="#1b3a4b")
    draw.text((24, 12), title, fill="white", font=_font(22))
    box_w = 180
    gap = 36
    start_x = 30
    y = 110
    for index, stage in enumerate(stages):
        x = start_x + index * (box_w + gap)
        draw.rounded_rectangle((x, y, x + box_w, y + 90), radius=8, fill="#24485c")
        draw.text((x + 12, y + 32), stage, fill="white", font=_font(16))
        if index < len(stages) - 1:
            ax = x + box_w + 6
            draw.polygon(
                [(ax, y + 38), (ax + 22, y + 45), (ax, y + 52)],
                fill="#f0b429",
            )
    image.save(path, "JPEG", quality=88)
    return path


def make_chart_figure(path: Path, title: str, bars: list[tuple[str, int]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1100
    height = 320
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 48), fill="#24485c")
    draw.text((24, 12), title, fill="white", font=_font(22))
    max_value = max(value for _label, value in bars) or 1
    left = 40
    base = 280
    bar_w = 160
    for index, (label, value) in enumerate(bars):
        x = left + index * 200
        h = int(180 * (value / max_value))
        draw.rectangle((x, base - h, x + bar_w, base), fill="#2b6cb0")
        draw.text((x, base + 8), f"{label}  {value}", fill="#222222", font=_font(16))
    image.save(path, "JPEG", quality=88)
    return path


def write_illustrated_pdf(path: Path, title: str, paragraphs: list[str], figures: list[Path]) -> None:
    """Build a multi-page PDF with text plus embedded JPEG figures."""
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((48, 56), title, fontsize=18, fontname="helv")
    y = 88
    for paragraph in paragraphs:
        leftover = page.insert_textbox(
            pymupdf.Rect(48, y, 547, y + 70),
            paragraph,
            fontsize=11,
            fontname="helv",
        )
        y += 18 + max(leftover, 36)
        if y > 760:
            page = doc.new_page(width=595, height=842)
            y = 56
    for figure in figures:
        page = doc.new_page(width=595, height=842)
        page.insert_text((48, 48), "Figure", fontsize=12, fontname="helv")
        page.insert_image(pymupdf.Rect(40, 72, 555, 360), filename=str(figure))
    doc.save(path)
    doc.close()
