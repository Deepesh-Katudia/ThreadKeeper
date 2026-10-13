"""Errors the API turns into plain messages."""


class NotAllowed(ValueError):
    """The request makes sense, just not right now (e.g. writing before the arc is approved)."""
