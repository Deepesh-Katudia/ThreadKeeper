

---

# Take-Home Assignment: Agentic Serial Story Writer 

**Role:** AI Engineer**Time window:** 24 hours from receipt. We expect about 6-8 hours of focused work.

## The Problem

Build an **agentic system that writes a 200-episode serial story**, with a **human in the loop** who can guide, approve, and correct it along the way.

Given a one-line premise, the system should plan and write a long-running serial where each episode is **400-700 words**, ends on a hook, and stays consistent with everything before it: characters, relationships, timeline, and unresolved threads.

**Example premise:** "A delivery rider realizes every address on today's route belongs to someone who died in the same building."

## What We Need to See

You are **not** expected to generate all 200 episodes in 24 hours. We want a system that could, demonstrated on a meaningful slice.

**Your system must:**

1. **Plan the full 200-episode arc:** overall structure, major turning points, and character arcs.  
2. **Write episodes sequentially** in a way that would hold up at episode 150 as well as episode 5\.  
3. **Keep the story consistent** across episodes: no forgotten characters, contradicted facts, dropped threads, or repeated plot beats.  
4. **Support human-in-the-loop** control at meaningful points. At minimum, a human should be able to:  
   - Approve or edit the arc plan before writing begins  
   - Review, edit, or reject an episode, or give feedback like "slow down the romance" or "kill off this character"  
   - Have that feedback **carry forward** into future episodes, not just fix the current one  
5. **Resume:** stop after episode 12, come back later, and continue from where it left off.

### **What's Up to You**

Everything about the approach. There is no single right answer, and we're interested in seeing how you think.

* Architecture: single agent, graph or state machine, planner-executor, critic loops, multi-agent, or plain Python  
* Framework: LangGraph, CrewAI, Deep Agents, raw API calls, or anything else  
* Models: any LLM provider (we'll share API credits)  
* How the system plans, drafts, judges quality, revises, and decides it's done

Simple is fine. If one well-designed call plus a revision pass beats an elaborate pipeline, we want to see that.

## Format: Web-Hosted or CLI (Your Choice)

- **Web-hosted:** a deployed app with a public URL where we can enter a premise, review and edit the plan, and step through episodes with approve, edit, and feedback controls. Keep it up for at least 7 days, and use your own API key with a spending cap.  
- **CLI:** an interactive command-line flow with the same controls. Setup should take under 5 minutes via the README.

## Requirements

- **Traceable:** each run logs steps, decisions, retries, token cost, and latency.  
- **Bounded:** clear stopping rules and a cost cap per episode.  
- **Cost-aware:** tell us the estimated cost and time to generate all 200 episodes, and how you'd reduce them.

## Deliverables

1. **Git repo** with a README  
2. **Live URL** (if web-hosted)  
3. **Demo output:** the full 200-episode arc plan, plus **at least 15 written episodes** from the premise we send at the start, including at least **two HITL interventions** showing that feedback changed later episodes  
4. **Short screen recording (under 5 minutes)** of the HITL flow  
5. **`DECISIONS.md`** (max one page), answering:  
   - How does your system remember the story at episode 150? What's in context, and what's retrieved or summarized?  
   - Where does the human step in, and why there rather than elsewhere?  
   - How do you detect inconsistency or repetition before a human has to?  
   - What breaks first as the story grows, and how would you fix it?

## How We'll Evaluate

| Area | What we look for |
| :---- | :---- |
| **Memory and consistency design** | A convincing way to stay consistent over 200 episodes, not just over 15 |
| **HITL design** | Intervention points that make sense, with feedback that actually propagates |
| **Design reasoning** | Choices that fit the problem, with no complexity for its own sake |
| **Output quality** | Episodes with hooks and momentum, not generic LLM prose |
| **Engineering** | Resumability, observability, cost awareness, clean code |
| **Honesty** | A clear view of where the system breaks |

## What Happens Next

In the next round, we'll walk through your submission together, then change one requirement live (for example, "a human rewrites episode 40, so now what happens to episodes 41-60?") and discuss how your design adapts.

---

**Notes for you (don't send):**

- 24 hours is tight for this scope. Expect partial HITL UIs, and judge the memory and feedback design over polish. If you want more depth, consider 48 hours.  
- The **"episode 150" question** in DECISIONS.md is your best filter. Weak answers stuff everything into context. Strong ones describe layered memory: arc plan, rolling summaries, a character and fact store, and open-thread tracking.  
- A good live twist: "a human edits episode 40 retroactively." It tests whether their state design can handle changes to history.

