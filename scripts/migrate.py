"""Apply additive schema changes before deploying. Never drops data."""

from sqlalchemy import text

from backend.config import Settings
from backend.database import Base, Database

if __name__ == "__main__":
    database = Database(Settings())
    Base.metadata.create_all(database.engine)
    if not database.sqlite:
        with database.engine.begin() as connection:
            connection.execute(text("ALTER TABLE pipelines ALTER COLUMN id TYPE BIGINT"))
            connection.execute(text("ALTER TABLE releases ALTER COLUMN run_id TYPE BIGINT"))
    database.check()
    print("Database schema ready")
