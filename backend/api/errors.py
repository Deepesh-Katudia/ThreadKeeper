"""Turns FastAPI's validation errors into sentences a person can act on.

Instead of  [{"type": "greater_than_equal", "loc": ["body", "total_episodes"], ...}]
the client gets  "Number of episodes must be at least 10."
"""

FIELD_NAMES = {
    "premise": "The premise",
    "total_episodes": "Number of episodes",
    "count": "Number of episodes to write",
    "auto_approve": "Auto-approve",
    "text": "The text",
    "title": "The title",
    "reason": "The reason",
    "beat": "The beat",
    "number": "Episode number",
    "name": "Character name",
    "expires_after_episode": "\"Applies until episode\"",
}


def field_name(location: list) -> str:
    # loc looks like ["body", "total_episodes"] or ["body", "beats", 3, "beat"]
    names = [part for part in location if isinstance(part, str) and part != "body"]
    if not names:
        return "The request"
    return FIELD_NAMES.get(names[-1], names[-1].replace("_", " ").capitalize())


def describe(error: dict) -> str:
    field = field_name(error.get("loc", []))
    limits = error.get("ctx") or {}
    kind = error.get("type", "")

    if kind == "missing":
        return f"{field} is required."
    if kind in ("greater_than_equal", "greater_than"):
        return f"{field} must be at least {limits.get('ge', limits.get('gt'))}."
    if kind in ("less_than_equal", "less_than"):
        return f"{field} can be at most {limits.get('le', limits.get('lt'))}."
    if kind == "string_too_short":
        return f"{field} is too short: use at least {limits.get('min_length')} characters."
    if kind == "string_too_long":
        return f"{field} is too long: keep it under {limits.get('max_length')} characters."
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return f"{field} must be a whole number."
    if kind in ("bool_parsing", "bool_type"):
        return f"{field} must be yes or no."
    if kind == "json_invalid":
        return "The request couldn't be read. Please try again."
    return f"{field}: {error.get('msg', 'is not valid')}."


def readable_validation_message(errors: list[dict]) -> str:
    """One sentence per problem, without repeats."""
    sentences = []
    for error in errors:
        sentence = describe(error)
        if sentence not in sentences:
            sentences.append(sentence)
    return " ".join(sentences)
