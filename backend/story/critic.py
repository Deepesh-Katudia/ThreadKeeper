"""Checks a draft before a human ever sees it.

Two layers: cheap rules in code (word count, dead characters showing up) and an LLM review
from a different model family that checks canon, repetition, directives and the hook.
"""

import re

from langsmith import traceable

from story import config, llm, prompts
from story.context import EpisodeContext
from story.models import Character
from story.schemas import CriticReport, Draft, Problem
from story.writer import count_words

REPEAT_SIMILARITY = 0.45


def rule_problems(draft: Draft, cast: list[Character]) -> list[Problem]:
    problems = []
    words = count_words(draft.text)
    if words < config.MIN_WORDS or words > config.MAX_WORDS:
        problems.append(Problem(
            kind="length",
            detail=f"The episode is {words} words; it must be {config.MIN_WORDS}-{config.MAX_WORDS}.",
        ))
    for person in cast:
        if person.status == "dead" and re.search(rf"\b{re.escape(person.name.split()[0])}\b", draft.text):
            problems.append(Problem(
                kind="check",
                detail=f"{person.name} died in ep {person.status_changed_in} but is named here. "
                "Fine as a memory or reference; a contradiction if they act or speak.",
            ))
    return problems


@traceable(name="review_draft")
def review_draft(story_id: int, context: EpisodeContext, draft: Draft, cast: list[Character]) -> CriticReport:
    rules = rule_problems(draft, cast)
    critic_context = context.text
    if context.earlier_episodes_index:
        critic_context += "\n\n## Earlier episodes (title and ending)\n" + context.earlier_episodes_index
    if rules:
        critic_context += "\n\n## Automatic checks flagged\n" + "\n".join(f"- {p.detail}" for p in rules)

    report = llm.write_json(
        "critic", prompts.critic_system(),
        prompts.critic_prompt(critic_context, draft.text, count_words(draft.text)),
        CriticReport, config.CRITIC_MODEL, story_id=story_id, episode=context.number,
        max_tokens=4000,
    )
    hard_rules = [p for p in rules if p.kind == "length"]
    verdict = "revise" if hard_rules else report.verdict
    return report.model_copy(update={"problems": hard_rules + report.problems, "verdict": verdict})


def needs_revision(report: CriticReport) -> bool:
    return report.verdict.strip().lower() != "pass"


def similar_earlier_episodes(summary: str, earlier: dict[int, str]) -> list[int]:
    """Numbers of earlier episodes whose summaries share most of their words with this one."""
    new_words = content_words(summary)
    hits = []
    for number, old in earlier.items():
        old_words = content_words(old)
        if not new_words or not old_words:
            continue
        overlap = len(new_words & old_words) / len(new_words | old_words)
        if overlap >= REPEAT_SIMILARITY:
            hits.append(number)
    return hits


STOPWORDS = set("""
a an the and or but of to in on at for with from by as is was were be been are it its his her
their they them he she him who that this then than into out up down over after before when while
""".split())


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOPWORDS and len(w) > 2}
