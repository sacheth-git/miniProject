import os
import sys
from pathlib import Path

import pytest

# Use an in-memory DB and no on-disk embedding cache side effects before app import.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))


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
