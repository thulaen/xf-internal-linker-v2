#!/usr/bin/env python3
"""Unit tests for scripts/inter_model_interface.py."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.inter_model_interface as imi
import scripts.solve_autoissues as solve_cli


class InterfaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "coordination.sqlite3"
        self.clock = imi.FakeClock(1000.0)
        self.store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=2)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class SchemaTests(InterfaceTestCase):
    def test_initializes_expected_tables(self) -> None:
        tables = self.store.table_names()
        self.assertEqual(
            tables,
            {
                "waves",
                "agents",
                "issue_claims",
                "path_locks",
                "reviews",
                "messages",
                "sqlite_sequence",
            },
        )

    def test_migrates_older_runtime_database(self) -> None:
        old_db = Path(self.tmp.name) / "old.sqlite3"
        db = sqlite3.connect(old_db)
        try:
            db.execute(
                """
                create table waves(
                    id integer primary key autoincrement,
                    status text not null,
                    gate_opened_at real not null,
                    gate_closes_at real not null,
                    sprint_target integer not null,
                    review_closes_at real
                )
                """
            )
            db.execute(
                """
                create table agents(
                    id integer primary key autoincrement,
                    wave_id integer not null references waves(id),
                    agent text not null,
                    joined_at real not null,
                    heartbeat_at real not null,
                    status text not null,
                    unique(wave_id, agent)
                )
                """
            )
            db.execute(
                """
                create table issue_claims(
                    id integer primary key autoincrement,
                    wave_id integer not null references waves(id),
                    issue_id integer not null,
                    status text not null,
                    claimed_by text not null,
                    claimed_at real not null,
                    fixed_by text,
                    fixed_at real,
                    touched_paths text not null,
                    unique(wave_id, issue_id)
                )
                """
            )
            db.execute(
                """
                create table path_locks(
                    id integer primary key autoincrement,
                    wave_id integer not null references waves(id),
                    path text not null,
                    issue_id integer not null,
                    agent text not null,
                    locked_at real not null
                )
                """
            )
            db.execute(
                """
                create table reviews(
                    id integer primary key autoincrement,
                    wave_id integer not null references waves(id),
                    issue_id integer not null,
                    reviewer text not null,
                    vote text not null,
                    note text not null default '',
                    reviewed_at real not null,
                    unique(wave_id, issue_id, reviewer)
                )
                """
            )
            db.commit()
        finally:
            db.close()
        imi.InterModelInterface(old_db, now=self.clock.now)
        db = sqlite3.connect(old_db)
        try:
            agents = {row[1] for row in db.execute("pragma table_info(agents)")}
            locks = {row[1] for row in db.execute("pragma table_info(path_locks)")}
        finally:
            db.close()
        self.assertIn("detail", agents)
        self.assertIn("status_updated_at", agents)
        self.assertIn("lease_expires_at", locks)
        self.assertIn("messages", imi.InterModelInterface(old_db, now=self.clock.now).table_names())


class JoinGateTests(InterfaceTestCase):
    def test_two_agents_join_same_two_minute_gate(self) -> None:
        first = self.store.join("codex")
        self.clock.advance(60)
        second = self.store.join("claude")
        self.assertEqual(first.wave_id, second.wave_id)
        self.assertEqual(first.status, "forming")
        self.assertEqual(first.gate_closes_at, 1120.0)
        self.assertEqual(first.message, "codex joined sprint pool #1.")
        self.assertEqual(second.team_size, 2)

    def test_late_agent_waits_for_next_sprint(self) -> None:
        first = self.store.join("codex")
        self.clock.advance(imi.JOIN_GATE_SECONDS + 1)
        self.store.start_ready_sprints()
        late = self.store.join("gemini")
        self.assertEqual(first.wave_id, late.wave_id)
        self.assertEqual(late.status, "sprinting")
        self.assertEqual(late.team_size, 2)
        self.assertIsNone(self.store.wave_status(9999))

    def test_late_joined_agent_can_claim_current_sprint_work(self) -> None:
        self.store.join("codex")
        self.clock.advance(imi.JOIN_GATE_SECONDS + 1)
        self.store.start_ready_sprints()
        late = self.store.join("claude")
        claim = self.store.claim_issue("claude", 202, ["docs/new.md"])
        self.assertEqual(late.status, "sprinting")
        self.assertTrue(claim.claimed)
        self.assertEqual(claim.message, "claude claimed AutoIssue #202.")

    def test_start_ready_sprints_moves_wave_without_claim_side_effects(self) -> None:
        joined = self.store.join("codex")
        self.assertEqual(self.store.wave_status(joined.wave_id), "forming")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.assertEqual(self.store.wave_status(joined.wave_id), "sprinting")
        db = sqlite3.connect(self.db_path)
        try:
            fixed = db.execute("select count(*) from issue_claims").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(fixed, 0)

    def test_join_does_not_spawn_agents(self) -> None:
        self.store.join("codex")
        self.assertEqual(self.store.agent_names(), ["codex"])

    def test_duplicate_join_renews_same_agent_without_growing_team(self) -> None:
        first = self.store.join("codex")
        self.clock.advance(30)
        second = self.store.join("codex")
        self.assertEqual(first.wave_id, second.wave_id)
        self.assertEqual(second.team_size, 1)
        self.assertEqual(self.store.agent_states()["codex"], "active")

    def test_join_after_duplicate_clears_blocked_detail(self) -> None:
        self.store.join("codex")
        self.store.heartbeat("codex", state="blocked", detail="waiting")
        self.clock.advance(10)
        self.store.join("codex")
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            row = db.execute("select status, detail from agents where agent='codex'").fetchone()
        finally:
            db.close()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["detail"], "")

    def test_blocked_agent_is_visible_but_not_active_team_member(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.store.heartbeat("codex", state="blocked", detail="waiting for lock")
        self.assertEqual(self.store.agent_states()["codex"], "blocked")
        self.assertEqual(self.store.agent_names(), ["claude"])

    def test_status_summary_names_joined_agents_and_states(self) -> None:
        self.store.join("codex")
        self.store.join("antigravity")
        self.store.heartbeat("antigravity", state="thinking", detail="reading issues")
        summary = self.store.status_summary()
        self.assertIn("Agents: antigravity=thinking, codex=active.", summary)
        self.assertIn("2 agent(s)", summary)

    def test_join_cli_accepts_capitalized_claude_name(self) -> None:
        parsed = solve_cli._parse_args(["join", "--agent", "Claude"])
        self.assertEqual(parsed.agent, "claude")

    def test_agents_can_post_and_read_messages(self) -> None:
        self.store.join("codex")
        self.store.post_message("codex", "I am taking frontend-only work.")
        self.store.post_message("claude", "I will avoid frontend paths.")
        messages = self.store.recent_messages(limit=2)
        self.assertEqual(
            messages,
            [
                "codex: I am taking frontend-only work.",
                "claude: I will avoid frontend paths.",
            ],
        )


class ClaimTests(InterfaceTestCase):
    def test_claim_fails_cleanly_when_another_writer_has_lock(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        db = sqlite3.connect(self.db_path, timeout=0.05, isolation_level=None)
        try:
            db.execute("begin immediate")
            claim = self.store.claim_issue("codex", 101, ["scripts/a.py"])
        finally:
            db.rollback()
            db.close()
        self.assertFalse(claim.claimed)
        self.assertIn("retry", claim.message)

    def test_claim_requires_at_least_one_touched_path(self) -> None:
        self.store.join("codex")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        claim = self.store.claim_issue("codex", 101, [])
        self.assertFalse(claim.claimed)
        self.assertIn("path", claim.message)

    def test_claim_before_sprint_starts_is_rejected(self) -> None:
        self.store.join("codex")
        claim = self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.assertFalse(claim.claimed)
        self.assertIsNone(claim.wave_id)
        self.assertIn("no active sprint", claim.message)

    def test_overlapping_paths_cannot_be_claimed_by_two_agents(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        first = self.store.claim_issue("codex", 101, ["frontend/src/app/find-bugs"])
        second = self.store.claim_issue("claude", 102, ["frontend/src/app/find-bugs/file.ts"])
        self.assertTrue(first.claimed)
        self.assertEqual(first.wave_id, 1)
        self.assertEqual(first.message, "codex claimed AutoIssue #101.")
        self.assertFalse(second.claimed)
        self.assertEqual(second.message, "Claim overlaps frontend/src/app/find-bugs.")

    def test_separate_paths_can_be_claimed(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        first = self.store.claim_issue("codex", 101, ["frontend/src/app/find-bugs"])
        second = self.store.claim_issue("claude", 102, ["backend/apps/auto_issues"])
        self.assertTrue(first.claimed)
        self.assertTrue(second.claimed)
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "select path, lease_expires_at from path_locks order by path"
            ).fetchall()
        finally:
            db.close()
        self.assertEqual(
            [row["path"] for row in rows],
            ["backend/apps/auto_issues", "frontend/src/app/find-bugs"],
        )
        self.assertEqual([row["lease_expires_at"] for row in rows], [2021.0, 2021.0])

    def test_claim_owner_can_add_extra_paths_only_when_unlocked(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/owned_by_claude.py"])
        added = self.store.add_touched_paths("codex", 101, ["docs/inter-model.md"])
        blocked = self.store.add_touched_paths("codex", 101, ["scripts/owned_by_claude.py"])
        self.assertTrue(added.claimed)
        self.assertEqual(added.message, "codex added 1 extra path lock(s).")
        self.assertFalse(blocked.claimed)
        self.assertIn("overlaps", blocked.message)
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            claim = db.execute(
                "select touched_paths from issue_claims where issue_id=101"
            ).fetchone()
            locks = db.execute(
                "select path from path_locks where issue_id=101 order by path"
            ).fetchall()
        finally:
            db.close()
        self.assertEqual(claim["touched_paths"], "scripts/a.py\ndocs/inter-model.md")
        self.assertEqual([row["path"] for row in locks], ["docs/inter-model.md", "scripts/a.py"])

    def test_add_touched_paths_rejects_empty_unowned_and_duplicate_issue(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        empty = self.store.add_touched_paths("codex", 101, [])
        wrong_owner = self.store.add_touched_paths("claude", 101, ["docs/a.md"])
        duplicate = self.store.claim_issue("claude", 101, ["docs/b.md"])
        self.assertFalse(empty.claimed)
        self.assertIn("at least one path", empty.message)
        self.assertFalse(wrong_owner.claimed)
        self.assertIn("does not own", wrong_owner.message)
        self.assertFalse(duplicate.claimed)
        self.assertIn("already claimed", duplicate.message)

    def test_expired_lock_no_longer_blocks_claim(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.clock.advance(imi.LOCK_LEASE_SECONDS + 1)
        claim = self.store.claim_issue("claude", 102, ["scripts/a.py"])
        self.assertTrue(claim.claimed)


class HeartbeatTests(InterfaceTestCase):
    def test_heartbeat_for_unknown_agent_is_noop(self) -> None:
        self.store.heartbeat("missing", state="thinking", detail="nothing")
        self.assertEqual(self.store.agent_states(), {})

    def test_default_heartbeat_keeps_agent_active_with_empty_detail(self) -> None:
        self.store.join("codex")
        self.clock.advance(15)
        self.store.heartbeat("codex")
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "select status, detail, heartbeat_at, status_updated_at from agents where agent='codex'"
            ).fetchone()
        finally:
            db.close()
        self.assertEqual(
            dict(row),
            {"status": "active", "detail": "", "heartbeat_at": 1015.0, "status_updated_at": 1015.0},
        )

    def test_invalid_heartbeat_state_is_rejected(self) -> None:
        self.store.join("codex")
        expected = "state must be active, thinking, working, testing, reviewing, blocked, or possibly_idle"
        with self.assertRaisesRegex(ValueError, expected):
            self.store.heartbeat("codex", state="stale")
        with self.assertRaisesRegex(ValueError, expected):
            self.store.heartbeat("codex", state="sleeping")

    def test_thinking_heartbeat_keeps_slow_agent_active_and_extends_lock(self) -> None:
        self.store.join("codex")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts"])
        db = sqlite3.connect(self.db_path)
        try:
            before = db.execute("select lease_expires_at from path_locks").fetchone()[0]
        finally:
            db.close()
        self.clock.advance(600)
        self.store.heartbeat("codex", state="thinking", detail="reading issue")
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "select agents.detail, path_locks.lease_expires_at from agents join path_locks on path_locks.agent=agents.agent"
            ).fetchone()
        finally:
            db.close()
        stale = self.store.cleanup_stale_agents(max_age_seconds=900)
        self.assertEqual(stale, [])
        self.assertEqual(self.store.agent_states()["codex"], "thinking")
        self.assertEqual(row["detail"], "reading issue")
        self.assertGreater(row["lease_expires_at"], before)

    def test_possibly_idle_agent_keeps_locks_until_stale(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts"])
        self.clock.advance(301)
        stale = self.store.cleanup_stale_agents(max_age_seconds=900, idle_after_seconds=300)
        self.assertEqual(stale, [])
        self.assertEqual(self.store.agent_states()["codex"], "possibly_idle")
        blocked = self.store.claim_issue("claude", 102, ["scripts/new_file.py"])
        self.assertFalse(blocked.claimed)
        self.clock.advance(601)
        self.store.heartbeat("claude", state="working")
        stale = self.store.cleanup_stale_agents(max_age_seconds=900, idle_after_seconds=300)
        self.assertEqual(stale, ["codex"])
        claimed = self.store.claim_issue("claude", 103, ["scripts/new_file.py"])
        self.assertTrue(claimed.claimed)

    def test_add_touched_paths_before_sprint_and_busy_database_fail_cleanly(self) -> None:
        self.store.join("codex")
        before_sprint = self.store.add_touched_paths("codex", 101, ["scripts/a.py"])
        self.assertFalse(before_sprint.claimed)
        self.assertIn("no active sprint", before_sprint.message)
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        db = sqlite3.connect(self.db_path, timeout=0.05, isolation_level=None)
        try:
            db.execute("begin immediate")
            busy = self.store.add_touched_paths("codex", 101, ["docs/a.md"])
        finally:
            db.rollback()
            db.close()
        self.assertFalse(busy.claimed)
        self.assertIn("retry", busy.message)

    def test_stale_agent_is_marked_and_locks_are_released(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts"])
        self.clock.advance(901)
        self.store.heartbeat("claude")
        stale = self.store.cleanup_stale_agents(max_age_seconds=900)
        self.assertEqual(stale, ["codex"])
        claim = self.store.claim_issue("claude", 102, ["scripts/new_file.py"])
        self.assertTrue(claim.claimed)


class ReviewTests(InterfaceTestCase):
    def test_only_claim_owner_can_mark_fixed(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.assertFalse(self.store.mark_fixed("claude", 101))
        self.assertIsNone(self.store.recommend_commit_agent().agent)
        self.assertTrue(self.store.mark_fixed("codex", 101))
        self.assertEqual(self.store.recommend_commit_agent().agent, "codex")

    def test_mark_fixed_without_sprint_does_not_create_review_state(self) -> None:
        self.store.join("codex")
        self.assertFalse(self.store.mark_fixed("codex", 101))
        self.assertEqual(self.store.current_wave_status(), "forming")
        db = sqlite3.connect(self.db_path)
        try:
            review_count = db.execute("select count(*) from reviews").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(review_count, 0)

    def test_mark_fixed_rejects_unclaimed_issue_and_sets_review_close_time(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.assertFalse(self.store.mark_fixed("codex", 999))
        self.assertTrue(self.store.mark_fixed("codex", 101))
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            claim = db.execute(
                "select status, fixed_by, fixed_at from issue_claims where issue_id=101"
            ).fetchone()
            row = db.execute("select review_closes_at from waves").fetchone()
        finally:
            db.close()
        self.assertEqual(
            dict(claim),
            {"status": "fixed", "fixed_by": "codex", "fixed_at": 1121.0},
        )
        self.assertIsNone(row["review_closes_at"])

    def test_mark_fixed_reaches_review_target_and_records_timestamp(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=1)
        store.join("codex")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        self.assertTrue(store.mark_fixed("codex", 101))
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            claim = db.execute(
                "select status, fixed_by, fixed_at from issue_claims where issue_id=101"
            ).fetchone()
            wave = db.execute("select status, review_closes_at from waves").fetchone()
        finally:
            db.close()
        self.assertEqual(
            dict(claim),
            {"status": "fixed", "fixed_by": "codex", "fixed_at": 1121.0},
        )
        self.assertEqual(dict(wave), {"status": "reviewing", "review_closes_at": 2021.0})

    def test_review_vote_before_review_phase_is_ignored(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.assertFalse(self.store.review_issue("claude", 101, "needs-correction", "too early"))
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        self.store.review_issue("claude", 101, "pass", "looks correct")
        self.store.review_issue("codex", 102, "pass", "looks correct")
        self.assertTrue(self.store.consensus_ready())

    def test_review_rejects_invalid_vote_and_self_review_and_updates_note(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        with self.assertRaisesRegex(ValueError, "vote must be pass or needs-correction"):
            self.store.review_issue("claude", 101, "maybe")
        self.assertFalse(self.store.review_issue("codex", 101, "pass"))
        self.assertTrue(self.store.review_issue("claude", 101, "needs-correction", "first"))
        self.clock.advance(7)
        self.assertTrue(self.store.review_issue("claude", 101, "pass", "updated"))
        db = sqlite3.connect(self.db_path)
        try:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "select vote, note, reviewed_at from reviews where issue_id=101 and reviewer='claude'"
            ).fetchone()
        finally:
            db.close()
        self.assertEqual(row["vote"], "pass")
        self.assertEqual(row["note"], "updated")
        self.assertEqual(row["reviewed_at"], 1128.0)

    def test_fixed_target_enters_review_and_reaches_consensus(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        self.assertEqual(self.store.current_wave_status(), "reviewing")
        self.store.review_issue("claude", 101, "pass", "looks correct")
        self.store.review_issue("codex", 102, "pass", "looks correct")
        self.assertTrue(self.store.consensus_ready())
        self.assertEqual(self.store.current_wave_status(), "consensus_ready")

    def test_needs_correction_blocks_consensus(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        self.store.review_issue("claude", 101, "needs-correction", "test missing")
        self.store.review_issue("codex", 102, "pass", "looks correct")
        self.assertFalse(self.store.consensus_ready())
        self.assertEqual(self.store.current_wave_status(), "reviewing")

    def test_review_for_unfixed_issue_does_not_block_consensus(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        self.assertFalse(self.store.review_issue("claude", 999, "needs-correction", "unrelated"))
        self.store.review_issue("claude", 101, "pass", "looks correct")
        self.store.review_issue("codex", 102, "pass", "looks correct")
        self.assertTrue(self.store.consensus_ready())

    def test_review_timeout_allows_consensus_when_one_peer_is_slow(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=1)
        store.join("codex")
        store.join("claude")
        store.join("gemini")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        store.mark_fixed("codex", 101)
        store.review_issue("claude", 101, "pass", "looks correct")
        self.assertFalse(store.consensus_ready())
        self.clock.advance(imi.REVIEW_SECONDS + 1)
        self.assertTrue(store.consensus_ready())
        self.assertEqual(store.current_wave_status(), "consensus_ready")

    def test_consensus_needs_two_peer_passes_before_timeout_with_three_peers(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=1)
        store.join("codex")
        store.join("claude")
        store.join("gemini")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        store.mark_fixed("codex", 101)
        store.review_issue("claude", 101, "pass", "looks correct")
        self.assertFalse(store.consensus_ready())
        store.review_issue("gemini", 101, "pass", "looks correct")
        self.assertTrue(store.consensus_ready())

    def test_single_agent_cannot_reach_peer_review_consensus(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=1)
        store.join("codex")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        store.mark_fixed("codex", 101)
        self.clock.advance(imi.REVIEW_SECONDS + 1)
        self.assertFalse(store.consensus_ready())


class RecommendationTests(InterfaceTestCase):
    def test_recommends_agent_with_most_fixed_work(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("codex", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("codex", 102)
        rec = self.store.recommend_commit_agent()
        self.assertEqual(rec.agent, "codex")
        self.assertIn("fixed 2 issue", rec.reason)

    def test_recommendation_ignores_stale_agents_and_correction_requests(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=3)
        store.join("codex")
        store.join("claude")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        store.claim_issue("codex", 102, ["scripts/b.py"])
        store.claim_issue("claude", 103, ["scripts/c.py"])
        store.mark_fixed("codex", 101)
        store.mark_fixed("codex", 102)
        store.mark_fixed("claude", 103)
        store.review_issue("claude", 101, "needs-correction", "test missing")
        self.clock.advance(901)
        store.heartbeat("claude", state="reviewing")
        store.cleanup_stale_agents(max_age_seconds=900)
        rec = store.recommend_commit_agent()
        self.assertEqual(rec.agent, "claude")

    def test_recommendation_tie_uses_latest_fix_then_agent_name(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.clock.advance(5)
        self.store.mark_fixed("claude", 102)
        self.assertEqual(self.store.recommend_commit_agent().agent, "claude")

    def test_recommendation_has_none_when_only_correction_requested_work_exists(self) -> None:
        store = imi.InterModelInterface(self.db_path, now=self.clock.now, sprint_target=1)
        store.join("codex")
        store.join("claude")
        self.clock.advance(121)
        store.start_ready_sprints()
        store.claim_issue("codex", 101, ["scripts/a.py"])
        store.mark_fixed("codex", 101)
        store.review_issue("claude", 101, "needs-correction", "missing test")
        rec = store.recommend_commit_agent()
        self.assertIsNone(rec.agent)
        self.assertEqual(rec.reason, "No fixed AutoIssues are recorded yet.")


class StatusSummaryTests(InterfaceTestCase):
    def test_status_summary_reports_empty_pool(self) -> None:
        self.assertEqual(self.store.status_summary(), "No AutoIssue sprint pool is active.")

    def test_status_summary_reports_forming_and_consensus_ready(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.assertEqual(
            self.store.status_summary(),
            "Pool #1 is forming with 2 agent(s); 0 fixed. Agents: claude=active, codex=active.",
        )
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.claim_issue("claude", 102, ["scripts/b.py"])
        self.store.mark_fixed("codex", 101)
        self.store.mark_fixed("claude", 102)
        self.store.review_issue("claude", 101, "pass")
        self.store.review_issue("codex", 102, "pass")
        self.store.consensus_ready()
        self.assertEqual(
            self.store.status_summary(),
            "Pool #1 is consensus_ready with 2 agent(s); 2 fixed. Agents: claude=active, codex=active.",
        )

    def test_status_summary_reports_fixed_idle_stale_and_overrun(self) -> None:
        self.store.join("codex")
        self.store.join("claude")
        self.clock.advance(121)
        self.store.start_ready_sprints()
        self.store.claim_issue("codex", 101, ["scripts/a.py"])
        self.store.mark_fixed("codex", 101)
        self.clock.advance(301)
        self.store.cleanup_stale_agents(max_age_seconds=900, idle_after_seconds=300)
        summary = self.store.status_summary()
        self.assertIn("Pool #", summary)
        self.assertIn("sprinting", summary)
        self.assertIn("1 fixed", summary)
        self.assertIn("Possibly idle:", summary)
        self.assertIn("codex", summary)
        self.assertIn("claude", summary)
        self.clock.advance(imi.REVIEW_SECONDS)
        self.store.heartbeat("claude")
        self.store.cleanup_stale_agents(max_age_seconds=900, idle_after_seconds=300)
        summary = self.store.status_summary()
        self.assertIn("over its 15-minute target", summary)
        self.assertIn("Stale agents: codex", summary)


class HelperTests(unittest.TestCase):
    def test_normalize_path_trims_slashes_spaces_and_backslashes(self) -> None:
        self.assertEqual(imi.normalize_path(" \\scripts\\a.py/ "), "scripts/a.py")

    def test_paths_overlap_for_same_parent_child_and_separate_paths(self) -> None:
        self.assertTrue(imi.paths_overlap("scripts", "scripts/a.py"))
        self.assertTrue(imi.paths_overlap("scripts/a.py", "scripts"))
        self.assertTrue(imi.paths_overlap("scripts/a.py", "scripts/a.py"))
        self.assertFalse(imi.paths_overlap("scripts/a.py", "scripts2/a.py"))

    def test_database_busy_detection(self) -> None:
        self.assertTrue(imi._is_database_busy(sqlite3.OperationalError("database is locked")))
        self.assertTrue(imi._is_database_busy(sqlite3.OperationalError("database is busy")))
        self.assertFalse(imi._is_database_busy(sqlite3.OperationalError("syntax error")))

    def test_row_get_requires_exact_key_casing(self) -> None:
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        try:
            row = db.execute("select 1 as name").fetchone()
        finally:
            db.close()
        self.assertEqual(imi._row_get(row, "name"), 1)
        with self.assertRaises(KeyError):
            imi._row_get(row, "NAME")

    def test_sql_marks_and_ensure_column(self) -> None:
        self.assertEqual(imi._sql_marks(("a", "b", "c")), "?, ?, ?")
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        try:
            db.execute("create table sample(id integer primary key)")
            imi._ensure_column(db, "sample", "name", "text")
            imi._ensure_column(db, "sample", "name", "text")
            columns = [row["name"] for row in db.execute("pragma table_info(sample)")]
        finally:
            db.close()
        self.assertEqual(columns.count("name"), 1)


if __name__ == "__main__":
    unittest.main()
