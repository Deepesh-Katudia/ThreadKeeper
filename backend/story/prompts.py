"""Every prompt the system uses, in one readable place."""

from story import config

WRITING_RULES = f"""\
How to write an episode:
- {config.MIN_WORDS}-{config.MAX_WORDS} words. One scene, or two at most. Start in motion; no recaps of the last episode.
- Concrete, specific detail over atmosphere. Name streets, objects, times of day, smells.
- Dialogue does the heavy lifting. People talk past each other, dodge, interrupt.
- End on a hook: a reveal, a decision, a threat, or a question the reader needs answered.
  The hook must be earned by this episode's events, not bolted on.
- Move the story forward. Every episode changes something that can't be undone.
- Never use these crutches: "little did they know", "a chill ran down", "the air was thick with",
  "something shifted", "in that moment", "the weight of", "unspoken", "testament to",
  eyes that "widened" more than once, or ending on someone simply staring into the dark.
- Stay inside canon. Dead characters stay dead unless the plan says otherwise. Don't invent
  new rules for how the world works when an existing one will do.
"""


def planner_system() -> str:
    return (
        "You are the showrunner of a long-running serial fiction app. Readers get one "
        f"{config.MIN_WORDS}-{config.MAX_WORDS} word episode a day and must want the next one. "
        "You plan stories that can sustain 200 episodes without sagging: escalating stakes, "
        "mysteries that pay off on schedule, and characters who change."
    )


def bible_prompt(premise: str, total_episodes: int) -> str:
    return f"""\
Premise: {premise}

Plan a {total_episodes}-episode serial built on this premise.

Return:
- title and a one-sentence logline
- setting: the place, the time, and the rules of anything strange in it (keep these rules consistent)
- style_guide: 5-8 specific rules for voice, point of view, tense, and tone that make this serial feel distinct
- characters: 6-10 people. Give each a role (protagonist / antagonist / supporting / minor),
  a concrete description (job, habit, want, secret) and a planned arc across the whole story
- acts: exactly {config.NUMBER_OF_ACTS} acts covering episodes 1-{total_episodes} with no gaps or overlaps.
  Each act has a goal and a turning point that changes the direction of the story.
- threads: 10-16 mysteries, promises, or relationships the reader will track. For each, the
  episode where it is first raised and the episode where it pays off. Spread payoffs across the
  whole run; don't save them all for the end.
"""


def act_beats_prompt(bible_text: str, act, total_episodes: int) -> str:
    return f"""\
{bible_text}

Now write the episode-by-episode beats for Act {act.number}: "{act.title}"
(episodes {act.first_episode}-{act.last_episode} of {total_episodes}).
Act goal: {act.goal}
Turning point: {act.turning_point}

One beat per episode, 1-2 sentences each: what happens and what changes. Every episode must
have a distinct event; no two beats may do the same job. Place thread openings and payoffs at
the episodes listed above. The last beat of the act lands the turning point.
Return exactly {act.last_episode - act.first_episode + 1} beats, numbered {act.first_episode} to {act.last_episode}.
"""


def writer_system(story, characters_text: str) -> str:
    """Stable per story, so it gets cached across episodes."""
    return f"""\
You are the writer of the serial "{story.title}".
Logline: {story.logline}

Setting and rules of the world:
{story.setting}

House style for this serial:
{story.style_guide}

Main cast:
{characters_text}

{WRITING_RULES}"""


def draft_prompt(context_text: str, episode_number: int, extra_note: str = "") -> str:
    note = f"\nThe editor rejected an earlier draft of this episode. Their note: {extra_note}\n" if extra_note else ""
    return f"""\
{context_text}
{note}
Write episode {episode_number}. Follow this episode's beat, respect every standing instruction
from the editor, and stay consistent with the canon above.
Return a short episode title and the episode text (prose only, no headings)."""


def revise_prompt(context_text: str, draft_text: str, report) -> str:
    problems = "\n".join(f"- [{p.kind}] {p.detail}" for p in report.problems) or "- none listed"
    return f"""\
{context_text}

Here is a draft of this episode:
<draft>
{draft_text}
</draft>

A reviewer flagged these problems:
{problems}
Reviewer advice: {report.advice}

Rewrite the episode to fix every problem while keeping what works. Same beat, same length rules.
Return the title and the full revised text."""


def critic_system() -> str:
    return (
        "You are a tough story editor for a serial fiction app. You catch continuity errors, "
        "repeated plot beats, ignored editor instructions, and weak endings before readers do. "
        "Only flag real problems you can point to in the text. Don't nitpick style."
    )


def critic_prompt(context_text: str, draft_text: str, word_count: int) -> str:
    return f"""\
{context_text}

Draft of this episode ({word_count} words, allowed {config.MIN_WORDS}-{config.MAX_WORDS}):
<draft>
{draft_text}
</draft>

Check the draft against the canon, the recent episodes and the editor's standing instructions:
1. contradiction: does anything contradict a fact, a character's status (e.g. a dead character
   acting), or earlier events?
2. repetition: does it replay a beat, reveal or scene shape we've already had?
3. directive: does it ignore a standing instruction from the editor?
4. follows_beat: does it deliver this episode's planned beat?
5. hook_score 1-5: 5 = I must read the next one, 1 = no reason to continue.
6. pacing / style: only if something is seriously wrong.

verdict is "revise" if there is any contradiction, repetition or ignored directive, if the beat
is missed, or if hook_score is below 3. Otherwise "pass". Give short, actionable advice."""


