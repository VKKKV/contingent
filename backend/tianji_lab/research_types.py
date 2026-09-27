"""Bounded research snapshots, embedded atomically in the v2 run, not an archive."""

import hashlib
import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .models import Model
from .public_fetch import validate_public_url

ResearchErrorCode = Literal[
    "search_failed",
    "search_timeout",
    "search_invalid",
    "search_no_results",
    "unsafe_url",
    "unsafe_address",
    "dns_failed",
    "fetch_failed",
    "fetch_byte_limit",
    "unsupported_encoding",
    "unsupported_content",
    "redirect_limit",
    "http_denied",
    "robots_denied",
    "robots_unavailable",
    "extract_failed",
    "challenge_page",
    "research_timeout",
    "no_queries",
    "no_sources",
    "no_new_evidence",
]


class ResearchBudget(Model):
    max_queries: int = Field(default=2, ge=1, le=3)
    max_pages: int = Field(default=3, ge=1, le=5)
    max_seconds: int = Field(default=90, ge=5, le=180)
    max_response_bytes: int = Field(default=524288, ge=1024, le=1048576)
    max_total_bytes: int = Field(default=2097152, ge=1024, le=5242880)


class ResearchOptions(Model):
    mode: Literal["online", "offline"] = "online"
    budget: ResearchBudget = Field(default_factory=ResearchBudget)


class Source(Model):
    id: str = Field(pattern=r"^(?:source_[1-5]|evidence_[0-9a-f]{64})$")
    title: str = Field(max_length=300)
    url: str = Field(max_length=2048)
    resolved_url: str = Field(max_length=2048)
    retrieved_at: str = Field(min_length=1, max_length=64)
    published_at: str | None = Field(default=None, max_length=100)
    publisher: str = Field(max_length=300)
    text: str = Field(min_length=1, max_length=6000)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor: str = Field(min_length=1, max_length=80)
    origin: Literal["public_web"] = "public_web"
    # Continuation read models use stable cross-run identities. Legacy v2
    # snapshots leave these unset and retain their source_N identifiers.
    document_id: str | None = Field(default=None, pattern=r"^document_[0-9a-f]{64}$")
    version: int = Field(default=1, ge=1, le=1000)
    origin_run_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("url", "resolved_url")
    @classmethod
    def public_url(cls, value: str) -> str:
        validate_public_url(value)
        return value

    @model_validator(mode="after")
    def text_integrity(self) -> "Source":
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("source text hash mismatch")
        return self


class Passage(Model):
    id: str = Field(pattern=r"^(?:source_[1-5]_p[1-8]|evidence_[0-9a-f]{64}_p[1-8])$")
    source_id: str = Field(pattern=r"^(?:source_[1-5]|evidence_[0-9a-f]{64})$")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=800)


class SearchHit(Model):
    title: str = Field(max_length=300)
    url: str = Field(max_length=2048)
    snippet: str = Field(max_length=1000)

    @field_validator("url")
    @classmethod
    def public_url(cls, value: str) -> str:
        validate_public_url(value)
        return value


