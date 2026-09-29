"""Turns database rows into plain dicts for JSON responses."""

from story.models import Act, Character, Directive, Episode, Fact, Job, LLMCall, Story, Thread


def story_view(story: Story) -> dict:
    return {
        "id": story.id,
        "premise": story.premise,
        "title": story.title,
        "logline": story.logline,
        "setting": story.setting,
        "style_guide": story.style_guide,
        "status": story.status,
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
    return {"id": fact.id, "subject": fact.subject, "statement": fact.statement, "source_episode": fact.source_episode}


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
