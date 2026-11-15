import os
import tempfile
import sys
from pathlib import Path

import pytest

# Use an in-memory DB and no on-disk embedding cache side effects before app import.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
# Never touch the real FAISS index from tests.
os.environ["INDEX_DIR"] = tempfile.mkdtemp(prefix="skillmatch-index-")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))


@pytest.fixture(scope="session", autouse=True)
def _isolate_file_stores(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Resume PDFs and import uploads go to temp dirs, never backend/data/."""
    import app.campus.bulk_import as bi
    import app.services.resume_store as rs

    rs.STORE = tmp_path_factory.mktemp("resumes")
    bi.IMPORT_DIR = tmp_path_factory.mktemp("imports")
    bi.RUN_INLINE = True  # shared in-memory SQLite connection: no background thread in tests


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> None:
    import app.models  # noqa: F401
    from app.core.db import Base, engine

    Base.metadata.create_all(engine)


@pytest.fixture(scope="session")
def sample_pdfs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    import make_sample_resumes as m

    out = tmp_path_factory.mktemp("samples")
    m.OUT = out
    return {name: m.build(name, spec) for name, spec in m.RESUMES.items()}


@pytest.fixture(scope="session")
def phrase_extractor():  # type: ignore[no-untyped-def]
    """Extractor without embeddings: fast, no model download."""
    from app.core.nlp import get_nlp
    from app.skills.extractor import SkillExtractor
    from app.skills.taxonomy import get_taxonomy

    return SkillExtractor(get_taxonomy(), get_nlp(), encoder=None)


# ---------------- auth helpers ----------------
_counter = {"n": 0}


def make_client(role: str = "job_seeker", admin: bool = False, **extra):  # type: ignore[no-untyped-def]
    """Register a fresh user; return (TestClient carrying its bearer token, user dict)."""
    from fastapi.testclient import TestClient

    from app.core.db import SessionLocal
    from app.main import app
    from app.models.user import User

    _counter["n"] += 1
    n = _counter["n"]
    body = {"email": f"user{n}@test.example", "password": "passw0rd!", "full_name": f"User {n}", "role": role, **extra}
    if role == "tpo" and "institution_name" not in body:
        body["institution_name"] = f"Test College {n}"
    r = TestClient(app).post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    tok = r.json()
    if admin:
        with SessionLocal() as db:
            u = db.get(User, tok["user"]["id"])
            u.is_admin = True  # type: ignore[union-attr]
            db.commit()
    client = TestClient(app, headers={"Authorization": f"Bearer {tok['access_token']}"})
    return client, tok["user"]


@pytest.fixture()
def seeker():  # type: ignore[no-untyped-def]
    return make_client("job_seeker")[0]


@pytest.fixture()
def admin_client():  # type: ignore[no-untyped-def]
    return make_client("job_seeker", admin=True)[0]
