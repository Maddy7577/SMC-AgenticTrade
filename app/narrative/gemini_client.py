"""Gemini 2.0 Flash narrative generator (FR-N-01 to N-05).

Called only on VALID/WAIT signal publish (not every evaluation cycle) to
stay within free tier limits (NFR-C-03).
Failures fall back to placeholder text — never block publish (FR-N-04).
"""

from __future__ import annotations

import logging
import textwrap
from datetime import datetime, timezone

import google.generativeai as genai

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_NARRATIVE_MAX_WORDS,
    GEMINI_NARRATIVE_MIN_WORDS,
    GEMINI_TIMEOUT_SECONDS,
    TZ_IST,
)

log = logging.getLogger(__name__)

_FALLBACK = "Narrative unavailable — Gemini API call failed or timed out."

genai.configure(api_key=GEMINI_API_KEY)


def generate_narrative(
    strategy_name: str,
    rules_summary: str,
    evidence: dict,
    agent_scores: list[dict],
    trade_params: dict,
    signal_t: datetime | None = None,
) -> str:
    """Generate a 80–150 word narrative. Returns fallback on any failure."""
    try:
        prompt = _build_prompt(strategy_name, rules_summary, evidence, agent_scores, trade_params, signal_t)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=300,
                temperature=0.4,
            ),
            request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
        )
        text = response.text.strip()
        if not text:
            return _FALLBACK
        return text
    except Exception as exc:
        log.warning("gemini narrative failed", extra={"error": str(exc)})
        return _FALLBACK


def _build_prompt(
    strategy_name: str,
    rules_summary: str,
    evidence: dict,
    agent_scores: list[dict],
    trade_params: dict,
    signal_t: datetime | None,
) -> str:
    ist_time = ""
    if signal_t:
        ist = signal_t.astimezone(TZ_IST)
        ist_time = ist.strftime("%d %b %Y %H:%M IST")

    scores_text = "\n".join(
        f"  {a['agent_id'].upper()}: score={a['score']}, {a['verdict']}, reasons={a['reasons'][:2]}"
        for a in agent_scores
    )
    ev_text = str(evidence)[:400]
    tp = trade_params

    return textwrap.dedent(f"""
        You are a Smart Money Concepts (SMC) trading analyst.
        Write a concise {GEMINI_NARRATIVE_MIN_WORDS}–{GEMINI_NARRATIVE_MAX_WORDS} word
        trade rationale in plain English with a professional trader tone.
        Use IST timestamps. Do not use bullet points — write as flowing prose.

        Signal time: {ist_time}
        Strategy: {strategy_name}
        Rules summary: {rules_summary}

        Evidence detected:
        {ev_text}

        Agent scores:
        {scores_text}

        Trade parameters:
        Direction: {tp.get('direction', 'N/A').upper()}
        Entry: {tp.get('entry', 'N/A')}
        SL: {tp.get('sl', 'N/A')}
        TP1: {tp.get('tp1', 'N/A')}
        TP2: {tp.get('tp2', 'N/A')}
        RR: {tp.get('rr', 'N/A')}

        Write the rationale now:
    """).strip()
