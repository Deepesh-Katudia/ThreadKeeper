"""All the knobs in one place. Everything can be overridden with environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ModelPrice:
    """Dollars per million tokens."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


# Which model does which job. Ids with a "/" go through OpenRouter; the rest go straight
# to the Anthropic API (e.g. PLANNER_MODEL=claude-opus-5-5). Everything runs on OpenRouter
# by default. The critic is a different model family on purpose: a judge that isn't
# Claude is less likely to wave through the writer's own habits.
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "anthropic/claude-opus-5.5")
WRITER_MODEL = os.getenv("WRITER_MODEL", "anthropic/claude-sonnet-5.5")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "anthropic/claude-haiku-4.5")
CRITIC_MODEL = os.getenv("CRITIC_MODEL", "google/gemini-2.5-flash")
# Used for non-Claude OpenRouter models (the critic) when no OpenRouter key is set.
DIRECT_FALLBACK_MODEL = "claude-haiku-4-5"

PRICES = {
    "claude-opus-5-5": ModelPrice(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-sonnet-5-5": ModelPrice(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    "claude-haiku-4-5": ModelPrice(input=1.00, output=5.00, cache_read=0.10, cache_write=1.25),
    # Same models through OpenRouter, same list prices. OpenRouter normally reports the exact
    # cost with each response; these are only used when it doesn't.
    "anthropic/claude-opus-5.5": ModelPrice(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "anthropic/claude-sonnet-5.5": ModelPrice(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    "anthropic/claude-haiku-4.5": ModelPrice(input=1.00, output=5.00, cache_read=0.10, cache_write=1.25),
}

# Models that accept the adaptive-thinking "effort" knob and server-side refusal fallbacks.
MODELS_WITH_EFFORT = {"claude-opus-5-5", "claude-sonnet-5-5", "anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5"}
PLANNER_EFFORT = os.getenv("PLANNER_EFFORT", "medium")
WRITER_EFFORT = os.getenv("WRITER_EFFORT", "medium")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Story shape
TOTAL_EPISODES = int(os.getenv("TOTAL_EPISODES", "200"))
NUMBER_OF_ACTS = 8
MIN_WORDS = 400
MAX_WORDS = 700

# Stopping rules
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "2"))
EPISODE_COST_CAP_USD = float(os.getenv("EPISODE_COST_CAP_USD", "0.25"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "180"))

# How much memory goes into each episode prompt. These numbers keep the prompt the same size
# at episode 150 as at episode 5.
RECENT_SUMMARIES = 8
UPCOMING_BEATS = 3
MAX_FACTS_IN_CONTEXT = 40
MAX_THREADS_IN_CONTEXT = 12
STORY_SO_FAR_EVERY = 10
LAST_WORDS_OF_PREVIOUS = 150

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///threadkeeper.db")
ACCESS_KEY = os.getenv("ACCESS_KEY", "")
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]
