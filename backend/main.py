"""Threadkeeper API. Run locally with:  uvicorn main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import routes_episodes, routes_memory, routes_stories
from api.errors import readable_validation_message
from api.jobs import JobAlreadyRunning
from story import config
from story.db import create_tables
from story.llm import LLMError
from story.pipeline import NotAllowed, recover_interrupted_work
from story.queries import NotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    recover_interrupted_work()
    yield


def check_access_key(x_access_key: str = Header(default="")) -> None:
    """A shared passcode, so strangers can't spend our API credits on the public URL."""
    if config.ACCESS_KEY and x_access_key != config.ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Wrong or missing access key.")


app = FastAPI(title="Threadkeeper", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(check_access_key)]
app.include_router(routes_stories.router, dependencies=protected)
app.include_router(routes_episodes.router, dependencies=protected)
app.include_router(routes_memory.router, dependencies=protected)


@app.get("/health")
def health():
    return {"ok": True}


@app.exception_handler(RequestValidationError)
def invalid_request(_request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": readable_validation_message(error.errors())})


@app.exception_handler(NotFound)
def not_found(_request: Request, error: NotFound):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(NotAllowed)
def not_allowed(_request: Request, error: NotAllowed):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(JobAlreadyRunning)
def busy(_request: Request, error: JobAlreadyRunning):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(LLMError)
def model_failed(_request: Request, error: LLMError):
    return JSONResponse(status_code=502, content={"detail": f"The AI model call failed: {error}. Please try again."})


@app.exception_handler(Exception)
def unexpected(_request: Request, error: Exception):
    logging.getLogger("threadkeeper").exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on the server. Please try again; if it keeps happening, check the backend logs."},
    )
