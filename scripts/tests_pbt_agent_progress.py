#!/usr/bin/env python3
"""Property-based tests for the chat-relative progress meter."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_agent_progress():
    path = _SCRIPTS_DIR / "agent_progress.py"
    spec = importlib.util.spec_from_file_location("agent_progress_pbt", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_progress_pbt"] = mod
    spec.loader.exec_module(mod)
    return mod


ap = _load_agent_progress()


@pytest.mark.property
@given(done=st.integers(min_value=-1000, max_value=1000), total=st.integers(-100, 1000))
def test_progress_bar_is_always_fixed_width(done: int, total: int) -> None:
    bar = ap.progress_bar(done, total)
    assert len(bar) == 20
    assert set(bar) <= {"█", "░"}


@pytest.mark.property
@given(dirty=st.integers(-1000, 1000), baseline=st.integers(-100, 1000))
def test_percent_done_stays_in_percent_bounds(dirty: int, baseline: int) -> None:
    assert 0 <= ap.percent_done(dirty, baseline) <= 100


@pytest.mark.property
@given(
    parts=st.lists(
        st.text(
            alphabet=st.characters(blacklist_characters="|", blacklist_categories=("Cs",)),
            max_size=12,
        ),
        max_size=12,
    )
)
def test_split_steps_matches_nonblank_trimmed_parts(parts: list[str]) -> None:
    raw = "|".join(parts)
    assert ap.split_steps(raw) == [part.strip() for part in parts if part.strip()]


@pytest.mark.property
@given(
    steps=st.lists(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
            max_size=12,
        ),
        min_size=1,
        max_size=12,
        unique=True,
    )
)
def test_finishing_task_makes_progress_complete(steps: list[str]) -> None:
    task = ap.start_task_state("meter", steps, now=1.0)
    task = ap.finish_task_state(task, now=2.0)
    done, total = ap.chat_task_counts(task)
    assert done == total
    assert ap.chat_task_current_step(task) == "complete"
    assert "100%" in ap.render("12:00:00", "fallback", 3, 0, [], task)
