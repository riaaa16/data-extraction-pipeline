from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from docx import Document


def _sample_text() -> str:
    return (
        "Interview Notes - Example\n\n"
        "Participant: Alex\n"
        "Date: 2026-04-01\n\n"
        "Alex said onboarding felt confusing at first because the instructions were spread across multiple pages.\n"
        "They expected a single checklist.\n\n"
        "They liked the search feature once they found it, but they did not notice the filter controls.\n\n"
        "Quote: \"I kept thinking I missed a step.\"\n\n"
        "Suggested improvement: show progress (Step 1 of 3) and a clear Continue button.\n"
    )


def _write_txt(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_docx(path: Path, text: str) -> None:
    doc = Document()
    for paragraph in text.split("\n\n"):
        doc.add_paragraph(paragraph)
    doc.save(path)


def _write_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixtures = root / "fixtures"
    core_fixtures = fixtures / "core"
    fixtures.mkdir(parents=True, exist_ok=True)
    core_fixtures.mkdir(parents=True, exist_ok=True)

    txt_path = core_fixtures / "sample.txt"
    docx_path = core_fixtures / "sample.docx"
    pdf_path = core_fixtures / "sample.pdf"

    text = _sample_text()
    _write_txt(txt_path, text)
    _write_docx(docx_path, text)
    _write_pdf(pdf_path, text)

    print(f"Wrote {txt_path}")
    print(f"Wrote {docx_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
