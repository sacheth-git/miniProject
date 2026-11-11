"""Skill extraction: spaCy PhraseMatcher over the taxonomy plus embedding normalisation.

Pipeline per section:
1. Phrase matching. Case-insensitive for normal surface forms; exact-case plus a
   list-context check for ambiguous forms ("Go", "R", "Swift", "Spring", ...).
2. Embedding normalisation. Noun chunks that no phrase matched are embedded and
   mapped to the nearest taxonomy skill if cosine >= threshold
   ("machine learning model development" -> Machine Learning).
Each skill keeps a confidence and the evidence sentence from the resume.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
from spacy.language import Language
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span
from spacy.util import filter_spans

from app.core.logging import get_logger
from app.core.nlp import get_nlp
from app.embeddings.encoder import Encoder
from app.skills.taxonomy import Skill, Taxonomy, get_taxonomy, normalize_form

log = get_logger(__name__)

# Surface forms that are also common English words, names or other-field terms.
AMBIGUOUS_FORMS: frozenset[str] = frozenset(
    {
        "go", "swift", "rust", "ruby", "julia", "dart", "scheme", "less", "spark", "chef",
        "puppet", "ray", "beam", "glue", "athena", "unity", "sketch", "inventor", "eagle",
        "cadence", "oracle", "arm", "pic", "spice", "fiber", "remix", "bun", "koa", "hapi",
        "gin", "expo", "chroma", "prisma", "lightning", "notion", "slack", "apex", "nexus",
        "react", "angular", "spring", "airflow", "excel", "lean", "storm", "pig", "hive",
        "processing", "elixir", "crystal", "solid", "redux", "jest", "mocha", "keras",
        "flutter", "ionic", "maven", "helm", "vault", "consul", "packer", "polars", "dash",
        "streamlit", "seaborn", "pandas", "scala", "perl", "lua", "kotlin", "terraform",
        "word", "teams", "access", "outlook", "dynamics", "proteus", "eclipse", "atom",
        "lambda", "logo", "basic", "pascal", "ada", "simula", "cobra", "sage", "matlab",
    }
)
# Generic single words: accepted only in the skills/summary sections.
GENERIC_FORMS: frozenset[str] = frozenset(
    {
        "testing", "reporting", "monitoring", "documentation", "collaboration", "automation",
        "routing", "switching", "indexing", "normalization", "caching", "scalability",
        "probability", "optimization", "classification", "regression", "clustering",
        "forecasting", "manufacturing", "embedded", "cloud", "networking", "debugging",
        "prototyping", "wireframes", "leadership", "teamwork", "communication", "accounting",
        "statistics", "forensics", "firmware", "sensors", "instrumentation", "lean",
        "research", "design", "analysis", "programming", "development", "management",
        "mathematics", "physics", "electricity", "electronics", "mechanics", "robotics",
        "ai", "ml", "os", "qa", "bi", "ui", "ux", "kanban", "reporting", "presentation",
        "mentoring", "adaptability", "negotiation", "surveying", "automotive", "security",
        "algorithms", "encryption", "firewall", "oop", "rest",
        # degree / discipline names: usually describe the degree, not a skill
        "computer science", "information technology", "mechanical engineering",
        "electrical engineering", "civil engineering", "electronics engineering",
        "chemical engineering", "software engineering", "computer engineering",
        "electronics and communication", "electrical and electronics engineering",
    }
)
LIST_SEPS = {",", "|", "/", ";", "•", "·", "&", "+"}
SECTION_CONFIDENCE = {
    "skills": 0.95,
    "experience": 0.9,
    "projects": 0.9,
    "certifications": 0.88,
    "summary": 0.85,
    "education": 0.8,
    "achievements": 0.8,
    "publications": 0.8,
    "header": 0.7,
}
EVIDENCE_PRIORITY = ["experience", "projects", "skills", "certifications", "summary"]
EMBED_SECTIONS = ("experience", "projects", "summary")
_PREP_RE = re.compile(r"[ \t]*([,|;()•·])[ \t]*")  # never eat newlines
_SLASH_RE = re.compile(r"(?<=\w)/(?=\w)")
# PDF soft wraps: a line that does not end a sentence, followed by a lowercase start.
_SOFT_WRAP_RE = re.compile(r"(?<=[^\s.:;!?])[ \t]*\n[ \t]*(?=[a-z(])")


def prep_text(text: str) -> str:
    """Normalise separators identically for patterns and documents."""
    text = _SOFT_WRAP_RE.sub(" ", text)
    text = _SLASH_RE.sub(" / ", text)
    return _PREP_RE.sub(r" \1 ", text)


def is_ambiguous(form: str) -> bool:
    f = normalize_form(form)
    return len(f) <= 2 or f in AMBIGUOUS_FORMS


@dataclass
class ExtractedSkill:
    skill_id: str
    name: str
    esco_uri: str | None
    confidence: float
    evidence: str
    section: str
    method: str  # phrase | embedding | user
    mentions: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SkillExtractor:
    def __init__(
        self,
        taxonomy: Taxonomy,
        nlp: Language,
        encoder: Encoder | None = None,
        embed_threshold: float = 0.80,
    ) -> None:
        self.tax = taxonomy
        self.nlp = nlp
        self.encoder = encoder
        self.embed_threshold = embed_threshold
        self._generic_ids = {
            s.id
            for s in taxonomy.skills
            if normalize_form(s.name) in GENERIC_FORMS
            or (s.source == "esco" and len(s.name.split()) == 1)
        }
        self._lower = PhraseMatcher(nlp.vocab, attr="LOWER")
        self._exact = PhraseMatcher(nlp.vocab, attr="ORTH")
        lower_pats: dict[str, list[Doc]] = {}
        exact_pats: dict[str, list[Doc]] = {}
        for s in taxonomy.skills:
            for form in s.forms:
                if is_ambiguous(form):
                    # Lowercase variants are never matched for ambiguous forms ("go", "arm").
                    variants = {form.upper(), form.title()} if form.islower() else {form, form.upper()}
                    exact_pats.setdefault(s.id, []).extend(nlp.make_doc(prep_text(v)) for v in variants)
                else:
                    lower_pats.setdefault(s.id, []).append(nlp.make_doc(prep_text(form)))
        for sid, pats in lower_pats.items():
            self._lower.add(sid, pats)
        for sid, pats in exact_pats.items():
            self._exact.add(sid, pats)
        self._skill_matrix: np.ndarray | None = None

    # ---------- phrase matching ----------

    def _accept_ambiguous(self, doc: Doc, span: Span, section: str) -> bool:
        nxt = doc[span.end] if span.end < len(doc) else None
        prv = doc[span.start - 1] if span.start > 0 else None
        line_start = span.start
        while line_start > 0 and "\n" not in doc[line_start - 1].text_with_ws:
            line_start -= 1
        line_end = span.end
        while line_end < len(doc) and "\n" not in doc[line_end - 1].text_with_ws:
            line_end += 1
        line = doc[line_start:line_end]
        n_seps = sum(1 for t in line if t.text in LIST_SEPS)
        followed_by_word = (
            nxt is not None
            and "\n" not in span[-1].text_with_ws
            and nxt.is_alpha
            and nxt.text.islower()
            and nxt.lower_ not in {"and", "or"}
        )
        if followed_by_word:
            return False
        adjacent_sep = (prv is not None and prv.text in LIST_SEPS) or (nxt is not None and nxt.text in LIST_SEPS)
        if section == "skills":
            return n_seps >= 1 or len(line) <= 4 or adjacent_sep
        return adjacent_sep and n_seps >= 2

    def _phrase_spans(self, doc: Doc, section: str) -> list[tuple[Span, bool]]:
        found: list[tuple[Span, bool]] = []
        for match_id, start, end in self._lower(doc):
            found.append((Span(doc, start, end, label=match_id), False))
        for match_id, start, end in self._exact(doc):
            found.append((Span(doc, start, end, label=match_id), True))
        ambiguous = {(s.start, s.end, s.label) for s, amb in found if amb}
        kept = filter_spans([s for s, _ in found])
        out: list[tuple[Span, bool]] = []
        for span in kept:
            amb = (span.start, span.end, span.label) in ambiguous
            if amb and not self._accept_ambiguous(doc, span, section):
                continue
            sid = self.nlp.vocab.strings[span.label]
            generic = sid in self._generic_ids or normalize_form(span.text) in GENERIC_FORMS
            if generic and section != "skills":
                continue
            out.append((span, amb))
        return out

    @staticmethod
    def _evidence(doc: Doc, span: Span, section: str) -> str:
        """The resume line (bullet) holding the match; soft wraps are already joined.

        spaCy sentences are not used: bullets without full stops merge into one
        'sentence' and would quote the wrong bullet.
        """
        start, end = span.start, span.end
        while start > 0 and "\n" not in doc[start - 1].text_with_ws:
            start -= 1
        while end < len(doc) and "\n" not in doc[end - 1].text_with_ws:
            end += 1
        text = doc[start:end].text
        text = re.sub(r"\s+([,|;)])", r"\1", re.sub(r"\s+", " ", text)).replace("( ", "(").strip()
        return text[:280]

    # ---------- embedding normalisation ----------

    def _matrix(self) -> np.ndarray:
        if self._skill_matrix is None:
            assert self.encoder is not None
            self._skill_matrix = self.encoder.encode([s.name for s in self.tax.skills])
        return self._skill_matrix

    def _embedding_matches(self, doc: Doc, covered: set[int]) -> list[tuple[Skill, float, Span]]:
        if self.encoder is None:
            return []
        chunks: list[Span] = []
        for nc in doc.noun_chunks:
            toks = [t for t in nc if not (t.is_stop or t.is_punct or t.pos_ in {"DET", "PRON", "NUM"})]
            if not (2 <= len(toks) <= 6):
                continue
            if any(t.i in covered for t in toks):
                continue
            chunks.append(doc[toks[0].i : toks[-1].i + 1])
        if not chunks:
            return []
        vecs = self.encoder.encode([c.text.lower() for c in chunks])
        sims = vecs @ self._matrix().T
        best = sims.argmax(axis=1)
        out: list[tuple[Skill, float, Span]] = []
        for i, chunk in enumerate(chunks):
            score = float(sims[i, best[i]])
            skill = self.tax.skills[int(best[i])]
            # Generic targets (disciplines, plain words) are too easy to hit by paraphrase.
            if score >= self.embed_threshold and skill.id not in self._generic_ids:
                out.append((skill, score, chunk))
        return out

    # ---------- public API ----------

    def extract(self, sections: dict[str, str], use_embeddings: bool = True) -> list[ExtractedSkill]:
        results: dict[str, ExtractedSkill] = {}
        evidence_rank: dict[str, int] = {}

        def add(skill: Skill, conf: float, evidence: str, section: str, method: str) -> None:
            rank = EVIDENCE_PRIORITY.index(section) if section in EVIDENCE_PRIORITY else 99
            cur = results.get(skill.id)
            if cur is None:
                results[skill.id] = ExtractedSkill(
                    skill.id, skill.name, skill.esco_uri, round(conf, 3), evidence, section, method
                )
                evidence_rank[skill.id] = rank
                return
            cur.mentions += 1
            cur.confidence = round(min(0.99, max(cur.confidence, conf) + 0.02), 3)
            if method == "phrase" and cur.method == "embedding":
                cur.method = "phrase"
            if rank < evidence_rank[skill.id]:
                cur.evidence, cur.section = evidence, section
                evidence_rank[skill.id] = rank

        for section, text in sections.items():
            if not text.strip() or section in ("interests", "languages_spoken"):
                continue
            doc = self.nlp(prep_text(text))
            base = SECTION_CONFIDENCE.get(section, 0.8)
            covered: set[int] = set()
            for span, amb in self._phrase_spans(doc, section):
                sid = self.nlp.vocab.strings[span.label]
                skill = self.tax.get(sid)
                if skill is None:
                    continue
                covered.update(range(span.start, span.end))
                add(skill, base - (0.15 if amb else 0.0), self._evidence(doc, span, section), section, "phrase")
            if use_embeddings and section in EMBED_SECTIONS:
                for skill, score, chunk in self._embedding_matches(doc, covered):
                    add(skill, score * 0.9, self._evidence(doc, chunk, section), section, "embedding")

        return sorted(results.values(), key=lambda s: (-s.confidence, s.name.lower()))

    def extract_text(self, text: str, section: str = "experience", use_embeddings: bool = False) -> list[ExtractedSkill]:
        return self.extract({section: text}, use_embeddings=use_embeddings)


@lru_cache
def get_extractor() -> SkillExtractor:
    from app.embeddings.encoder import get_encoder

    return SkillExtractor(get_taxonomy(), get_nlp(), get_encoder())
