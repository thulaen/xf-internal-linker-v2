#!/usr/bin/env python3
"""SQLite coordination for manually joined AutoIssue agents."""
from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "audit" / "inter_model" / "coordination.sqlite3"
JOIN_GATE_SECONDS = 600
REVIEW_SECONDS = 900
STALE_AGENT_SECONDS = 900
IDLE_AGENT_SECONDS = 300
LOCK_LEASE_SECONDS = 900
MAX_MESSAGE_CHARS = 500
ACTIVE_AGENT_STATUSES = ("active", "thinking", "working", "testing", "reviewing")
VISIBLE_AGENT_STATUSES = ACTIVE_AGENT_STATUSES + ("blocked", "possibly_idle")
VALID_AGENT_STATUSES = VISIBLE_AGENT_STATUSES + ("stale",)


@dataclass(frozen=True)
class JoinResult:
    """Result shown after an agent joins a sprint pool."""

    wave_id: int
    status: str
    team_size: int
    gate_closes_at: float
    message: str


@dataclass(frozen=True)
class ClaimResult:
    """Result shown after an agent tries to claim one AutoIssue."""

    claimed: bool
    wave_id: int | None
    message: str


@dataclass(frozen=True)
class Recommendation:
    """Recommended agent for final staging and commit prep."""

    agent: str | None
    reason: str


class FakeClock:
    """Tiny test clock so unit tests do not sleep."""

    def __init__(self, value: float) -> None:
        self.value = value

    def now(self) -> float:
        """Return the current fake time."""
        return self.value

    def advance(self, seconds: float) -> None:
        """Move fake time forward."""
        self.value += seconds


