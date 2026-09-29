"""Drafting and revising episode prose."""

from langsmith import traceable

from story import config, llm, prompts
from story.context import EpisodeContext
from story.schemas import CriticReport, Draft


@traceable(name="draft_episode")
def draft_episode(story_id: int, context: EpisodeContext, editor_note: str = "") -> Draft:
    return llm.write_json(
        "draft", context.system,
        prompts.draft_prompt(context.text, context.number, editor_note),
        Draft, config.WRITER_MODEL, story_id=story_id, episode=context.number,
    )


@traceable(name="revise_episode")
def revise_episode(story_id: int, context: EpisodeContext, draft: Draft, report: CriticReport) -> Draft:
    return llm.write_json(
        "revise", context.system,
        prompts.revise_prompt(context.text, draft.text, report),
        Draft, config.WRITER_MODEL, story_id=story_id, episode=context.number,
    )


def count_words(text: str) -> int:
    return len(text.split())
