"""Export a story as readable Markdown for reviewers.

    python -m tools.export_demo --story 1 --out ../docs/demo

Writes four files:
  arc.md            the full plan: bible, cast, acts, all beats, threads
  episodes.md       every approved episode with its review data
  interventions.md  every human intervention and what it changed afterwards
  run-stats.md      measured cost, tokens, latency and evaluation scores
"""

import argparse
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from story import config
from story.db import create_tables, session_scope
from story.models import Directive, Evaluation, LLMCall
from story.queries import acts, all_episodes, characters, get_story, threads


def export(story_id: int, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as session:
        data = {
            "story": get_story(session, story_id),
            "acts": acts(session, story_id),
            "episodes": all_episodes(session, story_id),
            "cast": characters(session, story_id),
            "threads": threads(session, story_id),
            "directives": list(session.scalars(select(Directive).where(Directive.story_id == story_id).order_by(Directive.id))),
            "calls": list(session.scalars(select(LLMCall).where(LLMCall.story_id == story_id).order_by(LLMCall.id))),
            "evaluations": list(session.scalars(select(Evaluation).where(Evaluation.story_id == story_id).order_by(Evaluation.id.desc()))),
        }
        files = {
            "arc.md": arc_markdown(data),
            "episodes.md": episodes_markdown(data),
            "interventions.md": interventions_markdown(data),
            "run-stats.md": stats_markdown(data),
        }
    written = []
    for name, text in files.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


# --- arc.md -----------------------------------------------------------------------


def arc_markdown(data) -> str:
    story = data["story"]
    lines = [
        f"# {story.title}: arc plan ({story.total_episodes} episodes)",
        "",
        f"**Premise:** {story.premise}",
        "",
        f"**Logline:** {story.logline}",
        "",
        "## Setting and rules of the world",
        "",
        story.setting,
        "",
        "## House style",
        "",
        story.style_guide,
        "",
        "## Characters",
        "",
    ]
    for person in data["cast"]:
        origin = "planned" if person.first_episode == 0 else f"introduced in ep {person.first_episode}"
        status = person.status if person.status == "alive" else f"{person.status} (ep {person.status_changed_in})"
        lines.append(f"- **{person.name}** ({person.role}, {origin}, {status}): {person.description}")
        if person.planned_arc:
            lines.append(f"  - *Planned arc:* {person.planned_arc}")
    lines += ["", "## Threads", "", "| Thread | Opens | Pays off | Status |", "|---|---|---|---|"]
    for thread in data["threads"]:
        payoff = f"ep {thread.resolved_episode} ✓" if thread.resolved_episode else (f"planned ep {thread.payoff_episode}" if thread.payoff_episode else "-")
        lines.append(f"| **{cell(thread.title)}**: {cell(thread.description)} | {thread.opened_episode or '-'} | {payoff} | {thread.status} |")

    episodes_by_act = defaultdict(list)
    for episode in data["episodes"]:
        episodes_by_act[episode.act_number].append(episode)
    lines += ["", "## Acts and episode beats", "", "✓ = written and approved. Beats marked *(re-planned)* were changed by human feedback.", ""]
    replanned = {change["episode"] for d in data["directives"] for change in (d.beat_changes or [])}
    for act in data["acts"]:
        lines += [
            f"### Act {act.number}: {act.title} (episodes {act.first_episode}-{act.last_episode})",
            "",
            f"*Goal:* {act.goal}  ",
            f"*Turning point:* {act.turning_point}",
            "",
        ]
        if act.summary:
            lines += [f"*What happened:* {act.summary}", ""]
        for episode in episodes_by_act[act.number]:
            mark = "✓ " if episode.status == "approved" else ""
            title = f" **{episode.title}**:" if episode.status == "approved" and episode.title else ""
            note = " *(re-planned)*" if episode.number in replanned else ""
            lines.append(f"{episode.number}. {mark}{title} {episode.beat}{note}")
        lines.append("")
    return "\n".join(lines)


# --- episodes.md ------------------------------------------------------------------


def episodes_markdown(data) -> str:
    story = data["story"]
    approved = [e for e in data["episodes"] if e.status == "approved"]
    lines = [f"# {story.title}: episodes 1-{approved[-1].number if approved else 0}", "", f"*Premise: {story.premise}*", ""]
    for episode in approved:
        report = episode.critic_report or {}
        final = report.get("final") or {}
        facts = [
            f"{len(episode.text.split())} words",
            f"critic: {'passed' if report.get('passed') else 'flagged'}",
            f"hook {final.get('hook_score', '?')}/5",
            f"{max(0, len(report.get('attempts', [])) - 1)} revisions",
            f"${report.get('cost_usd', 0):.3f}",
        ]
        if episode.was_edited_by_human:
            facts.append("edited by a human")
        if episode.human_note:
            facts.append(f"rewritten after rejection: \"{unquote(episode.human_note)}\"")
        lines += [
            "---",
            "",
            f"## Episode {episode.number}: {episode.title}",
            "",
            f"*Beat:* {episode.beat}  ",
            f"*{' · '.join(facts)}*",
            "",
            episode.text,
            "",
        ]
    return "\n".join(lines)


# --- interventions.md ------------------------------------------------------------


def interventions_markdown(data) -> str:
    episodes = {e.number: e for e in data["episodes"]}
    lines = [
        f"# {data['story'].title}: human interventions",
        "",
        "How a human steered the story, and the evidence that it changed what came after.",
        "",
        "## Story direction (standing instructions)",
        "",
        "Each instruction is saved as a directive that every later episode prompt includes, and the next",
        "20 unwritten beats are re-planned around it.",
        "",
    ]
    if not data["directives"]:
        lines += ["*(none given)*", ""]
    for number, directive in enumerate(data["directives"], start=1):
        scope = f"until ep {directive.expires_after_episode}" if directive.expires_after_episode else "for the rest of the story"
        lines += [
            f"### {number}. \"{unquote(directive.text)}\"",
            "",
            f"Given after episode {directive.given_after_episode}, {scope}{'' if directive.is_active else ' (later retired)'}.",
            "",
            f"**What the planner changed:** {directive.replan_summary or '-'}",
            "",
        ]
        changes = directive.beat_changes or []
        if changes:
            lines += ["| Ep | Beat before | Beat after |", "|---|---|---|"]
            lines += [f"| {c['episode']} | {cell(c['before'])} | {cell(c['after'])} |" for c in changes]
            lines.append("")
        followed = [episodes[c["episode"]] for c in changes if episodes.get(c["episode"]) and episodes[c["episode"]].status == "approved"]
        if followed:
            lines += ["**Episodes written from the new beats:**", ""]
            lines += [f"- Ep {e.number} \"{e.title}\": {e.summary}" for e in followed]
            lines.append("")

    rejected = [e for e in data["episodes"] if e.human_note]
    edited = [e for e in data["episodes"] if e.was_edited_by_human]
    lines += ["## Rejected drafts (rewritten with the reviewer's note)", ""]
    lines += [f"- Ep {e.number}: \"{unquote(e.human_note)}\". Rewritten as \"{e.title}\"." for e in rejected] or ["*(none)*"]
    lines += ["", "## Episodes edited by a human", ""]
    lines += [f"- Ep {e.number} \"{e.title}\": its memory (facts, deaths, threads) was re-extracted from the edited text." for e in edited] or ["*(none)*"]

    decided = [e for e in data["episodes"] if e.status == "approved" and "passed" in (e.critic_report or {})]
    if decided:
        agree = sum(1 for e in decided if e.critic_report.get("passed") == (not e.was_edited_by_human))
        lines += [
            "",
            "## Critic vs human",
            "",
            f"The critic agreed with the human on {agree} of {len(decided)} approved episodes "
            "(passed what the human approved unchanged, or flagged what the human edited).",
        ]
    lines.append("")
    return "\n".join(lines)


# --- run-stats.md ------------------------------------------------------------------


def stats_markdown(data) -> str:
    calls = data["calls"]
    approved = [e for e in data["episodes"] if e.status == "approved"]
    by_episode = defaultdict(lambda: {"cost": 0.0, "ms": 0, "calls": 0, "revisions": 0})
    by_step = defaultdict(lambda: {"cost": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0, "ms": 0, "failed": 0, "model": ""})
    for call in calls:
        step = "eval" if call.step.startswith("eval_") else ("plan_act" if call.step.startswith("plan_act_") else call.step)
        row = by_step[step]
        row["cost"] += call.cost_usd
        row["calls"] += 1
        row["tokens_in"] += call.input_tokens
        row["tokens_out"] += call.output_tokens
        row["ms"] += call.latency_ms
        row["failed"] += 0 if call.succeeded else 1
        row["model"] = call.model
        if call.episode_number and not call.step.startswith("eval_"):
            ep = by_episode[call.episode_number]
            ep["cost"] += call.cost_usd
            ep["ms"] += call.latency_ms
            ep["calls"] += 1
            ep["revisions"] += 1 if call.step == "revise" else 0

    written = [by_episode[e.number] for e in approved if e.number in by_episode]
    avg_cost = sum(r["cost"] for r in written) / len(written) if written else 0
    avg_seconds = sum(r["ms"] for r in written) / len(written) / 1000 if written else 0
    planning_total = by_step["plan_bible"]["cost"] + by_step["plan_act"]["cost"]
    times_planned = max(by_step["plan_bible"]["calls"], 1)
    planning = planning_total / times_planned  # a story that was re-planned from scratch paid for it more than once
    total = data["story"].total_episodes

    lines = [
        f"# {data['story'].title}: measured run statistics",
        "",
        f"From the `llm_calls` log: {len(calls)} model calls, {len(approved)} approved episodes.",
        "",
        "## Projection for the full serial",
        "",
        f"- Average per approved episode: **${avg_cost:.3f}** and **{avg_seconds:.0f}s** of model time",
        f"- Arc planning: **${planning:.2f}** per plan"
        + (f" (this story was planned {times_planned} times, ${planning_total:.2f} in total)" if times_planned > 1 else ""),
        f"- All {total} episodes: about **${avg_cost * total + planning:.2f}** and **{avg_seconds * total / 3600:.1f} hours** of model time, plus human review",
        f"- Hard ceiling from the per-episode cap: {total} x ${config.EPISODE_COST_CAP_USD:.2f} = ${total * config.EPISODE_COST_CAP_USD:.0f}",
        "",
        "## By step",
        "",
        "| Step | Model | Calls | Failed | Tokens in | Tokens out | Cost | Avg latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for step, row in sorted(by_step.items(), key=lambda item: -item[1]["cost"]):
        lines.append(
            f"| {step} | {row['model']} | {row['calls']} | {row['failed']} | {row['tokens_in']:,} | {row['tokens_out']:,} "
            f"| ${row['cost']:.3f} | {row['ms'] / max(row['calls'], 1) / 1000:.1f}s |"
        )
    lines += ["", "## Per episode", "", "| Ep | Calls | Revisions | Cost | Model time |", "|---|---|---|---|---|"]
    for e in approved:
        row = by_episode.get(e.number)
        if row:
            lines.append(f"| {e.number} | {row['calls']} | {row['revisions']} | ${row['cost']:.3f} | {row['ms'] / 1000:.0f}s |")

    if data["evaluations"]:
        latest = data["evaluations"][0]
        lines += ["", f"## LangSmith evaluation ({latest.episodes_scored} episodes, ${latest.cost_usd:.3f})", ""]
        lines += [f"- **{key.replace('_', ' ')}**: {'-' if score is None else f'{score * 100:.0f}%'}" for key, score in latest.scores.items()]
        if latest.experiment_url:
            lines += ["", f"Experiment: {latest.experiment_url}"]
    lines.append("")
    return "\n".join(lines)


def unquote(text: str) -> str:
    """People often type instructions wrapped in quotes; don't double them up."""
    return (text or "").strip().strip('"\u201c\u201d').strip()


def cell(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return (text or "").replace("|", "/").replace("\n", " ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", type=int, required=True)
    parser.add_argument("--out", default="../docs/demo")
    args = parser.parse_args()
    create_tables()
    for path in export(args.story, Path(args.out)):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
