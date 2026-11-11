from datetime import date

import fitz
import pytest

from app.parsing.pdf_parser import Block, PDFParseError, extract_text, order_blocks
from app.parsing.profile import date_ranges, education_level, years_of_experience
from app.parsing.section_detector import detect_sections


def test_order_blocks_two_column() -> None:
    blocks = [
        Block(30, 20, 560, 40, "NAME HEADER", 0),
        Block(320, 60, 560, 100, "right-1 experience text " * 3, 0),
        Block(30, 60, 200, 100, "left-1 skills", 0),
        Block(30, 110, 200, 150, "left-2 education", 0),
        Block(320, 110, 560, 150, "right-2 projects text " * 3, 0),
    ]
    ordered, two = order_blocks(blocks, 595)
    assert two is True
    assert [b.text.split()[0] for b in ordered] == ["NAME", "left-1", "left-2", "right-1", "right-2"]


def test_order_blocks_single_column() -> None:
    blocks = [Block(30, 100, 560, 120, "second", 0), Block(30, 20, 560, 40, "first", 0)]
    ordered, two = order_blocks(blocks, 595)
    assert two is False
    assert [b.text for b in ordered] == ["first", "second"]


def test_rejects_non_pdf() -> None:
    with pytest.raises(PDFParseError):
        extract_text(b"hello world")


def test_rejects_empty_pdf() -> None:
    doc = fitz.open()
    doc.new_page()
    with pytest.raises(PDFParseError):
        extract_text(doc.tobytes())


def test_all_samples_parse(sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    for name, path in sample_pdfs.items():
        parsed = extract_text(path.read_bytes())
        assert len(parsed.text) > 300, name
        sections = detect_sections(parsed.text)
        assert "experience" in sections, name
        assert "education" in sections, name
        assert "skills" in sections, name


def test_two_column_sample_keeps_columns_apart(sample_pdfs) -> None:  # type: ignore[no-untyped-def]
    parsed = extract_text(sample_pdfs["priya_fullstack.pdf"].read_bytes())
    assert parsed.two_column_pages == [0]
    sections = detect_sections(parsed.text)
    # Sidebar skills must not leak into experience, and experience must be intact.
    assert "Jest" in sections["skills"]
    assert "BrightCart" in sections["experience"]
    assert "BrightCart" not in sections["skills"]


def test_section_aliases_and_inline_skills() -> None:
    text = "Jane\nCAREER OBJECTIVE\nBuild things\nSkills: Python, SQL\nWork History\nDid work\nAcademic Projects\nA project"
    s = detect_sections(text)
    assert s["summary"] == "Build things"
    assert s["skills"] == "Python, SQL"
    assert s["experience"] == "Did work"
    assert s["projects"] == "A project"
    assert s["header"] == "Jane"


def test_years_of_experience_merges_overlaps() -> None:
    text = "Engineer (Jan 2020 - Dec 2021)\nIntern 06/2021 - 08/2021\nLead Mar 2022 - Present"
    today = date(2024, 2, 15)
    assert len(date_ranges(text, today)) == 3
    # Jan 2020..Dec 2021 = 24 months, Mar 2022..Feb 2024 = 24 months
    assert years_of_experience(text, today) == 4.0


def test_years_ignores_reversed_and_future() -> None:
    assert years_of_experience("2025 - 2020", date(2024, 1, 1)) == 0.0
    assert years_of_experience("no dates here") == 0.0


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Ph.D. in Computer Science", "phd"),
        ("M.Tech in VLSI", "masters"),
        ("MBA, 2020", "masters"),
        ("B.Tech in CSE", "bachelors"),
        ("Bachelor of Engineering", "bachelors"),
        ("Diploma in Mechanical", "diploma"),
        ("12th (PUC), 88%", "higher_secondary"),
        ("Skills: MS Excel", "unknown"),
    ],
)
def test_education_level(text: str, label: str) -> None:
    assert education_level(text)[0] == label
