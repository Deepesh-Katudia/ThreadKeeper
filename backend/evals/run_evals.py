"""Score the written episodes of a story with LangSmith.

    python -m evals.run_evals --story 1

Uploads one example per approved episode to a LangSmith dataset, then runs five evaluators:
  word_count   400-700 words (code)
  repetition   no episode summary is a near-copy of an earlier one (code)
  hook         does the ending make you want the next episode? (LLM judge, 1-5)
  consistency  does it contradict canon established *before* it? (LLM judge, 1-5)
  directives   does it follow the editor's standing instructions in force at the time? (LLM judge, 1-5)

The judge is the critic model (a different model family from the writer).
"""

import argparse
import os

from langsmith import Client, evaluate
from pydantic import BaseModel, ConfigDict

from story import config, llm
from story.critic import similar_earlier_episodes
from story.db import session_scope
from story.models import Directive
from story.queries import all_episodes, facts, get_story

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", config.CRITIC_MODEL)


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int
    reason: str


def collect_examples(story_id: int) -> tuple[str, list[dict]]:
    """Everything each judge needs, frozen at the moment the episode was written."""
    with session_scope() as session:
        story = get_story(session, story_id)
        episodes = [e for e in all_episodes(session, story_id) if e.status == "approved"]
        all_facts = facts(session, story_id)
        directives = list(session.query(Directive).filter(Directive.story_id == story_id))
        examples = []
        for episode in episodes:
            canon = [f"{f.subject}: {f.statement}" for f in all_facts if f.source_episode < episode.number][-60:]
            in_force = [
                d.text for d in directives
                if d.given_after_episode < episode.number
                and (d.expires_after_episode == 0 or d.expires_after_episode >= episode.number)
            ]
            earlier = {e.number: e.summary for e in episodes if e.number < episode.number}
            examples.append({
                "inputs": {"story_id": story_id, "episode": episode.number, "beat": episode.beat,
                           "canon": canon, "directives": in_force, "earlier_summaries": earlier},
                "outputs": {"text": episode.text, "summary": episode.summary},
            })
        return story.title or f"story-{story_id}", examples


def upload_dataset(client: Client, name: str, examples: list[dict]):
    if client.has_dataset(dataset_name=name):
        client.delete_dataset(dataset_name=name)
    dataset = client.create_dataset(dataset_name=name, description="Approved Threadkeeper episodes")
    client.create_examples(dataset_id=dataset.id, examples=examples)
    return dataset


def judge(step: str, question: str, inputs: dict) -> Judgement:
    return llm.write_json(
        f"eval_{step}", "You are a strict, fair judge of serial fiction. Score 1-5 and explain briefly.",
        # Logged against episode 0 with an "eval_" step, so it never counts toward an episode's cost cap.
        question, Judgement, JUDGE_MODEL, story_id=inputs["story_id"], episode=0,
        max_tokens=1500,
    )


# --- Evaluators ---------------------------------------------------------------------


def word_count(outputs: dict) -> dict:
    words = len(outputs["text"].split())
    return {"key": "word_count", "score": int(config.MIN_WORDS <= words <= config.MAX_WORDS), "comment": f"{words} words"}


def repetition(inputs: dict, outputs: dict) -> dict:
    earlier = {int(k): v for k, v in inputs["earlier_summaries"].items()}
    repeats = similar_earlier_episodes(outputs["summary"], earlier)
    return {"key": "no_repetition", "score": int(not repeats), "comment": f"similar to {repeats}" if repeats else ""}


def hook(inputs: dict, outputs: dict) -> dict:
    last_lines = " ".join(outputs["text"].split()[-120:])
    result = judge("hook", f"""Here is how an episode of a daily serial ends:
<ending>{last_lines}</ending>
Score 1-5: how strongly does this ending make a reader need the next episode?
5 = a real cliffhanger earned by the scene; 1 = it just stops.""", inputs)
    return {"key": "hook", "score": result.score / 5, "comment": result.reason}


def consistency(inputs: dict, outputs: dict) -> dict:
    canon = "\n".join(f"- {line}" for line in inputs["canon"]) or "(nothing yet)"
    result = judge("consistency", f"""Canon established before this episode:
{canon}

Episode:
<episode>{outputs["text"]}</episode>

Score 1-5: 5 = fully consistent with the canon, 1 = clear contradictions (dead people acting,
facts reversed, people knowing things they couldn't). Quote any contradiction.""", inputs)
    return {"key": "consistency", "score": result.score / 5, "comment": result.reason}


def directives(inputs: dict, outputs: dict) -> dict:
    if not inputs["directives"]:
        return {"key": "follows_directives", "score": None, "comment": "no instructions in force"}
    rules = "\n".join(f"- {d}" for d in inputs["directives"])
    result = judge("directives", f"""The editor's standing instructions when this episode was written:
{rules}

Episode:
<episode>{outputs["text"]}</episode>

Score 1-5: does the episode respect every instruction? 5 = clearly, 1 = ignores them.""", inputs)
    return {"key": "follows_directives", "score": result.score / 5, "comment": result.reason}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", type=int, required=True)
    args = parser.parse_args()

    title, examples = collect_examples(args.story)
    if not examples:
        raise SystemExit("No approved episodes to evaluate yet.")
    client = Client()
    dataset = upload_dataset(client, f"threadkeeper-{args.story}-{title}"[:100], examples)

    results = evaluate(
        lambda inputs: next(e["outputs"] for e in examples if e["inputs"]["episode"] == inputs["episode"]),
        data=dataset.name,
        evaluators=[word_count, repetition, hook, consistency, directives],
        experiment_prefix=f"threadkeeper-story-{args.story}",
        max_concurrency=4,
        client=client,
    )
    print(f"Done. Open the experiment in LangSmith: {results.experiment_name}")


if __name__ == "__main__":
    main()