def extractor_system() -> str:
    return (
        "You keep the continuity records for a serial story. You read a finished episode and "
        "record exactly what it establishes, nothing more. Use character names exactly as they "
        "appear in the known cast when referring to existing people."
    )


def extractor_prompt(episode_number: int, episode_text: str, known_cast: str, open_threads: str) -> str:
    return f"""\
Known cast: {known_cast}
Open threads: {open_threads}

Episode {episode_number}:
<episode>
{episode_text}
</episode>

Record:
- summary: 60-90 words, past tense, the events and what changed
- hook: one sentence, the cliffhanger the episode ends on
- characters_present: names of everyone who appears or speaks
- new_characters: people who appear for the first time (not in the known cast)
- character_changes: only if someone dies, goes missing, or comes back
- new_facts: 2-6 durable facts future episodes must not contradict (who knows what,
  relationships, injuries, objects, places, rules of the world). Skip passing moments.
  Be concrete: record exact addresses, room and locker numbers, objects and what is written on
  them, times and amounts. If the episode opens with a header line (an order, a date, an
  address), record what it says as a fact.
- threads_opened: new mysteries or promises raised in this episode
- resolved_thread_ids: the [id] of each open thread (from the list above) this episode answers
- threads_resolved: the titles of those same threads"""


def diff_prompt(
    episode_number: int, old_text: str, new_text: str, fact_lines: str, thread_lines: str, cast_lines: str,
) -> str:
    return f"""The editor rewrote episode {episode_number}, which was already part of the story.

Facts currently recorded from this episode:
{fact_lines}

Threads as of this episode:
{thread_lines}

Known characters:
{cast_lines}

Old version:
<old>
{old_text}
</old>

New version:
<new>
{new_text}
</new>

Return only what the edit changes. Keep every fact the new text still supports, even if it is
worded differently: retract a fact only when the new text no longer says it or says something else.
- summary, hook, characters_present: for the new version (same rules as a normal extraction)
- retract_fact_ids: [id]s of recorded facts the new text no longer supports
- new_facts: facts the new text establishes that no kept fact already covers. Be concrete:
  addresses, numbers, objects and what is written on them, times, and the opening line.
- new_characters: people who now appear for the first time; remove_character_ids: [id]s of people
  first seen in this episode who no longer appear in it
- character_changes: only where a character's status after this episode differs from what is listed
- threads_opened: questions the new text raises that aren't listed; remove_thread_ids: [id]s of
  threads opened in this episode that the new text no longer raises
- resolve_thread_ids: [id]s of open threads the new text now answers; reopen_thread_ids: [id]s of
  threads resolved in this episode that the new text no longer answers
Use empty lists when nothing changed."""


def replan_prompt(bible_text: str, feedback: str, after_episode: int, beats_text: str) -> str:
    return f"""\
{bible_text}

The human editor just gave this instruction after episode {after_episode}:
"{feedback}"

Here are the upcoming planned beats:
{beats_text}

Rewrite these beats so the story follows the instruction from here on, while keeping the act
goals and turning points intact where you can. Change only what needs changing.
Return every beat listed (same episode numbers) and a one-paragraph summary of what you changed."""


def story_so_far_prompt(previous_recap: str, summaries_text: str) -> str:
    return f"""\
Story so far (older recap):
{previous_recap or "(none yet)"}

Newer episode summaries:
{summaries_text}

Write an updated "story so far" in at most 350 words. Keep the events that still matter for
what comes next: who knows what, who is dead or missing, promises made, mysteries still open.
Drop the details that no longer matter."""


def act_summary_prompt(act_title: str, summaries_text: str) -> str:
    return f"""\
Summarise Act "{act_title}" in at most 200 words from these episode summaries. Focus on what
changed and what it set up.

{summaries_text}"""


def ripple_check_prompt(change_text: str, canon_text: str, episode_number: int, episode_text: str) -> str:
    return f"""\
The editor changed an earlier episode. Here is what changed:
{change_text}

Canon as it now stands (from the changed episode up to this one):
{canon_text}

Episode {episode_number} text:
<episode>
{episode_text}
</episode>

Does episode {episode_number} contradict the change? Only report passages that state or rely on
something that is no longer true. For each one, copy the passage exactly as it appears (a phrase
or one sentence) as quote, and say why in reason.
verdict: "consistent" if nothing conflicts, "minor" if a few words or a sentence can fix it,
"major" if the episode's events depend on what changed."""


def ripple_patch_prompt(change_text: str, conflicts_text: str, episode_number: int, episode_text: str) -> str:
    return f"""\
The editor changed an earlier episode:
{change_text}

These passages of episode {episode_number} below now contradict it:
{conflicts_text}

<episode>
{episode_text}
</episode>

Propose the smallest edits that remove these contradictions without changing what the episode
is about. Each edit replaces one exact passage (copied character for character from the episode,
usually one sentence) with new text in the same voice. Don't touch anything else.
Return the edits and a one-line note on what you changed."""
