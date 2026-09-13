"""Memory Context: с чего начинается каждый search batch.

Документ 06, ключевой принцип: лаборатория обязана накапливать знание, а не
искать заново одно и то же. Генератор не имеет права запускать батч, не
спросив память, что про эти области уже известно.

Возвращает не «да/нет», а разбор: что дубликат, что уже исследованная область,
что исчерпано, а что действительно ново.
"""
from __future__ import annotations

import dataclasses as dc
from collections import Counter

from fsl.logging import get_logger
from fsl.memory import dedupe, regions
from fsl.memory import registry as reg
from fsl.memory.fingerprints import region_key

log = get_logger(__name__)


@dc.dataclass
class CandidateContext:
    candidate_id: str
    verdict: str
    detail: str
    region: str
    region_exhausted: bool
    should_evaluate: bool
    known_hypothesis_id: str | None = None

    def as_dict(self) -> dict:
        return dc.asdict(self)


def build_context(sess, candidates, *, dataset_version: str, feature_versions: dict,
                  policy_hashes: dict) -> dict:
    """Прогоняет батч через память ДО расчёта."""
    per_candidate: list[CandidateContext] = []
    for cand in candidates:
        if not cand.conditions:
            continue                                  # негативные контроли не помним
        d = dedupe.check(sess, list(cand.conditions), cand.target,
                         dataset_version=dataset_version,
                         feature_versions=feature_versions,
                         policy_hashes=policy_hashes)
        rk = region_key(list(cand.conditions), cand.target)
        exhausted = regions.is_exhausted(sess, rk, dataset_version) is not None
        per_candidate.append(CandidateContext(
            candidate_id=cand.candidate_id, verdict=d.verdict, detail=d.detail,
            region=rk, region_exhausted=exhausted,
            should_evaluate=d.should_evaluate and not exhausted,
            known_hypothesis_id=d.known_hypothesis_id))

    counts = Counter(c.verdict for c in per_candidate)
    to_eval = [c for c in per_candidate if c.should_evaluate]
    skipped = [c for c in per_candidate if not c.should_evaluate]

    ctx = {
        "candidates_in": len(per_candidate),
        "to_evaluate": len(to_eval),
        "skipped": len(skipped),
        "verdicts": dict(counts),
        "skipped_regions_exhausted": sum(1 for c in skipped if c.region_exhausted),
        "registry": reg.registry_stats(sess),
        "exhausted_regions": regions.list_exhausted(sess),
        "per_candidate": [c.as_dict() for c in per_candidate],
    }
    log.info("memory.context", candidates=len(per_candidate),
             to_evaluate=len(to_eval), skipped=len(skipped))
    return ctx


def what_do_we_know(sess, conditions, target) -> dict:
    """Ответ на вопрос «мы это уже проверяли и чем кончилось?» без чтения файлов."""
    similar = reg.find_similar(sess, conditions, target)
    hist = reg.region_history(sess, conditions, target)
    return {
        "question": {"conditions": [c.as_dict() if hasattr(c, "as_dict") else dict(c)
                                    for c in conditions], "target": target},
        "region": hist,
        "checked_before": len(similar),
        "results": [{"hypothesis_id": r.hypothesis_id, "conditions": r.conditions,
                     "dataset_version": r.dataset_version, "n_signals": r.n_signals,
                     "z": r.z, "passed_batch_threshold": r.passed_batch_threshold,
                     "status": r.status, "strategy_id": r.strategy_id,
                     "times_seen": r.times_seen}
                    for r in similar[:10]],
    }
