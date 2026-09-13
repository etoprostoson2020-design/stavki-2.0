"""Memory API — операции, перечисленные в документе 06."""
from __future__ import annotations

from fsl.memory import families, lifecycle, regions
from fsl.memory import registry as reg
from fsl.memory.context import build_context, what_do_we_know

find_similar_hypothesis = reg.find_similar
get_feature_performance = reg.meta_summary
get_exhausted_regions = regions.list_exhausted
get_revival_candidates = lifecycle.revival_candidates
get_failure_history = lifecycle.failure_history
get_strategy_families = families.rebuild_families
get_similarity_matrix = families.similarity_matrix
get_memory_context = build_context
ask_memory = what_do_we_know

__all__ = ["find_similar_hypothesis", "get_feature_performance",
           "get_exhausted_regions", "get_revival_candidates", "get_failure_history",
           "get_strategy_families", "get_similarity_matrix", "get_memory_context",
           "ask_memory"]
