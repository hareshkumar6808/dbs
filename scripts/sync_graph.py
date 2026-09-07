from sqlalchemy.orm import Session
from backend.db import engine
from backend.graph import sync

if __name__ == "__main__":
    with Session(engine()) as db:
        print(sync(db))
