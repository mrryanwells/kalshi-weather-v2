from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Session:
    with Session(engine) as session:
        yield session
