from app.db.base import Base
from app.db.init_db import seed_initial_data
from app.db.migrations import upgrade_schema
from app.db.session import SessionLocal, engine


def create_database_schema() -> None:
    Base.metadata.create_all(bind=engine)
    upgrade_schema(engine)


def seed_database() -> None:
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()


def bootstrap_database() -> None:
    create_database_schema()
    seed_database()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database bootstrap utility")
    parser.add_argument("--schema", action="store_true", help="create/upgrade database schema only")
    parser.add_argument("--seed", action="store_true", help="seed framework data only")
    args = parser.parse_args()

    if args.schema:
        create_database_schema()
    elif args.seed:
        seed_database()
    else:
        bootstrap_database()
