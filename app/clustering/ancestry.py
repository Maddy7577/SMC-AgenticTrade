"""Strategy ancestry tree — determines representative in a cluster (FR-CL2-01–08).

Confirmation family (priority: Unicorn > Silver Bullet > MMM > CISD > Confirmation):
  01_unicorn, 04_silver_bullet, 09_mmm, 14_cisd, 03_confirmation

Judas family (Judas always representative):
  02_judas, 10_po3

Independent roots (never merge with any family):
  05_nested_fvg, 06_ifvg, 07_ote_fvg, 08_rejection_block,
  11_propulsion, 12_vacuum, 13_reclaimed_fvg, 15_bpr_ob
"""

from __future__ import annotations

# Priority within the Confirmation family (lower index = higher priority = representative)
CONFIRMATION_FAMILY: list[str] = [
    "01_unicorn", "04_silver_bullet", "09_mmm", "14_cisd", "03_confirmation"
]

# Judas family — Judas always representative (index 0)
JUDAS_FAMILY: list[str] = ["02_judas", "10_po3"]

# Independent roots — never merged with any family
INDEPENDENT_ROOTS: set[str] = {
    "05_nested_fvg", "06_ifvg", "07_ote_fvg", "08_rejection_block",
    "11_propulsion", "12_vacuum", "13_reclaimed_fvg", "15_bpr_ob",
}


def get_family(strategy_id: str) -> str:
    """Return family name for grouping."""
    if strategy_id in CONFIRMATION_FAMILY:
        return "confirmation_family"
    if strategy_id in JUDAS_FAMILY:
        return "judas_family"
    return strategy_id  # each independent root is its own family


def select_representative(strategy_ids: list[str]) -> str:
    """Return the highest-priority strategy_id from the list."""
    # Search confirmation family by priority order
    for candidate in CONFIRMATION_FAMILY:
        if candidate in strategy_ids:
            return candidate
    # Search Judas family — Judas always first
    for candidate in JUDAS_FAMILY:
        if candidate in strategy_ids:
            return candidate
    # Fallback for independent roots (should not cluster, but defensive)
    return strategy_ids[0]


def can_cluster_together(a: str, b: str) -> bool:
    """Return True if two strategies are allowed to form a cluster."""
    if a in INDEPENDENT_ROOTS or b in INDEPENDENT_ROOTS:
        return False
    return get_family(a) == get_family(b)
