"""Strategy ancestry tree — determines representative in a cluster (FR-CL-03, E2).

Ancestry order (most specific = higher priority):
  01_unicorn > 04_silver_bullet > 03_confirmation

Independent roots (no common ancestry with above family):
  02_judas, 06_ifvg

Clustering ONLY merges signals within the same root family (R4).
"""

from __future__ import annotations

# Priority within the Unicorn family (lower index = higher priority = chosen representative)
UNICORN_FAMILY = ["01_unicorn", "04_silver_bullet", "03_confirmation"]

# Independent roots — never merged with the Unicorn family
INDEPENDENT_ROOTS = {"02_judas", "06_ifvg"}


def get_family(strategy_id: str) -> str:
    """Return family name for grouping."""
    if strategy_id in UNICORN_FAMILY:
        return "unicorn_family"
    return strategy_id  # each independent root is its own family


def select_representative(strategy_ids: list[str]) -> str:
    """Return the highest-priority strategy_id from the list."""
    for candidate in UNICORN_FAMILY:
        if candidate in strategy_ids:
            return candidate
    # For independent roots, pick the only one (should never have multiple in one cluster)
    return strategy_ids[0]


def can_cluster_together(a: str, b: str) -> bool:
    """Return True if two strategies are allowed to form a cluster."""
    return get_family(a) == get_family(b)