class InterModelInterface:
    """SQLite-backed pool for Codex, Claude, Gemini, and Antigravity."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        now=time.time,
        sprint_target: int = 30,
    ) -> None:
        self.db_path = Path(db_path)
        self.now = now
        self.sprint_target = sprint_target
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def table_names(self) -> set[str]:
        """Return table names, used by tests and diagnostics."""
        with self._connect() as db:
            rows = db.execute("select name from sqlite_master where type='table'").fetchall()
        return {_row_get(row, "name") for row in rows}

    def join(self, agent: str) -> JoinResult:
        """Join the current pool, including a sprint that is already running."""
        now = self.now()
        with self._connect(write=True) as db:
            self._start_ready_sprints(db, now)
            wave = self._joinable_wave(db, now) or self._create_wave(db, now)
            db.execute(
                """
                insert into agents(wave_id, agent, joined_at, heartbeat_at, status, status_updated_at)
                values(?, ?, ?, ?, 'active', ?)
                on conflict(wave_id, agent) do update set
                    heartbeat_at=excluded.heartbeat_at,
                    status='active',
                    detail='',
                    status_updated_at=excluded.status_updated_at
                """,
                (_row_get(wave, "id"), agent, now, now, now),
            )
            wave_id = int(_row_get(wave, "id"))
            team_size = self._team_size(db, wave_id)
        return JoinResult(
            wave_id,
            _row_get(wave, "status"),
            team_size,
            _row_get(wave, "gate_closes_at"),
            f"{agent} joined sprint pool #{wave_id}.",
        )

    def start_ready_sprints(self) -> None:
        """Move pools whose 2-minute wait has ended into sprinting."""
        with self._connect(write=True) as db:
            self._start_ready_sprints(db, self.now())

    def heartbeat(self, agent: str, *, state: str = "active", detail: str = "") -> None:
        """Refresh one agent so it stays in the active pool."""
        if state not in VALID_AGENT_STATUSES or state == "stale":
            raise ValueError("state must be active, thinking, working, testing, reviewing, blocked, or possibly_idle")
        now = self.now()
        with self._connect(write=True) as db:
            wave = self._agent_wave(db, agent)
            if wave:
                db.execute(
                    """
                    update agents set heartbeat_at=?, status=?, detail=?, status_updated_at=?
                    where wave_id=? and agent=?
                    """,
                    (now, state, detail, now, _row_get(wave, "id"), agent),
                )
                db.execute(
                    """
                    update path_locks set locked_at=?, lease_expires_at=?
                    where wave_id=? and agent=?
                    """,
                    (now, now + LOCK_LEASE_SECONDS, _row_get(wave, "id"), agent),
                )

    def wave_status(self, wave_id: int) -> str | None:
        """Return one wave's status."""
        with self._connect() as db:
            row = db.execute("select status from waves where id=?", (wave_id,)).fetchone()
        return _row_get(row, "status") if row else None

    def current_wave_status(self) -> str | None:
        """Return the newest active wave status."""
        wave = self._active_wave()
        return _row_get(wave, "status") if wave else None

    def agent_names(self) -> list[str]:
        """Return all active agent names."""
        with self._connect() as db:
            rows = db.execute(
                f"select agent from agents where status in ({_sql_marks(ACTIVE_AGENT_STATUSES)}) order by agent",
                ACTIVE_AGENT_STATUSES,
            ).fetchall()
        return [_row_get(row, "agent") for row in rows]

    def agent_states(self) -> dict[str, str]:
        """Return newest known state for each visible agent."""
        with self._connect() as db:
            rows = db.execute(
                """
                select agent, status from agents
                where status != 'stale'
                order by wave_id desc, agent asc
                """
            ).fetchall()
        states: dict[str, str] = {}
        for row in rows:
            states.setdefault(_row_get(row, "agent"), _row_get(row, "status"))
        return states

    def post_message(self, agent: str, message: str) -> str:
        """Record one short message for the current coordination pool."""
        text = " ".join(message.split())[:MAX_MESSAGE_CHARS]
        if not text:
            return "Message was empty; nothing was recorded."
        now = self.now()
        with self._connect(write=True) as db:
            wave = self._active_wave_db(db) or self._create_wave(db, now)
            wave_id = int(_row_get(wave, "id"))
            db.execute(
                """
                insert into messages(wave_id, agent, body, posted_at)
                values(?, ?, ?, ?)
                """,
                (wave_id, agent, text, now),
            )
        return f"{agent} message recorded in pool #{wave_id}."

    def recent_messages(self, limit: int = 10) -> list[str]:
        """Return recent messages from the current coordination pool."""
        safe_limit = min(max(limit, 1), 50)
        with self._connect() as db:
            wave = self._active_wave_db(db)
            if not wave:
                return []
            rows = db.execute(
                """
                select agent, body from messages
                where wave_id=?
                order by posted_at desc, id desc
                limit ?
                """,
                (_row_get(wave, "id"), safe_limit),
            ).fetchall()
        return [
            f"{_row_get(row, 'agent')}: {_row_get(row, 'body')}"
            for row in reversed(rows)
        ]

    def claim_issue(self, agent: str, issue_id: int, touched_paths: list[str]) -> ClaimResult:
        """Claim one AutoIssue and lock its touched paths."""
        paths = [normalize_path(path) for path in touched_paths if normalize_path(path)]
        if not paths:
            return ClaimResult(False, None, "Claim needs at least one touched file or folder path.")
        try:
            with self._connect(write=True) as db:
                self._start_ready_sprints(db, self.now())
                wave = self._agent_sprint_wave(db, agent)
                if not wave:
                    return ClaimResult(False, None, f"{agent} has no active sprint.")
                wave_id = int(_row_get(wave, "id"))
                conflict = self._path_conflict(db, wave_id, paths)
                if conflict:
                    return ClaimResult(False, wave_id, f"Claim overlaps {conflict}.")
                self._insert_claim(db, wave_id, agent, issue_id, paths)
        except sqlite3.OperationalError as exc:
            if _is_database_busy(exc):
                return ClaimResult(False, None, "Coordination database is busy; retry in a few seconds.")
            raise
        except sqlite3.IntegrityError:
            return ClaimResult(False, None, f"AutoIssue #{issue_id} is already claimed.")
        return ClaimResult(True, wave_id, f"{agent} claimed AutoIssue #{issue_id}.")

    def add_touched_paths(
        self, agent: str, issue_id: int, touched_paths: list[str]
    ) -> ClaimResult:
        """Add extra path locks discovered after the initial claim."""
        paths = [normalize_path(path) for path in touched_paths if normalize_path(path)]
        if not paths:
            return ClaimResult(False, None, "Extra lock request needs at least one path.")
        now = self.now()
        try:
            with self._connect(write=True) as db:
                wave = self._agent_sprint_wave(db, agent)
                if not wave:
                    return ClaimResult(False, None, f"{agent} has no active sprint.")
                wave_id = int(_row_get(wave, "id"))
                claim = db.execute(
                    """
                    select * from issue_claims
                    where wave_id=? and issue_id=? and claimed_by=? and status='claimed'
                    """,
                    (wave_id, issue_id, agent),
                ).fetchone()
                if not claim:
                    return ClaimResult(False, wave_id, f"{agent} does not own AutoIssue #{issue_id}.")
                conflict = self._path_conflict(db, wave_id, paths, owner=agent, issue_id=issue_id)
                if conflict:
                    return ClaimResult(False, wave_id, f"Extra lock overlaps {conflict}.")
                existing = [line for line in _row_get(claim, "touched_paths").splitlines() if line]
                merged = list(dict.fromkeys([*existing, *paths]))
                db.execute(
                    "update issue_claims set touched_paths=? where id=?",
                    ("\n".join(merged), _row_get(claim, "id")),
                )
                for path in paths:
                    db.execute(
                        """
                        insert into path_locks(wave_id, path, issue_id, agent, locked_at, lease_expires_at)
                        values(?, ?, ?, ?, ?, ?)
                        """,
                        (wave_id, path, issue_id, agent, now, now + LOCK_LEASE_SECONDS),
                    )
        except sqlite3.OperationalError as exc:
            if _is_database_busy(exc):
                return ClaimResult(False, None, "Coordination database is busy; retry in a few seconds.")
            raise
        return ClaimResult(True, wave_id, f"{agent} added {len(paths)} extra path lock(s).")

    def mark_fixed(self, agent: str, issue_id: int) -> bool:
        """Mark a claimed issue fixed and enter review if the target is reached."""
        now = self.now()
        with self._connect(write=True) as db:
            wave = self._agent_sprint_wave(db, agent)
            if not wave:
                return False
            wave_id = int(_row_get(wave, "id"))
            result = db.execute(
                """
                update issue_claims set status='fixed', fixed_by=?, fixed_at=?
                where wave_id=? and issue_id=? and claimed_by=? and status='claimed'
                """,
                (agent, now, wave_id, issue_id, agent),
            )
            if result.rowcount == 0:
                return False
            if self._fixed_count(db, wave_id) >= self.sprint_target:
                db.execute(
                    "update waves set status='reviewing', review_closes_at=? where id=?",
                    (now + REVIEW_SECONDS, wave_id),
                )
        return True

    def review_issue(self, reviewer: str, issue_id: int, vote: str, note: str = "") -> bool:
        """Record one cross-review vote."""
        if vote not in {"pass", "needs-correction"}:
            raise ValueError("vote must be pass or needs-correction")
        with self._connect(write=True) as db:
            wave = self._agent_review_wave(db, reviewer)
            if not wave:
                return False
            wave_id = int(_row_get(wave, "id"))
            claim = self._fixed_claim(db, wave_id, issue_id)
            if not claim or _row_get(claim, "fixed_by") == reviewer:
                return False
            db.execute(
                """
                insert into reviews(wave_id, issue_id, reviewer, vote, note, reviewed_at)
                values(?, ?, ?, ?, ?, ?)
                on conflict(wave_id, issue_id, reviewer) do update set
                    vote=excluded.vote,
                    note=excluded.note,
                    reviewed_at=excluded.reviewed_at
                """,
                (wave_id, issue_id, reviewer, vote, note, self.now()),
            )
        return True

    def consensus_ready(self) -> bool:
        """Return true when review has passed, and mark the wave ready."""
        with self._connect(write=True) as db:
            wave = self._review_wave(db)
            if not wave:
                return False
            wave_id = int(_row_get(wave, "id"))
            if self._fixed_count(db, wave_id) < self.sprint_target:
                return False
            if self._has_correction_request(db, wave_id):
                return False
            if not self._all_fixed_have_peer_pass(db, wave_id):
                return False
            db.execute("update waves set status='consensus_ready' where id=?", (wave_id,))
        return True

    def cleanup_stale_agents(
        self,
        max_age_seconds: int = STALE_AGENT_SECONDS,
        idle_after_seconds: int = IDLE_AGENT_SECONDS,
    ) -> list[str]:
        """Mark idle/stale agents; only stale agents lose locks."""
        now = self.now()
        idle_cutoff = now - idle_after_seconds
        stale_cutoff = now - max_age_seconds
        with self._connect(write=True) as db:
            db.execute(
                f"""
                update agents set status='possibly_idle', status_updated_at=?
                where status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})
                    and heartbeat_at < ?
                """,
                (now, *ACTIVE_AGENT_STATUSES, idle_cutoff),
            )
            rows = db.execute(
                "select wave_id, agent from agents where status != 'stale' and heartbeat_at < ?",
                (stale_cutoff,),
            ).fetchall()
            for row in rows:
                wave_id = _row_get(row, "wave_id")
                agent = _row_get(row, "agent")
                db.execute(
                    "update agents set status='stale', status_updated_at=? where wave_id=? and agent=?",
                    (now, wave_id, agent),
                )
                db.execute(
                    "delete from path_locks where wave_id=? and agent=?",
                    (wave_id, agent),
                )
        return [_row_get(row, "agent") for row in rows]

    def recommend_commit_agent(self) -> Recommendation:
        """Recommend the live agent with the most clean fixed work."""
        with self._connect() as db:
            row = db.execute(
                f"""
                select issue_claims.fixed_by as agent, count(*) as fixed
                from issue_claims
                join agents on
                    agents.wave_id=issue_claims.wave_id
                    and agents.agent=issue_claims.fixed_by
                where issue_claims.status='fixed'
                    and issue_claims.fixed_by is not null
                    and agents.status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})
                    and not exists (
                        select 1 from reviews
                        where reviews.wave_id=issue_claims.wave_id
                            and reviews.issue_id=issue_claims.issue_id
                            and reviews.vote='needs-correction'
                    )
                group by issue_claims.fixed_by
                order by fixed desc, max(issue_claims.fixed_at) desc, issue_claims.fixed_by asc
                limit 1
                """,
                ACTIVE_AGENT_STATUSES,
            ).fetchone()
        if not row:
            return Recommendation(None, "No fixed AutoIssues are recorded yet.")
        agent = _row_get(row, "agent")
        fixed = _row_get(row, "fixed")
        return Recommendation(agent, f"{agent} fixed {fixed} issue(s).")

    def status_summary(self) -> str:
        """Plain-English summary for humans and agents."""
        with self._connect() as db:
            wave = self._active_wave_db(db)
            if not wave:
                return "No AutoIssue sprint pool is active."
            wave_id = int(_row_get(wave, "id"))
            status = _row_get(wave, "status")
            team_size = self._team_size(db, wave_id)
            fixed = self._fixed_count(db, wave_id)
            stale = db.execute(
                "select group_concat(agent, ', ') as agents from agents where wave_id=? and status='stale'",
                (wave_id,),
            ).fetchone()
            idle = db.execute(
                "select group_concat(agent, ', ') as agents from agents where wave_id=? and status='possibly_idle'",
                (wave_id,),
            ).fetchone()
            stale_agents = _row_get(stale, "agents")
            idle_agents = _row_get(idle, "agents")
            visible_agents = self._visible_agent_states_for_wave(db, wave_id)
            overrun = status == "sprinting" and self.now() > _row_get(wave, "gate_closes_at") + REVIEW_SECONDS
        parts = [f"Pool #{wave_id} is {status} with {team_size} agent(s); {fixed} fixed."]
        if visible_agents:
            parts.append(f"Agents: {visible_agents}.")
        if overrun:
            parts.append("Sprint is over its 15-minute target but keeps current claims.")
        if idle_agents:
            parts.append(f"Possibly idle: {idle_agents}.")
        if stale_agents:
            parts.append(f"Stale agents: {stale_agents}; their locks were released.")
        return " ".join(parts)

    def _visible_agent_states_for_wave(self, db: sqlite3.Connection, wave_id: int) -> str:
        rows = db.execute(
            f"""
            select agent, status from agents
            where wave_id=? and status in ({_sql_marks(VISIBLE_AGENT_STATUSES)})
            order by agent
            """,
            (wave_id, *VISIBLE_AGENT_STATUSES),
        ).fetchall()
        return ", ".join(
            f"{_row_get(row, 'agent')}={_row_get(row, 'status')}" for row in rows
        )

    @contextmanager
    def _connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=1.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("pragma foreign_keys=on")
        db.execute("pragma busy_timeout=1000")
        try:
            if write:
                db.execute("begin immediate")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self._connect(write=True) as db:
            for statement in _SCHEMA:
                db.execute(statement)
            self._migrate_schema(db)

    def _migrate_schema(self, db: sqlite3.Connection) -> None:
        """Add columns when an older runtime SQLite file already exists."""
        _ensure_column(db, "agents", "detail", "text not null default ''")
        _ensure_column(db, "agents", "status_updated_at", "real not null default 0")
        _ensure_column(db, "path_locks", "lease_expires_at", "real")
        db.execute(_MESSAGES_SCHEMA)

    def _joinable_wave(self, db: sqlite3.Connection, now: float) -> sqlite3.Row | None:
        return db.execute(
            """
            select * from waves
            where status='sprinting'
                or (status='forming' and gate_closes_at > ?)
            order by id desc limit 1
            """,
            (now,),
        ).fetchone()

    def _create_wave(self, db: sqlite3.Connection, now: float) -> sqlite3.Row:
        cur = db.execute(
            """
            insert into waves(status, gate_opened_at, gate_closes_at, sprint_target)
            values('forming', ?, ?, ?)
            """,
            (now, now + JOIN_GATE_SECONDS, self.sprint_target),
        )
        return db.execute("select * from waves where id=?", (cur.lastrowid,)).fetchone()

    def _start_ready_sprints(self, db: sqlite3.Connection, now: float) -> None:
        db.execute(
            "update waves set status='sprinting' where status='forming' and gate_closes_at <= ?",
            (now,),
        )

    def _team_size(self, db: sqlite3.Connection, wave_id: int) -> int:
        row = db.execute(
            f"select count(*) as count from agents where wave_id=? and status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})",
            (wave_id, *ACTIVE_AGENT_STATUSES),
        ).fetchone()
        return int(_row_get(row, "count"))

    def _agent_wave(self, db: sqlite3.Connection, agent: str) -> sqlite3.Row | None:
        return db.execute(
            """
            select waves.* from waves
            join agents on agents.wave_id=waves.id
            where agents.agent=? and agents.status != 'stale'
            order by waves.id desc limit 1
            """,
            (agent,),
        ).fetchone()

    def _agent_sprint_wave(self, db: sqlite3.Connection, agent: str) -> sqlite3.Row | None:
        return db.execute(
            f"""
            select waves.* from waves
            join agents on agents.wave_id=waves.id
            where agents.agent=? and agents.status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})
                and waves.status='sprinting'
            order by waves.id desc limit 1
            """,
            (agent, *ACTIVE_AGENT_STATUSES),
        ).fetchone()

    def _agent_review_wave(self, db: sqlite3.Connection, agent: str) -> sqlite3.Row | None:
        return db.execute(
            f"""
            select waves.* from waves
            join agents on agents.wave_id=waves.id
            where agents.agent=? and agents.status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})
                and waves.status='reviewing'
            order by waves.id desc limit 1
            """,
            (agent, *ACTIVE_AGENT_STATUSES),
        ).fetchone()

    def _active_wave(self) -> sqlite3.Row | None:
        with self._connect() as db:
            return self._active_wave_db(db)

    def _active_wave_db(self, db: sqlite3.Connection) -> sqlite3.Row | None:
        return db.execute(
            """
            select * from waves
            where status in ('forming', 'sprinting', 'reviewing', 'consensus_ready')
            order by id desc limit 1
            """
        ).fetchone()

    def _review_wave(self, db: sqlite3.Connection) -> sqlite3.Row | None:
        return db.execute(
            "select * from waves where status='reviewing' order by id desc limit 1"
        ).fetchone()

    def _path_conflict(
        self, db: sqlite3.Connection, wave_id: int, touched_paths: list[str],
        *, owner: str | None = None, issue_id: int | None = None
    ) -> str | None:
        rows = db.execute(
            """
            select path, agent, issue_id from path_locks
            where wave_id=? and (lease_expires_at is null or lease_expires_at > ?)
            """,
            (wave_id, self.now()),
        ).fetchall()
        for row in rows:
            if owner and issue_id and _row_get(row, "agent") == owner and _row_get(row, "issue_id") == issue_id:
                continue
            for path in touched_paths:
                locked_path = _row_get(row, "path")
                if paths_overlap(locked_path, path):
                    return locked_path
        return None

    def _insert_claim(
        self, db: sqlite3.Connection, wave_id: int, agent: str, issue_id: int,
        touched_paths: list[str]
    ) -> None:
        db.execute(
            """
            insert into issue_claims(wave_id, issue_id, status, claimed_by, claimed_at, touched_paths)
            values(?, ?, 'claimed', ?, ?, ?)
            """,
            (wave_id, issue_id, agent, self.now(), "\n".join(touched_paths)),
        )
        for path in touched_paths:
            db.execute(
                """
                insert into path_locks(wave_id, path, issue_id, agent, locked_at, lease_expires_at)
                values(?, ?, ?, ?, ?, ?)
                """,
                (wave_id, normalize_path(path), issue_id, agent, self.now(), self.now() + LOCK_LEASE_SECONDS),
            )

    def _fixed_count(self, db: sqlite3.Connection, wave_id: int) -> int:
        row = db.execute(
            "select count(*) as count from issue_claims where wave_id=? and status='fixed'",
            (wave_id,),
        ).fetchone()
        return int(_row_get(row, "count"))

    def _has_correction_request(self, db: sqlite3.Connection, wave_id: int) -> bool:
        row = db.execute(
            """
            select 1 from reviews
            join issue_claims on
                issue_claims.wave_id=reviews.wave_id
                and issue_claims.issue_id=reviews.issue_id
            where reviews.wave_id=?
                and reviews.vote='needs-correction'
                and issue_claims.status='fixed'
            limit 1
            """,
            (wave_id,),
        ).fetchone()
        return row is not None

    def _fixed_claim(
        self, db: sqlite3.Connection, wave_id: int, issue_id: int
    ) -> sqlite3.Row | None:
        return db.execute(
            """
            select * from issue_claims
            where wave_id=? and issue_id=? and status='fixed' and fixed_by is not null
            """,
            (wave_id, issue_id),
        ).fetchone()

    def _all_fixed_have_peer_pass(self, db: sqlite3.Connection, wave_id: int) -> bool:
        rows = db.execute(
            "select issue_id, fixed_by from issue_claims where wave_id=? and status='fixed'",
            (wave_id,),
        ).fetchall()
        for row in rows:
            if not self._has_required_peer_passes(
                db,
                wave_id,
                _row_get(row, "issue_id"),
                _row_get(row, "fixed_by"),
            ):
                return False
        return True

    def _has_required_peer_passes(
        self, db: sqlite3.Connection, wave_id: int, issue_id: int, fixed_by: str
    ) -> bool:
        wave = db.execute("select * from waves where id=?", (wave_id,)).fetchone()
        peer_count = self._active_peer_count(db, wave_id, fixed_by)
        required = min(2, peer_count)
        review_closes_at = _row_get(wave, "review_closes_at") if wave else None
        if review_closes_at and self.now() > review_closes_at:
            required = min(1, peer_count)
        if required == 0:
            return False
        row = db.execute(
            """
            select count(distinct reviewer) as passes from reviews
            where wave_id=? and issue_id=? and vote='pass' and reviewer != ?
            """,
            (wave_id, issue_id, fixed_by),
        ).fetchone()
        return int(_row_get(row, "passes")) >= required

    def _active_peer_count(self, db: sqlite3.Connection, wave_id: int, fixed_by: str) -> int:
        row = db.execute(
            f"""
            select count(*) as count from agents
            where wave_id=? and agent != ? and status in ({_sql_marks(ACTIVE_AGENT_STATUSES)})
            """,
            (wave_id, fixed_by, *ACTIVE_AGENT_STATUSES),
        ).fetchone()
        return int(_row_get(row, "count"))


