"""Driving a whole ripple review from a test, the way a human would from the dashboard."""

from story import pipeline, ripple
from story.db import session_scope


def edit_and_confirm(story_id: int, number: int, text: str) -> int:
    """Edit an approved episode, confirm the memory diff as proposed, and run the scan."""
    ripple_id = pipeline.edit_episode(story_id, number, text)
    ripple.confirm_memory(story_id, ripple_id)
    ripple.scan(story_id, ripple_id)
    return ripple_id


def close(story_id: int, ripple_id: int, decision: str = "keep") -> None:
    """Decide every waiting episode the same way, then approve the proposed beats."""
    while True:
        with session_scope() as session:
            waiting = [i.episode_number for i in ripple.items_of(session, ripple_id) if ripple.needs_decision(i)]
        if not waiting:
            break
        ripple.decide_item(story_id, ripple_id, waiting[0], decision)
    ripple.approve_replan(story_id, ripple_id)


def edit_through_ripple(story_id: int, number: int, text: str) -> int:
    ripple_id = edit_and_confirm(story_id, number, text)
    close(story_id, ripple_id)
    return ripple_id
