"""Small read helpers shared by the planner, writer and memory code."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from story.models import Act, Character, Directive, Episode, Fact, Story, Thread


class NotFound(LookupError):
    pass


def get_story(session: Session, story_id: int) -> Story:
    story = session.get(Story, story_id)
    if story is None:
        raise NotFound(f"story {story_id} does not exist")
    return story


def get_episode(session: Session, story_id: int, number: int) -> Episode:
    episode = session.scalar(
        select(Episode).where(Episode.story_id == story_id, Episode.number == number)
    )
    if episode is None:
        raise NotFound(f"episode {number} does not exist in story {story_id}")
    return episode


def all_episodes(session: Session, story_id: int) -> list[Episode]:
    return list(
        session.scalars(select(Episode).where(Episode.story_id == story_id).order_by(Episode.number))
    )


def episodes_between(session: Session, story_id: int, first: int, last: int) -> list[Episode]:
    return list(
        session.scalars(
            select(Episode)
            .where(Episode.story_id == story_id, Episode.number >= first, Episode.number <= last)
            .order_by(Episode.number)
        )
    )


def approved_episodes_before(session: Session, story_id: int, number: int, limit: int) -> list[Episode]:
    """The last `limit` approved episodes before `number`, oldest first."""
    rows = session.scalars(
        select(Episode)
        .where(Episode.story_id == story_id, Episode.number < number, Episode.status == "approved")
        .order_by(Episode.number.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


def acts(session: Session, story_id: int) -> list[Act]:
    return list(session.scalars(select(Act).where(Act.story_id == story_id).order_by(Act.number)))


def act_for_episode(session: Session, story_id: int, number: int) -> Act | None:
    return session.scalar(
        select(Act).where(
            Act.story_id == story_id, Act.first_episode <= number, Act.last_episode >= number
        )
    )


def characters(session: Session, story_id: int) -> list[Character]:
    return list(
        session.scalars(select(Character).where(Character.story_id == story_id).order_by(Character.id))
    )


def find_character(session: Session, story_id: int, name: str) -> Character | None:
    """Match on full name first, then on first name ("Mara" finds "Mara Okafor")."""
    wanted = name.strip().lower()
    cast = characters(session, story_id)
    for person in cast:
        if person.name.lower() == wanted:
            return person
    for person in cast:
        if person.name.lower().split()[0] == wanted.split()[0]:
            return person
    return None


def facts(session: Session, story_id: int) -> list[Fact]:
    return list(
        session.scalars(select(Fact).where(Fact.story_id == story_id).order_by(Fact.source_episode))
    )


def threads(session: Session, story_id: int, statuses: tuple[str, ...] | None = None) -> list[Thread]:
    query = select(Thread).where(Thread.story_id == story_id)
    if statuses:
        query = query.where(Thread.status.in_(statuses))
    return list(session.scalars(query.order_by(Thread.payoff_episode)))


def active_directives(session: Session, story_id: int, for_episode: int) -> list[Directive]:
    rows = session.scalars(
        select(Directive).where(Directive.story_id == story_id, Directive.is_active.is_(True))
    )
    return [
        d for d in rows if d.expires_after_episode == 0 or d.expires_after_episode >= for_episode
    ]
