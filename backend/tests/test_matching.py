"""Scorer units, baselines, and /match, /explain, /gap end to end (fake encoder)."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.embeddings.faiss_index import JobIndex, build_index, set_index
from app.matching import baselines
from app.matching.calibration import calibration_for
from app.matching.scorer import (
    CandidateProfile,
    JobFeatures,
    Scorer,
    ScorerConfig,
    SkillSpace,
    Weights,
    education_fit,
    experience_fit,
    job_type_fit,
    location_fit,
    required_education_rank,
)
from app.models.job import Job
from app.skills.taxonomy import get_taxonomy
from tests.fakes import FakeEncoder

ENC = FakeEncoder()
W = Weights(0.4, 0.4, 0.2, 0.15)


def sk(name: str, ev: str = "") -> dict[str, str]:
    s = get_taxonomy().lookup(name)
    assert s is not None, name
    return {"skill_id": s.id, "name": s.name, "evidence": ev}


@pytest.fixture(scope="module")
def space() -> SkillSpace:
    return SkillSpace(get_taxonomy(), ENC)


def profile(space: SkillSpace, skills: list[str], text: str, years: float = 1.0, prefs: dict | None = None) -> CandidateProfile:  # type: ignore[type-arg]
    s = [sk(n, f"used {n}") for n in skills]
    v = ENC.encode([text, text])
    return CandidateProfile("c", s, space.vectors(s), v[0], [v[1]], years, 3, prefs or {})


def job(jid: str, req: list[str], pref: list[str], text: str, **kw) -> JobFeatures:  # type: ignore[no-untyped-def]
    v = ENC.encode([text])[0]
    base = dict(exp_min=None, exp_max=None, job_type="full-time", location="Bengaluru", country="India",
                remote=False, description=text)
    base.update(kw)
    return JobFeatures(jid, jid, [sk(n, f"needs {n}") for n in req], [sk(n) for n in pref], doc_vec=v, resp_vec=v, **base)  # type: ignore[arg-type]


def test_calibration() -> None:
    bge = calibration_for("BAAI/bge-small-en-v1.5")
    assert float(bge.skill(0.618)) == 0.0  # unrelated pair -> 0
    assert 0.5 < float(bge.skill(0.836)) < 0.6  # near-equivalent -> partial credit
    assert float(bge.doc(0.80)) == pytest.approx(1.0) and float(bge.doc(0.60)) == 0.0
    assert calibration_for("all-MiniLM-L6-v2").skill_floor < bge.skill_floor
    assert calibration_for("finetuned") == bge


def test_skill_score_weights_and_penalty(space: SkillSpace) -> None:
    sc = Scorer(space, calibration_for("x"), W, ScorerConfig(skill_shrinkage=False))  # exact arithmetic
    cand = profile(space, ["Python", "PyTorch"], "python pytorch models")
    full = sc.score(cand, job("a", ["Python", "PyTorch"], [], "python pytorch models"), {})
    assert full.skill == pytest.approx(1.0) and full.penalty == 0.0 and not full.missing_required
    half = sc.score(cand, job("b", ["Python", "Kubernetes"], [], "python pytorch models"), {})
    assert half.penalty == 0.5 and [m.name for m in half.missing_required] == ["Kubernetes"]
    assert half.score < full.score
    # A missing *preferred* skill costs half as much and adds no penalty.
    pref = sc.score(cand, job("c", ["Python"], ["Kubernetes"], "python pytorch models"), {})
    assert pref.penalty == 0.0 and pref.skill == pytest.approx(1 / 1.5)
    # IDF: a rare missing skill hurts more than a common one.
    idf = {sk("Kubernetes")["skill_id"]: 1.5, sk("Python")["skill_id"]: 0.5}
    assert sc.score(cand, job("d", ["Python", "Kubernetes"], [], "x"), idf).skill == pytest.approx(0.25)
    m = full.matched[0]
    assert m.resume_evidence.startswith("used ") and m.jd_evidence.startswith("needs ")


def test_ablation_switches(space: SkillSpace) -> None:
    cand = profile(space, ["Python"], "python")
    j = job("a", ["Python", "Docker"], ["Git"], "python", exp_min=5.0)

    def run(**kw):  # type: ignore[no-untyped-def]
        return Scorer(space, calibration_for("x"), W, ScorerConfig(skill_shrinkage=False, **kw)).score(cand, j, {})

    base, no_ctx, no_pen = run(), run(use_context=False), run(use_penalty=False)
    flat, hard = run(use_type_weights=False, use_idf=False), run(soft_skill_match=False)
    assert no_pen.score > base.score
    assert no_ctx.score != base.score
    assert flat.skill == pytest.approx(1 / 3) and base.skill == pytest.approx(1 / 2.5)
    assert hard.skill == pytest.approx(base.skill)  # exact skill present either way


def test_shrinkage_for_thin_and_empty_jds(space: SkillSpace) -> None:
    sc = Scorer(space, calibration_for("x"), W)
    cand = profile(space, ["Python"], "python")
    empty = sc.score(cand, job("s", [], [], "sales targets"), {})
    assert empty.skill == pytest.approx(0.5) and empty.penalty == 0.0
    thin = sc.score(cand, job("t", ["Python"], [], "python"), {})
    rich = sc.score(profile(space, ["Python", "SQL", "Docker", "Git"], "python"), job("r", ["Python", "SQL", "Docker", "Git"], [], "python"), {})
    assert thin.skill == pytest.approx((1 + 1) / 3)  # one matched skill is not 100%
    assert rich.skill > thin.skill  # more evidence, more confidence


def test_with_extra_skill_raises_score(space: SkillSpace) -> None:
    sc = Scorer(space, calibration_for("x"), W)
    b = sc.score(profile(space, ["Python"], "python"), job("a", ["Python", "Docker"], [], "python"), {})
    vec = space.vectors([sk("Docker")])[0]
    assert sc.with_extra_skill(b, vec, sk("Docker")["skill_id"]) > b.score


def test_context_parts() -> None:
    assert experience_fit(1, 3, 5) == pytest.approx(1 / 3)
    assert experience_fit(10, 3, 5) == 0.0 and experience_fit(4, 3, 5) == 1.0 and experience_fit(0, None, None) == 1.0
    assert job_type_fit("internship", {"job_types": ["internship"]}, 0) == 1.0
    assert job_type_fit("full-time", {"job_types": ["internship"]}, 0) == 0.2
    assert job_type_fit("internship", {}, 3) == 0.4
    assert location_fit("Pune, India", "India", False, {"locations": ["pune"]}) == 1.0
    assert location_fit("Austin", "US", True, {"locations": ["pune"], "remote_ok": True}) == 1.0
    assert location_fit("Austin", "US", False, {"locations": ["pune"]}) == 0.2
    assert required_education_rank("Requirements\nMaster's degree in CS or related field") == 4
    assert required_education_rank("Bachelor's or Master's degree") == 3
    assert required_education_rank("Python skills") is None
    assert education_fit(3, "PhD in machine learning required degree") == pytest.approx(0.2)


def test_baselines() -> None:
    jobs = ["python machine learning pytorch", "java spring backend", "sales manager"]
    t = baselines.tfidf_scores("python pytorch deep learning", jobs)
    b = baselines.bm25_scores("python pytorch deep learning", jobs)
    assert t.argmax() == 0 and b.argmax() == 0 and b.max() == 1.0
    j = baselines.keyword_jaccard({"python", "sql"}, [{"python", "sql"}, {"java"}, set()])
    assert list(j) == [1.0, 0.0, 0.0]
    assert baselines.tfidf_scores("x", []).size == 0


# ---------------- end to end ----------------

JOBS = [
    ("ml", "Machine Learning Engineer", "Requirements\n- Python, PyTorch and machine learning\n- Deep learning for NLP\nNice to have\n- Docker, Kubernetes", "Bengaluru, India"),
    ("fe", "Frontend Developer", "Requirements\n- React, TypeScript, CSS\n- Jest testing", "Pune, India"),
    ("mech", "Mechanical Design Engineer", "Requirements\n- SolidWorks, AutoCAD, ANSYS\n- GD&T drawings", "Chennai, India"),
]


@pytest.fixture(scope="module")
def e2e(phrase_extractor, sample_pdfs):  # type: ignore[no-untyped-def]
    import app.matching.service as svc
    from app.main import app
    from app.skills.jd_skill_weighter import extract_jd_skills

    mp = pytest.MonkeyPatch()
    mp.setattr(svc, "get_encoder", lambda: ENC)
    svc.get_skill_space.cache_clear()
    mp.setattr(svc, "get_skill_space", lambda: SkillSpace(get_taxonomy(), ENC))
    for mod in ("app.matching.explain", "app.matching.gap_advisor"):
        if hasattr(__import__(mod, fromlist=["x"]), "get_encoder"):
            mp.setattr(f"{mod}.get_encoder", lambda: ENC)
    with SessionLocal() as db:
        for jid, title, desc, loc in JOBS:
            req, pref = extract_jd_skills(desc, phrase_extractor)
            db.merge(Job(id=f"e2e-{jid}", source="greenhouse", source_job_id=f"e2e:{jid}", title=title, company="Acme",
                         company_norm="acme", description=desc, responsibilities="", location=loc, country="India",
                         job_type="full-time", apply_url=f"https://example.com/{jid}",
                         apply_options=[{"publisher": "Acme", "url": f"https://example.com/{jid}", "is_direct": True}],
                         required_skills=[s.to_dict() for s in req], preferred_skills=[s.to_dict() for s in pref]))
        db.commit()
        set_index(build_index(db, ENC))
    client = TestClient(app)
    cid = client.post("/resume/upload", files={"file": ("u.pdf", sample_pdfs["uday_ml.pdf"].read_bytes(), "application/pdf")}).json()["id"]
    yield client, cid
    set_index(None)
    mp.undo()


def test_match_ranks_ml_job_first(e2e) -> None:  # type: ignore[no-untyped-def]
    client, cid = e2e
    r = client.get(f"/match/{cid}", params={"limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["job"]["id"] for it in body["items"]]
    assert ids.index("e2e-ml") < ids.index("e2e-fe") < len(ids)
    assert ids.index("e2e-ml") < ids.index("e2e-mech")
    top = next(it for it in body["items"] if it["job"]["id"] == "e2e-ml")
    assert {"Python", "PyTorch"} <= {m["name"] for m in top["matched_skills"]}
    assert 0 <= top["match_percent"] <= 100 and set(body["timings_ms"]) >= {"profile", "retrieve", "score"}


def test_match_filters_and_methods(e2e) -> None:  # type: ignore[no-untyped-def]
    client, cid = e2e
    only_pune = client.get(f"/match/{cid}", params={"location": "pune", "role": "frontend"}).json()
    assert [it["job"]["id"] for it in only_pune["items"]] == ["e2e-fe"]
    for m in baselines.METHODS:
        r = client.get(f"/match/{cid}", params={"method": m, "limit": 5})
        assert r.status_code == 200 and r.json()["method"] == m, m
    assert client.get(f"/match/{cid}", params={"method": "magic"}).status_code == 422
    assert client.get("/match/nope").status_code == 404


def test_explain_and_gap(e2e) -> None:  # type: ignore[no-untyped-def]
    client, cid = e2e
    ex = client.get(f"/match/{cid}/e2e-ml/explain").json()
    assert set(ex["contributions"]) == {"semantic", "skills", "context", "penalty"}
    assert ex["summary"].startswith("Matches ")
    w = ex["weights"]
    norm = w["alpha"] + w["beta"] + w["gamma"]
    assert ex["score"] == pytest.approx(min(1.0, max(0.0, sum(ex["contributions"].values()) / norm)), abs=1e-3)
    assert client.get(f"/match/{cid}/nope/explain").status_code == 404
    gap = client.get(f"/gap/{cid}", params={"top_n": 5}).json()
    assert gap["jobs_considered"] >= 3
    names = {g["name"] for g in gap["by_total_gain"]}
    assert names & {"Docker", "Kubernetes", "React", "TypeScript", "SolidWorks", "AutoCAD", "ANSYS", "CSS", "Jest"}
    assert all(g["message"].startswith("Learn ") for g in gap["by_total_gain"])


def test_match_without_index_is_503(e2e, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    client, cid = e2e
    import app.embeddings.faiss_index as fi
    from app.core.config import get_settings

    saved = fi.get_index()
    monkeypatch.setattr(get_settings(), "index_dir", str(tmp_path))  # empty: nothing to lazy-load
    set_index(None)
    try:
        assert client.get(f"/match/{cid}").status_code == 503
    finally:
        set_index(saved)


def test_index_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    v = ENC.encode(["a b", "c d"])
    idx = JobIndex(["x", "y"], v, v.copy(), {"python": 1.0}, "fake", 0.0)
    idx.save(tmp_path)
    back = JobIndex.load(tmp_path)
    assert back is not None and back.ids == ["x", "y"] and np.allclose(back.doc, v)
    assert back.search(v[1], 1)[0][0] == "y"
    assert back.search(v[1], 2, allowed=[0])[0][0] == "x"
    assert back.search(v[1], 2, allowed=[]) == []
