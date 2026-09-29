"""Test setup: a fresh SQLite file per test and a fake model that never costs money."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from story import db, llm  # noqa: E402
from story.schemas import (  # noqa: E402
    ActBeats, CriticReport, Draft, MemoryUpdate, PlannedAct, PlannedBeat, PlannedCharacter,
    PlannedThread, Problem, Recap, Replan, StoryBible, NewFact, CharacterChange,
)


class FakeModel:
    """Answers each kind of request with something plausible, and remembers every prompt."""

    def __init__(self):
        self.prompts: list[tuple[str, str]] = []  # (schema name, prompt)
        self.critic_verdicts: list[str] = []  # queue of verdicts; "pass" once it runs out
        self.deaths: dict[int, str] = {}  # episode number -> name of someone who dies in it

    def __call__(self, system, prompt, model, max_tokens, schema):
        self.prompts.append((schema.__name__ if schema else "text", prompt))
        answer = getattr(self, f"answer_{schema.__name__}")(prompt)
        return answer, llm.Usage(input_tokens=1000, output_tokens=200)

    def answer_StoryBible(self, prompt):
        total = int(re.search(r"Plan a (\d+)-episode", prompt).group(1))
        size = total // 8
        acts = [
            PlannedAct(number=i + 1, title=f"Act {i + 1}", goal=f"goal {i + 1}", turning_point=f"turn {i + 1}",
                       first_episode=i * size + 1, last_episode=(i + 1) * size)
            for i in range(8)
        ]
        return StoryBible(
            title="Last Drop", logline="A rider delivers to the dead.", setting="Mumbai, monsoon.",
            style_guide="Close third person, present tense.",
            characters=[
                PlannedCharacter(name="Ravi Menon", role="protagonist", description="delivery rider", planned_arc="learns"),
                PlannedCharacter(name="Asha Rao", role="antagonist", description="building manager", planned_arc="falls"),
                PlannedCharacter(name="Mr Das", role="supporting", description="old tenant", planned_arc="dies"),
            ],
            acts=acts,
            threads=[PlannedThread(title="Who ordered the parcels", description="?", opened_episode=1, payoff_episode=total)],
        )

    def answer_ActBeats(self, prompt):
        first, last = map(int, re.search(r"numbered (\d+) to (\d+)", prompt).groups())
        return ActBeats(beats=[PlannedBeat(episode=n, beat=f"beat {n}") for n in range(first, last + 1)])

    def answer_Replan(self, prompt):
        numbers = [int(n) for n in re.findall(r"^(\d+)\. ", prompt, flags=re.MULTILINE)]
        return Replan(beats=[PlannedBeat(episode=n, beat=f"replanned beat {n}") for n in numbers],
                      what_changed="Moved things around.")

    def answer_Draft(self, prompt):
        number = int(re.search(r"THIS EPISODE \(ep (\d+)\)", prompt).group(1))
        body = " ".join(["Ravi rode through the rain."] * 90)  # 450 words
        return Draft(title=f"Episode {number}", text=f"{body} Episode {number} ends at a door.")

    def answer_CriticReport(self, prompt):
        verdict = self.critic_verdicts.pop(0) if self.critic_verdicts else "pass"
        problems = [] if verdict == "pass" else [Problem(kind="hook", detail="weak ending")]
        return CriticReport(problems=problems, hook_score=4, follows_beat=True, verdict=verdict, advice="ok")

    def answer_MemoryUpdate(self, prompt):
        number = int(re.search(r"Episode (\d+):", prompt).group(1))
        changes = []
        if number in self.deaths:
            changes = [CharacterChange(name=self.deaths[number], new_status="dead", reason="fell")]
        return MemoryUpdate(
            summary=f"In episode {number} unique-event-{number} happened to someone new-{number * 7}.",
            hook=f"hook {number}", characters_present=["Ravi Menon"], new_characters=[],
            character_changes=changes,
            new_facts=[NewFact(subject="Ravi Menon", statement=f"fact from episode {number}")],
            threads_opened=[], threads_resolved=[],
        )

    def answer_Recap(self, prompt):
        return Recap(text="Recap of everything so far.")

    def prompts_for(self, schema_name: str) -> list[str]:
        return [p for name, p in self.prompts if name == schema_name]


@pytest.fixture
def fake_model(monkeypatch, tmp_path):
    db.use_database(f"sqlite:///{tmp_path / 'test.db'}")
    fake = FakeModel()
    monkeypatch.setattr(llm, "_call_anthropic", fake)
    monkeypatch.setattr(llm, "_call_openrouter", fake)
    return fake
