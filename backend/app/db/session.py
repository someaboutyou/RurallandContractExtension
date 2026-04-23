from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import base as _base  # noqa: F401  Ensures all ORM models are registered.

engine = create_engine(settings.sqlalchemy_database_uri, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
