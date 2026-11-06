import pytest
from app.services.rate_limiter import rate_limiter
from app.database import SessionLocal, Base, engine
from app.models.all_models import *

@pytest.fixture(autouse=True, scope="session")
def setup_database_schema():
    Base.metadata.create_all(bind=engine)

@pytest.fixture(autouse=True)
def reset_rate_limiter_and_db():
    rate_limiter.reset()
    yield
    rate_limiter.reset()

