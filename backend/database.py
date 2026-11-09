from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import Settings


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Check(Base):
    __tablename__ = "health_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String(80), index=True)
    checked_at: Mapped[str] = mapped_column(String(40), default=now, index=True)
    healthy: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(String(160))


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String(80), index=True)
    opened_at: Mapped[str] = mapped_column(String(40), default=now)
    resolved_at: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(160))


class Release(Base):
    __tablename__ = "releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    commit_sha: Mapped[str] = mapped_column(String(40), unique=True)
    deployed_at: Mapped[str] = mapped_column(String(40), default=now)
    environment: Mapped[str] = mapped_column(String(20), default="production")
    run_id: Mapped[int] = mapped_column(BigInteger)
    version: Mapped[str] = mapped_column(String(80))


class Pipeline(Base):
    __tablename__ = "pipelines"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(40))
    commit_sha: Mapped[str] = mapped_column(String(40))
    branch: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    url: Mapped[str] = mapped_column(Text)
    jobs: Mapped[list] = mapped_column(JSON, default=list)


class SyncState(Base):
    __tablename__ = "sync_state"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    checked_at: Mapped[str] = mapped_column(String(40), default=now)
    success: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(String(160))


class Database:
    def __init__(self, config: Settings):
        url = config.database_url.get_secret_value()
        self.sqlite = url.startswith("sqlite")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        args = (
            {"check_same_thread": False, "timeout": 10}
            if self.sqlite
            else {
                "sslmode": config.database_sslmode,
                "connect_timeout": 8,
                "prepare_threshold": None,
                "options": f"-c search_path={config.database_schema} -c statement_timeout=8000",
            }
        )
        self.engine = create_engine(url, connect_args=args, pool_pre_ping=True)

    def initialize(self):
        # Production schema is applied separately by scripts/migrate.py.
        if self.sqlite:
            Base.metadata.create_all(self.engine)
        self.check()

    def check(self):
        with self.engine.connect() as connection:
            connection.execute(text("SELECT id FROM health_checks LIMIT 1"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine) as session:
            with session.begin():
                yield session
