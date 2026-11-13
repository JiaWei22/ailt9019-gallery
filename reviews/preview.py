from pathlib import Path

import pymupdf
from django.conf import settings


def preview_dir(file_token: str) -> Path:
    path = Path(settings.MEDIA_ROOT) / "previews" / file_token
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_pdf_pages(pdf_path: Path, file_token: str, scale: float = 1.6) -> list[Path]:
    """Rasterize each PDF page to PNG. Reliable for image-heavy student uploads."""
    out_dir = preview_dir(file_token)
    doc = pymupdf.open(pdf_path)
    pages = []
    matrix = pymupdf.Matrix(scale, scale)
    for index, page in enumerate(doc, start=1):
        dest = out_dir / f"page-{index:02d}.png"
        if not dest.exists():
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(dest)
        pages.append(dest)
    doc.close()
    return pages


def pdf_to_positioned_html(pdf_path: Path, dest: Path) -> Path:
    """Try native PDF→HTML. Layout is often broken once figures are present."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<style>body{margin:0;background:#eef2f5} .page{position:relative;",
        "margin:16px auto;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.12)}</style>",
        "</head><body>",
    ]
    for page in doc:
        html = page.get_text("html")
        parts.append(f"<section class='page'>{html}</section>")
    parts.append("</body></html>")
    dest.write_text("".join(parts), encoding="utf-8")
    doc.close()
    return dest


def pages_as_html(page_paths: list[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    images = "\n".join(
        f"<p><img src='{path.name}' alt='Page {index}' style='width:100%;max-width:820px'></p>"
        for index, path in enumerate(page_paths, start=1)
    )
    dest.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Preview</title></head>"
        f"<body style='margin:16px;background:#eef2f5'>{images}</body></html>",
        encoding="utf-8",
    )
    return dest
