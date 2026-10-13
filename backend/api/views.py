"""Turns database rows into plain dicts for JSON responses."""

from story.models import (
    Act, Character, Directive, Episode, EpisodeVersion, Fact, Job, LLMCall, Ripple, RippleItem, Story, Thread,
)


def story_view(story: Story) -> dict:
    return {
        "id": story.id,
        "premise": story.premise,
        "title": story.title,
        "logline": story.logline,
        "setting": story.setting,
        "style_guide": story.style_guide,
        "status": story.status,
        "history_mode": story.history_mode or "repair",
        "total_episodes": story.total_episodes,
        "story_so_far": story.story_so_far,
        "story_so_far_through": story.story_so_far_through,
        "created_at": story.created_at.isoformat() if story.created_at else None,
    }


def act_view(act: Act) -> dict:
    return {
        "number": act.number, "title": act.title, "goal": act.goal,
        "turning_point": act.turning_point, "first_episode": act.first_episode,
        "last_episode": act.last_episode, "summary": act.summary,
    }


def episode_brief(episode: Episode) -> dict:
    return {
        "number": episode.number, "act_number": episode.act_number, "beat": episode.beat,
        "status": episode.status, "title": episode.title,
        "passed_critic": episode.critic_report.get("passed") if episode.critic_report else None,
        "was_edited_by_human": episode.was_edited_by_human,
        "current_version": episode.current_version,
        "continuity": episode.continuity,
    }


def episode_full(episode: Episode) -> dict:
    return {
        **episode_brief(episode),
        "text": episode.text,
        "word_count": len(episode.text.split()),
        "summary": episode.summary,
        "hook": episode.hook,
        "characters_present": episode.characters_present,
        "critic_report": episode.critic_report,
        "pending_memory": episode.pending_memory,
        "revision_count": episode.revision_count,
        "human_note": episode.human_note,
        "error": episode.error,
    }


def character_view(person: Character) -> dict:
    return {
        "id": person.id, "name": person.name, "role": person.role, "description": person.description,
        "planned_arc": person.planned_arc, "status": person.status,
        "status_changed_in": person.status_changed_in, "first_episode": person.first_episode,
        "last_seen_episode": person.last_seen_episode,
    }


def fact_view(fact: Fact) -> dict:
    return {
        "id": fact.id, "subject": fact.subject, "statement": fact.statement, "source_episode": fact.source_episode,
        "source_version": fact.source_version, "is_active": fact.is_active is not False,
        "retracted_reason": fact.retracted_reason or "", "retracted_by_ripple": fact.retracted_by_ripple,
    }


def thread_view(thread: Thread) -> dict:
    return {
        "id": thread.id, "title": thread.title, "description": thread.description,
        "opened_episode": thread.opened_episode, "payoff_episode": thread.payoff_episode,
        "status": thread.status, "resolved_episode": thread.resolved_episode,
    }


def directive_view(directive: Directive) -> dict:
    return {
        "id": directive.id, "text": directive.text, "given_after_episode": directive.given_after_episode,
        "expires_after_episode": directive.expires_after_episode, "is_active": directive.is_active,
        "replan_summary": directive.replan_summary,
        "beat_changes": directive.beat_changes or [],
    }


def job_view(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id, "story_id": job.story_id, "kind": job.kind, "status": job.status,
        "detail": job.detail, "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def call_view(call: LLMCall) -> dict:
    return {
        "id": call.id, "episode_number": call.episode_number, "step": call.step, "model": call.model,
        "input_tokens": call.input_tokens, "output_tokens": call.output_tokens,
        "cache_read_tokens": call.cache_read_tokens, "cost_usd": call.cost_usd,
        "latency_ms": call.latency_ms, "succeeded": call.succeeded, "error": call.error,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


def version_view(row: EpisodeVersion, current: int | None) -> dict:
    return {
        "version": row.version, "title": row.title, "text": row.text, "source": row.source, "note": row.note,
        "ripple_id": row.ripple_id, "is_current": row.version == current, "is_pending": row.memory is None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def ripple_item_view(item: RippleItem) -> dict:
    return {
        "episode_number": item.episode_number, "check_status": item.check_status,
        "signals": item.signals or {"reasons": [], "verdict": None}, "conflicts": item.conflicts or [],
        "proposal": item.proposal, "decision": item.decision, "decision_note": item.decision_note,
        "resulting_version": item.resulting_version,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
    }


def ripple_view(ripple: Ripple, items: list[RippleItem]) -> dict:
    record = ripple.memory_diff or {}
    return {
        "id": ripple.id, "source_episode": ripple.source_episode,
        "from_version": ripple.from_version, "to_version": ripple.to_version,
        "status": ripple.status, "is_restore": bool(record.get("restore_version")),
        "diff": record.get("diff"), "change": record.get("change"),
        "replan": ripple.replan, "summary": ripple.summary, "cost_usd": round(ripple.cost_usd or 0.0, 4),
        "items": [ripple_item_view(i) for i in items], "counts": item_counts(items),
        "created_at": ripple.created_at.isoformat() if ripple.created_at else None,
        "closed_at": ripple.closed_at.isoformat() if ripple.closed_at else None,
    }


def ripple_brief(ripple: Ripple | None, items: list[RippleItem]) -> dict | None:
    if ripple is None:
        return None
    return {
        "id": ripple.id, "status": ripple.status, "source_episode": ripple.source_episode,
        "from_version": ripple.from_version, "to_version": ripple.to_version,
        "counts": item_counts(items), "summary": ripple.summary,
    }


def item_counts(items: list[RippleItem]) -> dict:
    """How many later episodes are in each state; "waiting" means a human decision is needed."""
    counts = {"pending": 0, "unaffected": 0, "minor": 0, "major": 0, "recheck": 0, "decided": 0, "waiting": 0}
    for item in items:
        counts[item.check_status] = counts.get(item.check_status, 0) + 1
        if item.decision:
            counts["decided"] += 1
        elif item.check_status != "unaffected":
            counts["waiting"] += 1
    return counts
