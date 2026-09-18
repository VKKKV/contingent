"""Single-proposal, offline adjudication; only the kernel can transition state.

Content hashes provide integrity, not authentication. The director must supply a
trusted context and authoritative state from an immutable branch/tick. Participant
observations deliberately contain no full-state digest (private state is enumerable).
"""

from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from . import kernel
from .models import Action, Digest, Model, Scenario, Shipment, State
from .store import canonical

ParticipantRole = Literal["retailer", "supplier"]
AdjudicationStatus = Literal["accepted", "rejected"]
Identifier = Annotated[str, Field(min_length=1, max_length=100)]
_IDENTIFIER = TypeAdapter(Identifier)
_ROLE = TypeAdapter(ParticipantRole)
_ACTION = TypeAdapter(Action)


def _digest(value: object) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


class ObservationContext(Model):
    """Director-supplied identity of the frozen branch specification."""

    branch_id: Identifier
    scenario_revision: int = Field(ge=1, le=2147483647)
    spec_hash: Digest


class _Projection(Model):
    tick: int = Field(ge=0, le=10)
    # JSON arrays also occur in Python API adapter payloads. Convert only a
    # bounded list, never arbitrary iterables/generators or unordered containers.
    shipments: tuple[Shipment, ...] = Field(max_length=10)

    @field_validator("shipments", mode="before")
    @classmethod
    def freeze_shipments(cls, value: object) -> object:
        if isinstance(value, list):
            if len(value) > 10:
                raise ValueError("at most 10 shipments are allowed")
            return tuple(value)
        return value


class RetailerProjection(_Projection):
    inventory: int = Field(ge=0, le=300)
    cash: int = Field(ge=0, le=10000)
    delivered: int = Field(ge=0, le=200)
    shortage: int = Field(ge=0, le=400)
    spent: int = Field(ge=0, le=10000)


class SupplierProjection(_Projection):
    supplier_stock: int = Field(ge=0, le=200)


class ObservationEnvelope(Model):
    actor_id: Identifier
    role: ParticipantRole
    context: ObservationContext
    tick: int = Field(ge=0, le=10)
    projection: RetailerProjection | SupplierProjection
    projection_hash: Digest
    observation_hash: Digest

    @model_validator(mode="after")
    def consistent_projection(self) -> "ObservationEnvelope":
        expected = RetailerProjection if self.role == "retailer" else SupplierProjection
        if not isinstance(self.projection, expected):
            raise ValueError("projection does not match observation role")
        if self.tick != self.projection.tick:
            raise ValueError("projection and observation tick differ")
        return self

    def verify_integrity(self) -> None:
        """Check public content only; authoritative freshness is adjudicator-owned."""
        if _digest(self.projection.model_dump(mode="json")) != self.projection_hash:
            raise ValueError("observation projection hash mismatch")
        if _digest(self.model_dump(mode="json", exclude={"observation_hash"})) != (
            self.observation_hash
        ):
            raise ValueError("observation hash mismatch")


class ActionProposal(Model):
    actor_id: Identifier
    role: ParticipantRole
    action: Action
    observation_hash: Digest
    policy_id: Identifier


class AdjudicationRecord(Model):
    """Director-only receipt: its hash binds every field except record_hash itself."""

    record_id: Identifier
    adjudicator_id: Identifier
    proposal_actor_id: Identifier
    role: ParticipantRole
    context: ObservationContext
    policy_id: Identifier
    pre_state_hash: Digest
    observation_hash: Digest
    action: Action
    status: AdjudicationStatus
    reason: str = Field(min_length=1, max_length=500)
    post_state_hash: Digest
    record_hash: Digest

    @model_validator(mode="after")
    def consistent_record(self) -> "AdjudicationRecord":
        if self.adjudicator_id == self.proposal_actor_id:
            raise ValueError("adjudicator must be independent from proposing actor")
        if self.status == "rejected" and self.post_state_hash != self.pre_state_hash:
            raise ValueError("rejected proposal must not change state")
        if self.status == "accepted" and self.role == "supplier" and self.action != "wait":
            raise ValueError("supplier may only wait")
        if _digest(self.model_dump(mode="json", exclude={"record_hash"})) != self.record_hash:
            raise ValueError("adjudication record hash mismatch")
        return self


