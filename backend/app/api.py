from typing import Literal

import psycopg
from fastapi import FastAPI, Response
from pydantic import BaseModel

app = FastAPI(title="SiteMind API")


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
