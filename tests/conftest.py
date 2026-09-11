from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# 테스트는 항상 임시 SQLite 로 돌린다. 개발 DB 를 건드리지 않는다.
_tmpdir = tempfile.mkdtemp(prefix="idp-pool-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir, 'test.db').as_posix()}"
os.environ["DATA_MODE"] = "dummy"
os.environ["AUTH_PROVIDER"] = "mock"
# 테스트는 소량 더미데이터로 돌린다
os.environ.setdefault("SEED_PERSON_COUNT", "25")


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    """코드·설정·더미 인물까지 적재한다.

    빈 DB 로만 테스트하면 페이지가 데이터 없이 st.stop() 해서
    실제 렌더링 경로를 검증하지 못한다.
    """
    from data import seed

    seed.run(reset=True)
    yield
