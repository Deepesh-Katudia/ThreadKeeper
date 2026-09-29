"""Shapes of the JSON we ask models to return.

`extra="forbid"` makes the JSON schema strict (additionalProperties: false), which both
Anthropic structured outputs and OpenRouter's strict mode expect.
"""

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Arc planning ----------------------------------------------------------


class PlannedCharacter(Strict):
    name: str
    role: str  # protagonist / antagonist / supporting / minor
    description: str
    planned_arc: str


class PlannedAct(Strict):
    number: int
    title: str
    goal: str
    turning_point: str
    first_episode: int
    last_episode: int


class PlannedThread(Strict):
    title: str
    description: str
    opened_episode: int
    payoff_episode: int


class StoryBible(Strict):
    title: str
    logline: str
    setting: str
    style_guide: str
    characters: list[PlannedCharacter]
    acts: list[PlannedAct]
    threads: list[PlannedThread]


class PlannedBeat(Strict):
    episode: int
    beat: str


class ActBeats(Strict):
    beats: list[PlannedBeat]


class Replan(Strict):
    beats: list[PlannedBeat]
    what_changed: str


# --- Writing and reviewing ---------------------------------------------------


class Draft(Strict):
    title: str
    text: str


class Problem(Strict):
    kind: str  # contradiction / repetition / directive / pacing / hook / style
    detail: str


class CriticReport(Strict):
    problems: list[Problem]
    hook_score: int  # 1-5: does the final beat make you need the next episode?
    follows_beat: bool
    verdict: str  # "pass" or "revise"
    advice: str


# --- Memory -------------------------------------------------------------------


class NewCharacter(Strict):
    name: str
    role: str
    description: str


class CharacterChange(Strict):
    name: str
    new_status: str  # alive / dead / missing / unknown
    reason: str


class NewFact(Strict):
    subject: str
    statement: str


class ThreadOpened(Strict):
    title: str
    description: str


class MemoryUpdate(Strict):
    summary: str
    hook: str
    characters_present: list[str]
    new_characters: list[NewCharacter]
    character_changes: list[CharacterChange]
    new_facts: list[NewFact]
    threads_opened: list[ThreadOpened]
    threads_resolved: list[str]


class Recap(Strict):
    text: str
