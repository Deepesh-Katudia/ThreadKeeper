"""Which later episodes does an edit affect? Checked in three tiers, cheapest first.

1. Code only, free. An episode is suspicious if its writer was shown canon the edit changed
   (`episodes.context_ids`), or its text mentions what was retracted or who was removed. The
   episode right after the edit is always checked: the handoff is where continuity breaks first.
   Anything without a signal is marked unaffected and costs nothing.
2. A cheap critic call per suspicious episode (`ripple_check`), returning quotes. A quote that isn't
   really in the text is dropped, so every flag points at words a human can see.
3. A writer call (`ripple_patch`) proposing the smallest sentence-level edits. Code applies them
   only if each passage occurs exactly once and the length stays in bounds; otherwise the human
   is offered a rewrite instead. Patches are proposals until the human accepts them.

Everything stops at RIPPLE_COST_CAP_USD; what wasn't checked stays "pending" and says so.
"""

import re
from datetime import datetime

from langsmith import traceable
from sqlalchemy import func, select

from story import config, llm, prompts
from story.context import describe_main_cast
from story.critic import content_words
from story.models import Episode, LLMCall, Ripple
from story.db import session_scope
from story.queries import characters, episode_facts, facts, find_character, get_story, threads
from story.schemas import ContinuityCheck, Patch
from story.writer import count_words


# --- What changed, in plain lines ----------------------------------------------------


def describe_change(session, story_id: int, number: int, diff) -> dict:
    """The diff with names and statements filled in, captured before it is applied (removed rows vanish)."""
    own = {f.id: f for f in episode_facts(session, story_id, number, active_only=False)}
    cast = {c.id: c for c in characters(session, story_id)}
    all_threads = {t.id: t for t in threads(session, story_id)}

    def thread_rows(ids, what):
        return [{"id": i, "title": all_threads[i].title, "change": what} for i in ids if i in all_threads]

    return {
        "retracted": [
            {"id": i, "subject": own[i].subject, "statement": own[i].statement} for i in diff.retract_fact_ids if i in own
        ],
        "added": [{"subject": f.subject, "statement": f.statement} for f in diff.new_facts],
        "removed_characters": [{"id": i, "name": cast[i].name} for i in diff.remove_character_ids if i in cast],
        "new_characters": [c.name for c in diff.new_characters],
        "status_changes": [{"name": c.name, "status": c.new_status} for c in diff.character_changes],
        "changed_character_ids": [
            person.id for person in (find_character(session, story_id, c.name) for c in diff.character_changes) if person
        ],
        "threads": (
            thread_rows(diff.remove_thread_ids, "removed") + thread_rows(diff.resolve_thread_ids, "resolved")
            + thread_rows(diff.reopen_thread_ids, "reopened")
        ) + [{"id": None, "title": t.title, "change": "opened"} for t in diff.threads_opened],
    }


def change_lines(number: int, change: dict) -> str:
    lines = [f"No longer true (ep {number}): {r['subject']}: {r['statement']}" for r in change["retracted"]]
    lines += [f"Now true (ep {number}): {a['subject']}: {a['statement']}" for a in change["added"]]
    lines += [f"No longer in episode {number}: {r['name']}" for r in change["removed_characters"]]
    lines += [f"{s['name']} is now {s['status']} as of episode {number}" for s in change["status_changes"]]
    lines += [f"Thread \"{t['title']}\" {t['change']} in episode {number}" for t in change["threads"]]
    return "\n".join(lines) or f"Episode {number} was reworded; no recorded facts changed."


def changes_anything(change: dict) -> bool:
    return any(change.get(key) for key in (
        "retracted", "added", "removed_characters", "new_characters", "status_changes", "threads",
    ))


# --- Tier 1: signals, in code -------------------------------------------------------


def signals_for(episode: Episode, source_number: int, change: dict) -> list[str]:
    """Reasons to suspect this episode, or [] if there are none. No model call."""
    reasons = []
    if episode.number == source_number + 1:
        reasons.append("next episode after the edit (handoff and opening line)")
    reasons += context_signals(episode.context_ids or {}, change)
    text = f"{episode.text}\n{episode.summary}"
    for row in change["retracted"]:
        if mentions_statement(text, row["subject"], row["statement"]):
            reasons.append(f"mentions \"{row['statement']}\"")
        elif not episode.context_ids and row["statement"] in context_sent(episode):
            reasons.append(f"its writer was shown \"{row['statement']}\"")
    for row in change["removed_characters"]:
        if names_person(text, row["name"]):
            reasons.append(f"mentions {row['name']}, who is no longer in episode {source_number}")
    return reasons


