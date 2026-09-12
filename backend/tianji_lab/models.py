"""Strict, bounded data contracts for the fictional supply-chain laboratory."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_VERSION = "supply-chain.v1"
Action = Literal["wait", "order_standard", "order_express"]
Role = Literal["director", "retailer", "supplier"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )


class Scenario(Model):
    name: str = Field(min_length=1, max_length=100)
    horizon: int = Field(default=6, ge=1, le=10)
    initial_inventory: int = Field(default=12, ge=0, le=100)
    initial_cash: int = Field(default=160, ge=0, le=10000)
    demand_per_tick: int = Field(default=4, ge=1, le=20)
    supplier_stock: int = Field(default=40, ge=0, le=200)
    shipment_size: int = Field(default=8, ge=1, le=20)
    standard_cost: int = Field(default=16, ge=1, le=1000)
    express_cost: int = Field(default=32, ge=1, le=1000)
    standard_lead: int = Field(default=2, ge=1, le=5)
    express_lead: int = Field(default=1, ge=1, le=5)
    description: str | None = Field(
        default=(
            "Fictional civilian supply chain with fixed demand, finite stock, "
            "and rules-v1 ordering; results are model-conditional, not predictions."
        ),
        max_length=2000,
    )


class Goal(Model):
    max_shortage: int = Field(default=0, ge=0, le=200)
    min_cash: int = Field(default=0, ge=0, le=10000)
    max_spend: int = Field(default=100, ge=0, le=10000)
    min_inventory: int = Field(default=0, ge=0, le=100)


class Shipment(Model):
    due_tick: int = Field(ge=1, le=15)
    quantity: int = Field(ge=1, le=20)


class State(Model):
    tick: int = Field(ge=0, le=10)
    inventory: int = Field(ge=0, le=300)
    cash: int = Field(ge=0, le=10000)
    supplier_stock: int = Field(ge=0, le=200)
    delivered: int = Field(ge=0, le=200)
    shortage: int = Field(ge=0, le=200)
    spent: int = Field(ge=0, le=10000)
    shipments: list[Shipment] = Field(default_factory=list, max_length=10)


class Frame(Model):
    state: State
    action: Literal["initial", "wait", "order_standard", "order_express"]
    events: list[Annotated[str, Field(max_length=500)]] = Field(max_length=16)
    state_hash: Digest


class Trajectory(Model):
    frames: list[Frame] = Field(min_length=1, max_length=11)
    actions: list[Action] = Field(max_length=10)
    final_state: State
    state_hash: Digest
    goal_met: bool | None = None
    rule_version: Literal["supply-chain.v1"] = RULE_VERSION


class SearchResult(Model):
    plans: list[Trajectory] = Field(max_length=3)
    expanded: int = Field(ge=0, le=50000)
    exhausted: bool
    status: Literal["found", "no_solution", "budget_exhausted"]
    rule_version: Literal["supply-chain.v1"] = RULE_VERSION

    @model_validator(mode="after")
    def consistent_status(self) -> "SearchResult":
        if self.status == "found":
            if not self.plans or any(plan.goal_met is not True for plan in self.plans):
                raise ValueError("found requires forward-verified goal plans")
        elif self.plans:
            raise ValueError("only found may contain plans")
        if self.status == "no_solution" and not self.exhausted:
            raise ValueError("no_solution requires an exhausted frontier")
        if self.status == "budget_exhausted" and self.exhausted:
            raise ValueError("budget_exhausted requires an unsearched frontier")
        return self
