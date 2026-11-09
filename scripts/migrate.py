"""Apply additive schema changes before deploying. Never drops data."""

from backend.config import Settings
from backend.database import Base, Database

if __name__ == "__main__":
    database = Database(Settings())
    Base.metadata.create_all(database.engine)
    database.check()
    print("Database schema ready")
