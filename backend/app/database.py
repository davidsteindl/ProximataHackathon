import os
from functools import lru_cache

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session


@lru_cache
def get_engine():
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            host=os.environ["PGHOST"],
            port=5432,
            database=os.environ["PGDATABASE"],
        ),
        pool_pre_ping=True,
    )


def get_session():
    with Session(get_engine()) as session:
        yield session
