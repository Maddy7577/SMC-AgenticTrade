"""Signal cluster engine (FR-CL-02 to CL-05, E3).

Groups signals with matching canonical signatures within a 5-minute bucket.
Selects the representative using ancestry rules.
Applies confluence boost to representative's confidence.
Persists to clusters table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import NamedTuple

from app.clustering.ancestry import can_cluster_together, select_representative
from app.clustering.signature import build_cluster_key, parse_strategy_signature
from app.storage import db as _db
from app.storage.repositories import get_signal, insert_cluster, update_signal_gate
from config.settings import CONFLUENCE_BOOST, CONFLUENCE_BOOST_CAP

log = logging.getLogger(__name__)


class ClusterResult(NamedTuple):
    cluster_id: int
    representative_signal_id: int
    representative_strategy_id: str
    member_signal_ids: list[int]
    boosted_confidence: float


def process_new_signal(
    signal_id: int,
    pending_signals: list[dict],  # other signals pending cluster check
    db_path=_db.DB_PATH,
) -> ClusterResult | None:
    """Attempt to cluster the new signal with pending signals.

    `pending_signals` is a list of signal dicts (with 'id', 'strategy_id',
    'signature', 'confidence') that arrived in the same 5-min window.

    Returns ClusterResult if a cluster was formed/extended, else None.
    """
    with _db.get_connection(db_path) as conn:
        new_sig = get_signal(conn, signal_id)
    if not new_sig or not new_sig.get("signature"):
        return None

    new_parsed = parse_strategy_signature(new_sig["signature"])
    if not new_parsed:
        return None

    # Check each pending signal for cluster eligibility
    cluster_members: list[dict] = [new_sig]
    for pending in pending_signals:
        if pending["id"] == signal_id:
            continue
        if not pending.get("signature"):
            continue
        p_parsed = parse_strategy_signature(pending["signature"])
        if not p_parsed:
            continue
        if not can_cluster_together(new_parsed["strategy_id"], p_parsed["strategy_id"]):
            continue
        # Compare cluster keys
        new_key = _sig_to_cluster_key(new_sig)
        p_key = _sig_to_cluster_key(pending)
        if new_key and p_key and new_key == p_key:
            cluster_members.append(pending)

    if len(cluster_members) < 2:
        return None  # no cluster formed

    # Select representative
    strategy_ids = [m["strategy_id"] for m in cluster_members]
    rep_strategy = select_representative(strategy_ids)
    rep = next(m for m in cluster_members if m["strategy_id"] == rep_strategy)

    # Tie-break by confidence if multiple have same strategy
    reps = [m for m in cluster_members if m["strategy_id"] == rep_strategy]
    rep = max(reps, key=lambda m: m["confidence"])

    # Confluence boost
    size = len(cluster_members)
    boost = min(CONFLUENCE_BOOST.get(min(size, 3), 15.0), CONFLUENCE_BOOST_CAP)
    boosted = min(rep["confidence"] + boost, 100.0)

    with _db.get_connection(db_path) as conn:
        cluster_id = insert_cluster(
            conn,
            t=datetime.now(tz=timezone.utc),
            signature=new_sig["signature"],
            representative_signal_id=rep["id"],
            member_signal_ids=[m["id"] for m in cluster_members],
            boosted_confidence=boosted,
        )
        conn.commit()

    log.info(
        "cluster formed",
        extra={
            "cluster_id": cluster_id,
            "representative": rep["strategy_id"],
            "members": len(cluster_members),
            "boost": boost,
            "boosted_confidence": boosted,
        },
    )
    return ClusterResult(
        cluster_id=cluster_id,
        representative_signal_id=rep["id"],
        representative_strategy_id=rep["strategy_id"],
        member_signal_ids=[m["id"] for m in cluster_members],
        boosted_confidence=boosted,
    )


def _sig_to_cluster_key(signal: dict) -> str | None:
    parsed = parse_strategy_signature(signal.get("signature") or "")
    if not parsed:
        return None
    t_str = signal.get("t", "")
    try:
        t = datetime.fromisoformat(t_str)
    except (ValueError, TypeError):
        return None
    return build_cluster_key(
        t=t,
        direction=parsed["direction"],
        sweep_level=parsed["sweep_level"],
        mss_level=parsed["mss_level"],
        entry_midpoint=parsed["entry_midpoint"],
    )
