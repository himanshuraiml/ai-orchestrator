from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Every Mapped[datetime] column becomes TIMESTAMPTZ. Without this,
    # SQLAlchemy infers a naive DateTime and asyncpg rejects the
    # timezone-aware datetimes the app actually produces (datetime.now(UTC)).
    type_annotation_map: ClassVar[dict] = {
        datetime: DateTime(timezone=True),
    }
