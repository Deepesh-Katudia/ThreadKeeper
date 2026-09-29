"""Request bodies for the API."""

from pydantic import BaseModel, Field


class NewStory(BaseModel):
    premise: str = Field(min_length=10, max_length=1000)
    total_episodes: int = Field(default=200, ge=10, le=200)


class BeatEdit(BaseModel):
    number: int
    beat: str = Field(min_length=1, max_length=2000)


class CharacterEdit(BaseModel):
    id: int | None = None  # None means a new character
    name: str = Field(min_length=1, max_length=120)
    role: str = "supporting"
    description: str = ""
    planned_arc: str = ""


class ArcEdit(BaseModel):
    beats: list[BeatEdit] = []
    characters: list[CharacterEdit] = []


class WriteRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=25)
    auto_approve: bool = False


class EpisodeEdit(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    title: str | None = None


class Rejection(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    rewrite_now: bool = True


class Feedback(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    expires_after_episode: int = Field(default=0, ge=0)
