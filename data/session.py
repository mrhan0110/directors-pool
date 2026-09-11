"""DB 엔진 / 세션 관리.

접속 문자열만 환경변수로 분리해 두어 개발(SQLite) → 운영(PostgreSQL) 전환이
코드 수정 없이 가능하다 (PRD §8).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from data.models import Base

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "storage" / "pool_dev.db"

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def get_engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        url = database_url()
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            # Streamlit 은 스크립트를 여러 스레드에서 재실행한다
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션 경계. 예외 시 롤백한다."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(drop: bool = False) -> None:
    engine = get_engine()
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def reset_engine() -> None:
    """테스트에서 DB 를 갈아끼울 때 사용."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
