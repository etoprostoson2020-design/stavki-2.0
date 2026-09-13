"""Подключение к PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fsl.settings import get_settings

_engine = None
_Session = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().postgres_dsn, pool_pre_ping=True, future=True)
    return _engine


def session_factory():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=engine(), expire_on_commit=False, future=True)
    return _Session


@contextmanager
def session() -> Session:
    s = session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
