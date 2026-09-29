"""Database tables.

The arc plan is not a separate table: every episode row exists from the moment the arc is
planned, holding its one-line beat, and fills in with text once it is written. That way
"what's planned" and "what's written" can never drift apart.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    premise: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200), default="")
    logline: Mapped[str] = mapped_column(Text, default="")
    setting: Mapped[str] = mapped_column(Text, default="")
    style_guide: Mapped[str] = mapped_column(Text, default="")
    # planning -> arc_review -> writing -> finished  (or planning_failed)
    status: Mapped[str] = mapped_column(String(30), default="planning")
    total_episodes: Mapped[int] = mapped_column(Integer, default=200)
    story_so_far: Mapped[str] = mapped_column(Text, default="")
    story_so_far_through: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    turning_point: Mapped[str] = mapped_column(Text, default="")
    first_episode: Mapped[int] = mapped_column(Integer)
    last_episode: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default="")


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    act_number: Mapped[int] = mapped_column(Integer)
    beat: Mapped[str] = mapped_column(Text)
    # planned -> drafting -> in_review -> approved   (failed / stale send it back to be rewritten)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    title: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    characters_present: Mapped[list] = mapped_column(JSON, default=list)
    critic_report: Mapped[dict] = mapped_column(JSON, default=dict)
    pending_memory: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    human_note: Mapped[str] = mapped_column(Text, default="")
    was_edited_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60), default="supporting")
    description: Mapped[str] = mapped_column(Text, default="")
    planned_arc: Mapped[str] = mapped_column(Text, default="")
    # alive / dead / missing / unknown
    status: Mapped[str] = mapped_column(String(20), default="alive")
    status_changed_in: Mapped[int] = mapped_column(Integer, default=0)
    first_episode: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_episode: Mapped[int] = mapped_column(Integer, default=0)


class Fact(Base):
    """A piece of canon. Keyed by the episode it came from so history can be re-written."""

    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    subject: Mapped[str] = mapped_column(String(120))
    statement: Mapped[str] = mapped_column(Text)
    source_episode: Mapped[int] = mapped_column(Integer, index=True)


class Thread(Base):
    """An open question or promise the story has made to the reader."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    opened_episode: Mapped[int] = mapped_column(Integer, default=0)
    payoff_episode: Mapped[int] = mapped_column(Integer, default=0)
    # planned (from the arc, not on the page yet) / open / resolved
    status: Mapped[str] = mapped_column(String(20), default="planned")
    resolved_episode: Mapped[int] = mapped_column(Integer, default=0)


class Directive(Base):
    """Human feedback that should keep shaping the story, not just fix one episode."""

    __tablename__ = "directives"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    given_after_episode: Mapped[int] = mapped_column(Integer, default=0)
    # 0 means "for the rest of the story"
    expires_after_episode: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    replan_summary: Mapped[str] = mapped_column(Text, default="")
    # [{"episode": 7, "before": "...", "after": "..."}]: proof the feedback reached future episodes
    beat_changes: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LLMCall(Base):
    """One row per model call: the trace we show on the Costs page."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    episode_number: Mapped[int] = mapped_column(Integer, index=True, default=0)
    step: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Evaluation(Base):
    """One LangSmith experiment run over a story's approved episodes."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(Integer, index=True)
    experiment_name: Mapped[str] = mapped_column(String(200), default="")
    experiment_url: Mapped[str] = mapped_column(Text, default="")
    episodes_scored: Mapped[int] = mapped_column(Integer, default=0)
    # {"hook": 0.8, "consistency": 0.9, ...}: the average of each evaluator, 0..1
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    # [{"episode": 3, "hook": 0.8, ..., "comments": {"hook": "..."}}, ...]
    per_episode: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    """A background task (planning the arc, writing an episode) the frontend can poll."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    # running / done / failed
    status: Mapped[str] = mapped_column(String(20), default="running")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