def normalize_path(path: str) -> str:
    """Normalize a repo path for path-lock comparison."""
    return path.replace("\\", "/").strip().strip("/")


def paths_overlap(left: str, right: str) -> bool:
    """Return true when two file or folder paths overlap."""
    a = normalize_path(left)
    b = normalize_path(right)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _is_database_busy(exc: sqlite3.OperationalError) -> bool:
    """Return true for SQLite write-lock contention errors."""
    return "locked" in str(exc).lower() or "busy" in str(exc).lower()


def _row_get(row: sqlite3.Row, key: str):
    """Return a SQLite row value using exact key casing."""
    return dict(row)[key]


def _sql_marks(values: tuple[str, ...]) -> str:
    """Return SQLite placeholders for an IN clause."""
    return ", ".join("?" for _ in values)


def _ensure_column(
    db: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Add one column to a runtime SQLite table if it is missing."""
    rows = db.execute(f"pragma table_info({table})").fetchall()
    if column not in {_row_get(row, "name") for row in rows}:
        db.execute(f"alter table {table} add column {column} {definition}")


_MESSAGES_SCHEMA = """
    create table if not exists messages(
        id integer primary key autoincrement,
        wave_id integer not null references waves(id),
        agent text not null,
        body text not null,
        posted_at real not null
    )
    """


_SCHEMA = (
    """
    create table if not exists waves(
        id integer primary key autoincrement,
        status text not null,
        gate_opened_at real not null,
        gate_closes_at real not null,
        sprint_target integer not null,
        review_closes_at real
    )
    """,
    """
    create table if not exists agents(
        id integer primary key autoincrement,
        wave_id integer not null references waves(id),
        agent text not null,
        joined_at real not null,
        heartbeat_at real not null,
        status text not null,
        detail text not null default '',
        status_updated_at real not null default 0,
        unique(wave_id, agent)
    )
    """,
    """
    create table if not exists issue_claims(
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
    """,
    """
    create table if not exists path_locks(
        id integer primary key autoincrement,
        wave_id integer not null references waves(id),
        path text not null,
        issue_id integer not null,
        agent text not null,
        locked_at real not null,
        lease_expires_at real
    )
    """,
    """
    create table if not exists reviews(
        id integer primary key autoincrement,
        wave_id integer not null references waves(id),
        issue_id integer not null,
        reviewer text not null,
        vote text not null,
        note text not null default '',
        reviewed_at real not null,
        unique(wave_id, issue_id, reviewer)
    )
    """,
    _MESSAGES_SCHEMA,
)