def context_signals(ids: dict, change: dict) -> list[str]:
    reasons = []
    retracted = {r["id"] for r in change["retracted"]}
    for fact_id in set(ids.get("facts", [])) & retracted:
        reasons.append(f"its writer used retracted fact #{fact_id}")
    people = {r["id"] for r in change["removed_characters"]} | set(change.get("changed_character_ids", []))
    if set(ids.get("characters", [])) & people:
        reasons.append("its writer was shown a character the edit changed")
    threads = {t["id"] for t in change["threads"] if t["id"]}
    if set(ids.get("threads", [])) & threads:
        reasons.append("its writer was shown a thread the edit changed")
    return reasons


def key_terms(text: str) -> set[str]:
    """Content words plus numbers: "locker 214" has to match on 214, not just on "locker"."""
    return content_words(text) | set(re.findall(r"\d+", text))


def mentions_statement(text: str, subject: str, statement: str) -> bool:
    terms = key_terms(f"{subject} {statement}")
    if not terms:
        return False
    found = key_terms(text) & terms
    return len(found) >= min(2, len(terms))


def names_person(text: str, name: str) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", text, flags=re.IGNORECASE) for n in {name, name.split()[0]})


def context_sent(episode: Episode) -> str:
    sent = (episode.critic_report or {}).get("context_sent") or {}
    return "\n".join(sent.values()) if isinstance(sent, dict) else str(sent)


# --- Tier 2 and 3: model calls ------------------------------------------------------------


@traceable(name="ripple_check")
def check_episode(story_id: int, number: int, text: str, change_text: str, canon_text: str) -> tuple[str, list[dict]]:
    """Ask the critic model whether this episode contradicts the change. Returns (verdict, real conflicts)."""
    result = llm.write_json(
        "ripple_check", prompts.critic_system(),
        prompts.ripple_check_prompt(change_text, canon_text, number, text),
        ContinuityCheck, config.CRITIC_MODEL, story_id=story_id, episode=number, max_tokens=3000,
    )
    conflicts = [c.model_dump() for c in result.conflicts if c.quote.strip() and c.quote in text]
    verdict = result.verdict.strip().lower()
    if not conflicts or verdict not in ("minor", "major"):
        return "unaffected", []  # only act on words we can point to
    return verdict, conflicts


@traceable(name="ripple_patch")
def propose_patch(story_id: int, episode: dict, change_text: str, conflicts: list[dict]) -> dict:
    """The smallest fix the writer model can find, applied in code only if it applies cleanly."""
    with session_scope() as session:
        story = get_story(session, story_id)
        system = prompts.writer_system(story, describe_main_cast(characters(session, story_id)))
    conflicts_text = "\n".join(f"- \"{c['quote']}\": {c['reason']}" for c in conflicts)
    patch = llm.write_json(
        "ripple_patch", system, prompts.ripple_patch_prompt(change_text, conflicts_text, episode["number"], episode["text"]),
        Patch, config.WRITER_MODEL, story_id=story_id, episode=episode["number"], max_tokens=4000,
    )
    edits = [e.model_dump() for e in patch.edits]
    patched = apply_patch(episode["text"], edits)
    if patched is None:
        return {"kind": "rewrite", "edits": edits, "text": "", "title": "", "note": "The suggested edits didn't apply cleanly."}
    return {"kind": "patch", "edits": edits, "text": patched, "title": episode["title"], "note": patch.note}


def apply_patch(text: str, edits: list[dict]) -> str | None:
    """Apply find/replace edits, or None if any passage isn't there exactly once or the length breaks."""
    if not edits:
        return None
    for edit in edits:
        if not edit["find"] or text.count(edit["find"]) != 1:
            return None
        text = text.replace(edit["find"], edit["replace"])
    return text if config.MIN_WORDS <= count_words(text) <= config.MAX_WORDS else None


def canon_between(session, story_id: int, first: int, last: int) -> str:
    """Active facts from the edited episode up to (not including) the episode being checked."""
    rows = [f for f in facts(session, story_id) if first <= f.source_episode < last][-config.MAX_FACTS_IN_CONTEXT:]
    return "\n".join(f"- (ep {f.source_episode}) {f.subject}: {f.statement}" for f in rows) or "(none)"


# --- Cost ---------------------------------------------------------------------------------


def ripple_cost(session, ripple: Ripple) -> float:
    """Dollars spent on ripple_ steps since this ripple started."""
    since: datetime = ripple.created_at
    total = session.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
        LLMCall.story_id == ripple.story_id, LLMCall.step.like("ripple_%"), LLMCall.created_at >= since,
    ))
    return float(total or 0.0)
