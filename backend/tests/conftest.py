import pytest
from sqlalchemy import text
from app.services.rate_limiter import rate_limiter
from app.database import SessionLocal, Base, engine
from app.models.all_models import *

@pytest.fixture(autouse=True, scope="session")
def setup_database_schema():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for col_sql in [
            "ALTER TABLE projects ADD COLUMN is_archived BOOLEAN DEFAULT 0",
            "ALTER TABLE projects ADD COLUMN archived_at DATETIME"
        ]:
            try:
                conn.execute(text(col_sql))
                conn.commit()
            except Exception:
                pass
    try:
        from app.seed_data import seed
        seed()
    except Exception:
        pass

@pytest.fixture(autouse=True)
def reset_rate_limiter_and_db():
    rate_limiter.reset()
    yield
    rate_limiter.reset()