class ResearchState(Model):
    model_config = ConfigDict(frozen=False)
    status: Literal[
        "not_started",
        "running",
        "succeeded",
        "partial",
        "failed",
        "cancelled",
        "interrupted",
        "skipped",
    ] = "not_started"
    queries: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=3
    )
    # Actual query-to-source links are local to this snapshot. Continuation
    # persistence translates them to stable evidence IDs before saving.
    query_sources: dict[str, list[str]] = Field(default_factory=dict, max_length=3)
    hits: list[SearchHit] = Field(default_factory=list, max_length=15)
    sources: list[Source] = Field(default_factory=list, max_length=5)
    passages: list[Passage] = Field(default_factory=list, max_length=15)
    errors: list[ResearchErrorCode] = Field(default_factory=list, max_length=10)
    queries_used: int = Field(default=0, ge=0)
    pages_used: int = Field(default=0, ge=0)
    fetched_bytes: int = Field(default=0, ge=0)
    started_at: str | None = Field(default=None, max_length=64)
    finished_at: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def provenance(self) -> "ResearchState":
        sources = {source.id: source for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("duplicate source ID")
        if len({source.text_sha256 for source in self.sources}) != len(self.sources):
            raise ValueError("duplicate source text")
        if len({p.id for p in self.passages}) != len(self.passages):
            raise ValueError("duplicate passage ID")
        query_keys = {query.casefold() for query in self.queries}
        if any(query.casefold() not in query_keys for query in self.query_sources):
            raise ValueError("query source map contains an unknown query")
        if any(
            source_id not in sources for ids in self.query_sources.values() for source_id in ids
        ):
            raise ValueError("query source map contains an unknown source")
        if any(len(ids) != len(set(ids)) for ids in self.query_sources.values()):
            raise ValueError("duplicate query source reference")
        for passage in self.passages:
            source = sources.get(passage.source_id)
            if (
                source is None
                or not passage.id.startswith(passage.source_id + "_p")
                or passage.start >= passage.end
                or passage.end > len(source.text)
                or source.text[passage.start : passage.end] != passage.quote
            ):
                raise ValueError("passage does not match exact source slice")
        return self


class ResearchFrontierItem(Model):
    """A durable, inspectable research question/query proposal."""

    id: str = Field(pattern=r"^frontier_(?:[1-3]|c[0-9a-f]{64}_[1-3])$")
    question: str = Field(min_length=1, max_length=400)
    parent_question: str | None = Field(default=None, max_length=400)
    goal_facet: str = Field(default="", max_length=120)
    query: str = Field(min_length=1, max_length=500)
    priority: int = Field(ge=1, le=3)
    state: Literal["proposed", "attempted", "skipped", "cancelled", "interrupted"] = "proposed"
    attempts: int = Field(default=0, ge=0, le=3)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    stop_reason: str | None = Field(default=None, max_length=200)
    created_at: str = Field(min_length=1, max_length=64)
    updated_at: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def state_attempts(self) -> "ResearchFrontierItem":
        if self.state == "proposed" and self.attempts:
            raise ValueError("Proposed frontier items cannot have attempts")
        if self.state == "attempted" and self.attempts < 1:
            raise ValueError("Attempted frontier items require an attempt")
        if self.state in ("skipped", "cancelled", "interrupted") and not self.stop_reason:
            raise ValueError("Stopped frontier items require a reason")
        return self


class ResearchContinuation(Model):
    """An explicit, separately budgeted continuation of a terminal v2 run."""

    model_config = ConfigDict(frozen=False)

    schema_version: Literal["tianji.research.continuation.v1"] = "tianji.research.continuation.v1"
    id: str = Field(min_length=1, max_length=100)
    parent_id: str = Field(min_length=1, max_length=100)
    reason: Literal["manual", "critique", "gap"] = "manual"
    queries: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=3
    )
    research_options: ResearchOptions = Field(default_factory=ResearchOptions)
    status: Literal[
        "queued",
        "running",
        "succeeded",
        "partial",
        "failed",
        "skipped",
        "cancelled",
        "interrupted",
    ] = "queued"
    research: ResearchState = Field(default_factory=ResearchState)
    query_evidence: dict[str, list[str]] = Field(default_factory=dict, max_length=3)
    added_source_ids: list[str] = Field(default_factory=list, max_length=5)
    added_passage_ids: list[str] = Field(default_factory=list, max_length=15)
    frontier: list[ResearchFrontierItem] = Field(default_factory=list, max_length=3)
    stop_reason: str | None = Field(default=None, max_length=200)
    created_at: str = Field(min_length=1, max_length=64)
    finished_at: str | None = Field(default=None, max_length=64)
    error: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def references(self) -> "ResearchContinuation":
        query_keys = {query.casefold() for query in self.queries}
        if any(query.casefold() not in query_keys for query in self.query_evidence):
            raise ValueError("Continuation evidence refers to an unknown query")
        if any(len(refs) != len(set(refs)) for refs in self.query_evidence.values()):
            raise ValueError("Duplicate continuation evidence reference")
        if any(
            not re.fullmatch(r"evidence_[0-9a-f]{64}", source_id)
            for refs in self.query_evidence.values()
            for source_id in refs
        ):
            raise ValueError("Invalid continuation evidence reference")
        if len(self.added_source_ids) != len(set(self.added_source_ids)):
            raise ValueError("Duplicate continuation source identity")
        if len(self.added_passage_ids) != len(set(self.added_passage_ids)):
            raise ValueError("Duplicate continuation passage identity")
        if set(self.added_source_ids) != {source.id for source in self.research.sources}:
            raise ValueError("Continuation source index does not match research sources")
        if set(self.added_passage_ids) != {passage.id for passage in self.research.passages}:
            raise ValueError("Continuation passage index does not match selected passages")
        if len({item.id for item in self.frontier}) != len(self.frontier):
            raise ValueError("Duplicate continuation frontier identity")
        if self.status in ("cancelled", "interrupted") and not self.stop_reason:
            raise ValueError("Stopped continuation requires a reason")
        if self.status in ("succeeded", "partial", "failed", "skipped") and not self.finished_at:
            raise ValueError("Terminal continuation requires finished_at")
        return self
