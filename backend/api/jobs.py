"""Runs slow work (planning, writing) in the background and records its progress in the jobs table."""

import logging

from fastapi import BackgroundTasks
from sqlalchemy import select

from story.db import session_scope
from story.models import Job

log = logging.getLogger(__name__)


class JobAlreadyRunning(RuntimeError):
    pass


def running_job(story_id: int) -> Job | None:
    with session_scope() as session:
        return session.scalar(select(Job).where(Job.story_id == story_id, Job.status == "running"))


def start_job(background: BackgroundTasks, story_id: int, kind: str, work, *args) -> Job:
    """Queue `work(*args)`. One job per story at a time, so two writers never race on the same episode."""
    if running_job(story_id) is not None:
        raise JobAlreadyRunning("Something is already running for this story. Wait for it to finish.")
    with session_scope() as session:
        job = Job(story_id=story_id, kind=kind)
        session.add(job)
        session.flush()
        job_id = job.id
    background.add_task(_run, job_id, work, *args)
    with session_scope() as session:
        return session.get(Job, job_id)


def _run(job_id: int, work, *args) -> None:
    try:
        result = work(*args)
        status, detail = "done", result if isinstance(result, str) else ""
    except Exception as error:
        log.exception("job %s failed", job_id)
        status, detail = "failed", str(error)[:2000]
    with session_scope() as session:
        job = session.get(Job, job_id)
        job.status, job.detail = status, detail
