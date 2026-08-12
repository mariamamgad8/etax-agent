import datetime
from typing import Optional, Tuple

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import String, DateTime, create_engine, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from app.config import DATABASE_URL, EMBEDDING_DIM

engine = create_engine(DATABASE_URL, future=True)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def init_db():
    with engine.connect() as conn:
        conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)


def register_person(name: str, embedding: np.ndarray) -> int:
    with Session(engine) as session:
        person = Person(name=name, embedding=embedding.tolist())
        session.add(person)
        session.commit()
        return person.id


def find_closest(embedding: np.ndarray) -> Optional[Tuple[Person, float]]:
    """
    Returns (Person, cosine_similarity) for the closest enrolled face,
    or None if the table is empty.

    pgvector's `<=>` operator returns cosine *distance* (1 - cosine_similarity)
    for normalized vectors, so similarity = 1 - distance.
    """
    with Session(engine) as session:
        distance_col = Person.embedding.cosine_distance(embedding.tolist())
        stmt = select(Person, distance_col).order_by(distance_col).limit(1)
        result = session.execute(stmt).first()
        if result is None:
            return None
        person, distance = result
        similarity = 1.0 - float(distance)
        # detach values we need before the session closes
        return Person(id=person.id, name=person.name, embedding=person.embedding), similarity
