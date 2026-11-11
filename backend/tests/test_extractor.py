from pathlib import Path

import pytest
import yaml

from app.skills.extractor import is_ambiguous, prep_text
from app.skills.taxonomy import get_taxonomy

GOLD = yaml.safe_load((Path(__file__).parent / "data" / "sample_gold.yaml").read_text(encoding="utf-8"))


def names(skills) -> set[str]:  # type: ignore[no-untyped-def]
    return {s.name for s in skills}


def test_taxonomy_size_and_aliases() -> None:
    tax = get_taxonomy()
    assert len(tax) >= 1000
    assert tax.lookup("ML").name == "Machine Learning"  # type: ignore[union-attr]
    assert tax.lookup("torch").name == "PyTorch"  # type: ignore[union-attr]
    assert tax.lookup("k8s").name == "Kubernetes"  # type: ignore[union-attr]
    assert tax.resolve_or_custom("Quantum Basket Weaving").id.startswith("custom-")
    assert any(s.esco_uri for s in tax.skills), "ESCO ids should be linked"


def test_prep_text_and_ambiguity() -> None:
    assert prep_text("CI/CD,Docker") == "CI / CD , Docker"
    assert is_ambiguous("Go") and is_ambiguous("R") and not is_ambiguous("Python")


def test_aliases_map_to_canonical(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    got = names(phrase_extractor.extract_text("Skills: ML, torch, k8s, sklearn, Node.js and CI/CD", section="skills"))
    assert {"Machine Learning", "PyTorch", "Kubernetes", "scikit-learn", "Node.js", "CI/CD"} <= got


def test_ambiguous_words_need_list_context(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    prose = "I will go to the office. Spring is a lovely season and the report was swift."
    assert not names(phrase_extractor.extract_text(prose, section="experience")) & {"Go", "Spring", "Swift"}
    listed = "Languages: Go, Rust, R, C, Swift"
    assert {"Go", "Rust", "R", "C", "Swift"} <= names(phrase_extractor.extract_text(listed, section="skills"))


def test_generic_words_only_in_skills_section(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    assert "Monitoring" not in names(phrase_extractor.extract_text("Monitoring of staff.", section="experience"))
    assert "Monitoring" in names(phrase_extractor.extract_text("Monitoring, Docker", section="skills"))


def test_longest_match_wins(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    got = names(phrase_extractor.extract_text("Built services with Spring Boot and Regression Testing.", section="experience"))
    assert "Spring Boot" in got and "Regression Testing" in got
    assert "Spring" not in got


def test_evidence_and_confidence(phrase_extractor) -> None:  # type: ignore[no-untyped-def]
    skills = phrase_extractor.extract(
        {"skills": "Python, Docker", "experience": "Deployed Python services on Docker in production."}
    )
    py = next(s for s in skills if s.name == "Python")
    assert py.section == "experience"  # experience evidence preferred over skills list
    assert "Deployed Python services" in py.evidence
    assert py.mentions == 2
    assert 0.9 <= py.confidence <= 0.99


@pytest.fixture(scope="module")
def sample_results(sample_pdfs):  # type: ignore[no-untyped-def]
    from app.services.resume_pipeline import process_pdf

    return {n: process_pdf(p.read_bytes(), bias_aware=True) for n, p in sample_pdfs.items()}


def test_precision_on_hand_checked_samples(sample_results) -> None:  # type: ignore[no-untyped-def]
    """Acceptance: precision >= 0.8 over the extracted skills of the 5 sample resumes."""
    tp = fp = fn = 0
    report = []
    for name, res in sample_results.items():
        pred = {s["name"] for s in res.skills}
        gold = set(GOLD[name])
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)
        report.append(f"{name}: FP={sorted(pred - gold)} FN={sorted(gold - pred)}")
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    print("\n".join(report))
    print(f"TP={tp} FP={fp} FN={fn} precision={precision:.3f} recall={recall:.3f}")
    assert tp + fp >= 50, "need a sample of at least 50 extracted skills"
    assert precision >= 0.8
    assert recall >= 0.6


def test_embedding_normalisation_maps_paraphrase() -> None:
    from app.skills.extractor import get_extractor

    ex = get_extractor()
    got = names(ex.extract({"experience": "Led machine learning model development for fraud scoring."}))
    assert "Machine Learning" in got
