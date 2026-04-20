from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixtures = root / "fixtures"
    core_fixtures = fixtures / "core"
    fixtures.mkdir(parents=True, exist_ok=True)
    core_fixtures.mkdir(parents=True, exist_ok=True)

    out_path = core_fixtures / "sample.pdf"

    doc = fitz.open()
    page = doc.new_page()

    text = (
        "Interview Notes - Example\n\n"
        "Participant: Alex\n"
        "Date: 2026-04-01\n\n"
        "Alex said onboarding felt confusing at first because the instructions were spread across multiple pages.\n"
        "They expected a single checklist.\n\n"
        "They liked the search feature once they found it, but they didn’t notice the filter controls.\n\n"
        "Quote: \"I kept thinking I missed a step.\"\n\n"
        "Suggested improvement: show progress (Step 1 of 3) and a clear Continue button.\n"
    )

    page.insert_text((72, 72), text, fontsize=11)
    doc.save(out_path)
    doc.close()

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
