from typing import Literal

import psycopg
from fastapi import FastAPI, Response
from pydantic import BaseModel

from app.site_api import router
from app.cad_api import router as cad_router
from app.ingestion_api import router as ingestion_router
from app.flag_api import router as flag_router

from app.outbox import router as outbox_router

app = FastAPI(title="SiteMind API")
app.include_router(router)
app.include_router(cad_router)
app.include_router(ingestion_router)
app.include_router(flag_router)
app.include_router(outbox_router)


class Health(BaseModel):
    api: Literal["ok"] = "ok"
    db: Literal["ok", "error"]


@app.get("/health", response_model=Health, responses={503: {"model": Health}})
def health(response: Response) -> Health:
    try:
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SELECT 1").fetchone()
    except psycopg.Error:
        response.status_code = 503
        return Health(db="error")
    return Health(db="ok")