def observe_envelope(
    state: State,
    actor_id: str,
    role: ParticipantRole,
    *,
    context: ObservationContext,
) -> ObservationEnvelope:
    """Return a bounded, deeply immutable projection, without private-state hashes."""
    state = State.model_validate(state)
    context = ObservationContext.model_validate(context)
    actor_id = _IDENTIFIER.validate_python(actor_id, strict=True)
    role = _ROLE.validate_python(role, strict=True)
    projection_type = RetailerProjection if role == "retailer" else SupplierProjection
    projection = projection_type.model_validate(kernel.observe(state, role))
    payload = {
        "actor_id": actor_id,
        "role": role,
        "context": context.model_dump(mode="json"),
        "tick": state.tick,
        "projection": projection.model_dump(mode="json"),
        "projection_hash": _digest(projection.model_dump(mode="json")),
    }
    return ObservationEnvelope(**payload, observation_hash=_digest(payload))


class FakeActor:
    """Deterministic test double; never receives the authoritative State.

    A fixed known action may intentionally be unauthorized or unaffordable: a
    proposal is inert and adjudication, not this policy, enforces permissions.
    """

    def __init__(self, actor_id: str, role: ParticipantRole, action: Action = "wait"):
        self.actor_id = _IDENTIFIER.validate_python(actor_id, strict=True)
        self.role = _ROLE.validate_python(role, strict=True)
        self.action = _ACTION.validate_python(action, strict=True)

    def propose(self, observation: ObservationEnvelope) -> ActionProposal:
        observation = ObservationEnvelope.model_validate(observation)
        observation.verify_integrity()
        if observation.actor_id != self.actor_id or observation.role != self.role:
            raise ValueError("observation does not belong to this actor")
        return ActionProposal(
            actor_id=self.actor_id,
            role=self.role,
            action=self.action,
            observation_hash=observation.observation_hash,
            policy_id=f"fake.{self.role}.fixed-action.v1",
        )


def adjudicate(
    scenario: Scenario,
    state: State,
    observation: ObservationEnvelope,
    proposal: ActionProposal,
    *,
    context: ObservationContext,
    adjudicator_id: str,
    record_id: str,
) -> tuple[AdjudicationRecord, State]:
    """Apply one independent proposal or return a rejection and detached state.

    Malformed contracts, mismatched actor/role, self-adjudication and an invalid
    authoritative spec binding raise ValueError. Well-formed stale/tampered
    observations, forbidden actions and kernel refusals produce rejected receipts.
    Rejected receipts hash the unchanged state as both pre- and post-state.
    """
    scenario = Scenario.model_validate(scenario)
    state = State.model_validate(state)
    context = ObservationContext.model_validate(context)
    observation = ObservationEnvelope.model_validate(observation)
    proposal = ActionProposal.model_validate(proposal)
    adjudicator_id = _IDENTIFIER.validate_python(adjudicator_id, strict=True)
    record_id = _IDENTIFIER.validate_python(record_id, strict=True)
    if context.spec_hash != _digest(scenario.model_dump(mode="json")):
        raise ValueError("authoritative context spec_hash does not match scenario")
    if adjudicator_id == proposal.actor_id:
        raise ValueError("adjudicator must be independent from proposing actor")
    if observation.actor_id != proposal.actor_id or observation.role != proposal.role:
        raise ValueError("proposal and observation actor/role differ")

    expected = observe_envelope(state, proposal.actor_id, proposal.role, context=context)
    pre_hash = kernel.state_hash(state)
    next_state = state.model_copy(deep=True)
    status: AdjudicationStatus = "rejected"
    if observation != expected or proposal.observation_hash != expected.observation_hash:
        reason = "observation is stale or does not match authoritative state/context"
    elif proposal.role == "supplier" and proposal.action != "wait":
        reason = "supplier may only wait; no supplier-specific kernel command exists"
    else:
        try:
            next_state = kernel.step(scenario, state, proposal.action).state
        except ValueError as exc:
            reason = f"kernel rejected proposal: {exc}"
        else:
            status = "accepted"
            reason = "accepted by authoritative kernel"

    payload = {
        "record_id": record_id,
        "adjudicator_id": adjudicator_id,
        "proposal_actor_id": proposal.actor_id,
        "role": proposal.role,
        "context": context.model_dump(mode="json"),
        "policy_id": proposal.policy_id,
        "pre_state_hash": pre_hash,
        "observation_hash": proposal.observation_hash,
        "action": proposal.action,
        "status": status,
        "reason": reason,
        "post_state_hash": kernel.state_hash(next_state),
    }
    record = AdjudicationRecord(**payload, record_hash=_digest(payload))
    return record, next_state
