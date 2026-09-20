"""Versioned public analysis objects. Validation is not empirical verification."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from .models import Model
from .vision import VisionRequest

Text = Annotated[str, Field(min_length=1, max_length=400)]
Key = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
Status = Literal["queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted"]


class AnalysisBudget(Model):
    max_calls: int = Field(default=8, ge=1, le=8)
    max_seconds: int = Field(default=900, ge=10, le=1200)
    max_output_tokens: int = Field(default=16000, ge=256, le=20000)
    max_tasks: int = Field(default=8, ge=1, le=8)
    max_revision_depth: int = Field(default=1, ge=0, le=1)


class AnalysisStart(Model):
    request: VisionRequest
    budget: AnalysisBudget = Field(default_factory=AnalysisBudget)


class Frame(Model):
    objective: Text
    criteria: list[Text] = Field(min_length=1, max_length=3)
    assumptions: list[Text] = Field(max_length=3)
    unknowns: list[Text] = Field(max_length=3)
    perspectives: list[Text] = Field(min_length=1, max_length=3)
    clarification: str = Field(default="", max_length=400)


class Claim(Model):
    id: Key
    kind: Literal["assumption", "intervention", "outcome"]
    title: Text
    detail: Text
    stakeholders: list[Text] = Field(min_length=1, max_length=3)
    signals: list[Text] = Field(max_length=3)


class Link(Model):
    source: Key
    target: Key
    kind: Literal["requires", "supports", "may-influence"]


class Strategy(Model):
    title: Text
    mechanism: Text
    claims: list[Claim] = Field(min_length=1, max_length=3)
    links: list[Link] = Field(max_length=4)
    prerequisites: list[Text] = Field(min_length=1, max_length=3)
    tradeoffs: list[Text] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def references(self):
        ids = {claim.id for claim in self.claims}
        if len(ids) != len(self.claims):
            raise ValueError("Duplicate claim IDs")
        if not any(claim.kind == "intervention" for claim in self.claims):
            raise ValueError("A strategy needs an intervention")
        if any(link.source not in ids or link.target not in ids for link in self.links):
            raise ValueError("Strategy link has an unknown reference")
        if any(link.source == link.target for link in self.links):
            raise ValueError("Self links are not supported")
        return self


class Objection(Model):
    target_claim_id: Key
    concern: Text
    test: Text


class Critique(Model):
    objections: list[Objection] = Field(max_length=4)
    revision_task_id: str = Field(default="", max_length=64)
    limitation: Text


class Synthesis(Model):
    summary: str = Field(min_length=1, max_length=1000)
    alternatives: list[Key] = Field(min_length=1, max_length=3)
    unresolved: list[Text] = Field(max_length=6)


class AnalysisTask(Model):
    model_config = ConfigDict(frozen=False)

    id: Key
    parent_id: Key | None = None
    dependencies: list[Key] = Field(default_factory=list, max_length=7)
    role: Literal["framing", "strategy", "critic", "revision", "synthesis"]
    brief: Text
    status: Status = "queued"
    model: str = Field(max_length=200)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    result: Frame | Strategy | Critique | Synthesis | None = None
    error: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def role_result(self):
        expected = {
            "framing": Frame,
            "strategy": Strategy,
            "revision": Strategy,
            "critic": Critique,
            "synthesis": Synthesis,
        }[self.role]
        if self.result is not None and not isinstance(self.result, expected):
            raise ValueError("Task result does not match its role")
        if self.status == "succeeded" and self.result is None:
            raise ValueError("Successful tasks require a structured result")
        if self.result is not None and self.status != "succeeded":
            raise ValueError("Only completed tasks may publish a result")
        return self


class IssueNode(Model):
    id: Key
    kind: Literal["question", "assumption", "claim", "intervention", "outcome", "objection"]
    title: Text
    detail: Text
    task_id: Key
    grounding: Literal["model_hypothesis", "model_objection"] = "model_hypothesis"
    stakeholders: list[Text] = Field(default_factory=list, max_length=3)
    signals: list[Text] = Field(default_factory=list, max_length=3)


class IssueEdge(Model):
    source: Key
    target: Key
    kind: Literal["requires", "supports", "challenges", "may-influence"]


class Candidate(Model):
    id: Key
    task_id: Key
    title: Text
    mechanism: Text
    node_ids: list[Key] = Field(min_length=1, max_length=3)
    prerequisites: list[Text] = Field(min_length=1, max_length=3)
    tradeoffs: list[Text] = Field(min_length=1, max_length=3)
    supersedes: Key | None = None


class AnalysisRun(Model):
    model_config = ConfigDict(frozen=False)

    schema_version: Literal["tianji.analysis.v1"] = "tianji.analysis.v1"
    id: Key
    request: VisionRequest
    budget: AnalysisBudget
    status: Status = "queued"
    created_at: str
    finished_at: str | None = None
    tasks: list[AnalysisTask] = Field(default_factory=list, max_length=8)
    nodes: list[IssueNode] = Field(default_factory=list, max_length=20)
    edges: list[IssueEdge] = Field(default_factory=list, max_length=40)
    candidates: list[Candidate] = Field(default_factory=list, max_length=4)
    summary: str = Field(default="", max_length=1000)
    unresolved: list[Text] = Field(default_factory=list, max_length=8)
    calls: int = Field(default=0, ge=0, le=8)
    reserved_output_tokens: int = Field(default=0, ge=0, le=20000)
    duration_ms: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=400)
    architecture: Literal["bounded_same_model_agents"] = "bounded_same_model_agents"

    @model_validator(mode="after")
    def references(self):
        tasks = {task.id: task for task in self.tasks}
        nodes = {node.id: node for node in self.nodes}
        if len(tasks) != len(self.tasks) or len(nodes) != len(self.nodes):
            raise ValueError("Duplicate task or issue identity")
        for relation in (lambda t: t.dependencies, lambda t: [t.parent_id] if t.parent_id else []):
            visiting, visited = set(), set()

            def visit(id):
                if id in visiting:
                    raise ValueError("Task hierarchy/dependencies must be acyclic")
                if id in visited:
                    return
                if id not in tasks:
                    raise ValueError("Unknown task reference")
                visiting.add(id)
                for dep in relation(tasks[id]):
                    visit(dep)
                visiting.remove(id)
                visited.add(id)

            for id in tasks:
                visit(id)
        for node in self.nodes:
            if node.task_id not in tasks or tasks[node.task_id].status != "succeeded":
                raise ValueError("Issues require a completed producing task")
        for edge in self.edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("Unknown issue reference")
            if edge.kind == "challenges" and nodes[edge.source].kind != "objection":
                raise ValueError("Challenge edges require an objection source")
        candidate_ids = {candidate.id for candidate in self.candidates}
        if len(candidate_ids) != len(self.candidates):
            raise ValueError("Duplicate candidate identity")
        for candidate in self.candidates:
            if candidate.task_id not in tasks or any(n not in nodes for n in candidate.node_ids):
                raise ValueError("Unknown candidate reference")
            if any(nodes[n].task_id != candidate.task_id for n in candidate.node_ids):
                raise ValueError("Candidate claims must belong to its producing task")
            if candidate.supersedes and candidate.supersedes not in candidate_ids:
                raise ValueError("Unknown superseded candidate")
        by_id = {c.id: c for c in self.candidates}
        for candidate in self.candidates:
            lineage = {candidate.id}
            current = candidate
            while current.supersedes:
                if current.supersedes in lineage:
                    raise ValueError("Candidate supersession must be acyclic")
                lineage.add(current.supersedes)
                current = by_id[current.supersedes]
        for task in self.tasks:
            if isinstance(task.result, Synthesis):
                alternatives = task.result.alternatives
                if not set(alternatives) <= candidate_ids or len(alternatives) != len(
                    set(alternatives)
                ):
                    raise ValueError("Invalid synthesis alternatives")
            if isinstance(task.result, Critique):
                # Criticism precedes revision and must reference an original
                # strategy's claims, not framing, itself or a later revision.
                claim_ids = {
                    node_id
                    for candidate in self.candidates
                    if tasks[candidate.task_id].role == "strategy"
                    for node_id in candidate.node_ids
                }
                if any(o.target_claim_id not in claim_ids for o in task.result.objections):
                    raise ValueError("Invalid critique claim")
                if (
                    task.result.revision_task_id
                    and task.result.revision_task_id not in candidate_ids
                ):
                    raise ValueError("Unknown revision candidate")
        if self.calls > self.budget.max_calls or len(self.tasks) > self.budget.max_tasks:
            raise ValueError("Run exceeded call/task budget")
        if self.reserved_output_tokens > self.budget.max_output_tokens:
            raise ValueError("Run exceeded reserved token budget")
        return self
