"""Research Budget.

Документ 04: у каждого search batch ограниченный бюджет — признаки, окна,
пороги, число гипотез, мутаций и поколений. Это часть защиты от множественного
тестирования, а не способ ускорить расчёт.
"""
from __future__ import annotations

import dataclasses as dc


class BudgetExceeded(RuntimeError):
    pass


@dc.dataclass
class ResearchBudget:
    max_hypotheses: int
    max_mutations_per_parent: int
    max_generations: int
    max_features: int
    max_targets: int
    max_complexity: int

    spent_hypotheses: int = 0
    spent_mutations: dict[str, int] = dc.field(default_factory=dict)

    @classmethod
    def from_policy(cls, policy) -> "ResearchBudget":
        b = policy.get("budget", default={})
        g = policy.get("grammar", default={})
        return cls(max_hypotheses=b.get("max_hypotheses_per_batch", 400),
                   max_mutations_per_parent=b.get("max_mutations_per_parent", 6),
                   max_generations=b.get("max_generations", 2),
                   max_features=b.get("max_features_per_batch", 8),
                   max_targets=b.get("max_targets_per_batch", 6),
                   max_complexity=g.get("max_complexity", 4))

    @property
    def remaining(self) -> int:
        return max(self.max_hypotheses - self.spent_hypotheses, 0)

    def can_spend(self, n: int = 1) -> bool:
        return self.spent_hypotheses + n <= self.max_hypotheses

    def spend(self, n: int = 1) -> None:
        if not self.can_spend(n):
            raise BudgetExceeded(
                f"бюджет батча исчерпан: {self.spent_hypotheses}/{self.max_hypotheses}")
        self.spent_hypotheses += n

    def can_mutate(self, parent_key: str) -> bool:
        return self.spent_mutations.get(parent_key, 0) < self.max_mutations_per_parent

    def spend_mutation(self, parent_key: str) -> None:
        if not self.can_mutate(parent_key):
            raise BudgetExceeded(f"лимит мутаций для {parent_key} исчерпан")
        self.spent_mutations[parent_key] = self.spent_mutations.get(parent_key, 0) + 1

    def check_inputs(self, features: list[str], targets: list[str]) -> None:
        if len(features) > self.max_features:
            raise BudgetExceeded(
                f"признаков {len(features)} при лимите {self.max_features}")
        if len(targets) > self.max_targets:
            raise BudgetExceeded(
                f"таргетов {len(targets)} при лимите {self.max_targets}")

    def report(self) -> dict:
        return {"max_hypotheses": self.max_hypotheses,
                "spent_hypotheses": self.spent_hypotheses,
                "remaining": self.remaining,
                "mutated_parents": len(self.spent_mutations),
                "mutations_spent": sum(self.spent_mutations.values())}
