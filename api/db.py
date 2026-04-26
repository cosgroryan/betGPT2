import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/betgpt.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id = Column(String, primary_key=True)
    date = Column(String, index=True)
    name = Column(String)
    country = Column(String)
    state = Column(String)
    track_condition = Column(String)
    category = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class Race(Base):
    __tablename__ = "races"

    event_id = Column(String, primary_key=True)
    meeting_id = Column(String, index=True)
    race_number = Column(Integer)
    name = Column(String)
    distance = Column(Integer)
    class_level = Column(String)
    field_size = Column(Integer)
    track_surface = Column(String)
    track_direction = Column(String)
    track_condition = Column(String)
    rail_position = Column(String)
    prize_money_first = Column(Float)
    start_type = Column(String)
    start_time = Column(String)
    status = Column(String)
    weather = Column(String)
    country = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class Runner(Base):
    """
    One row per runner per race, snapshotted at race time.
    Odds columns reflect the final pre-race state.
    Feature columns are computed by features.py and stored here
    so training doesn't require re-parsing raw JSON.
    """
    __tablename__ = "runners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True)
    entrant_id = Column(String)
    name = Column(String)
    runner_number = Column(Integer)
    barrier = Column(Integer)
    is_scratched = Column(Boolean, default=False)
    is_late_scratched = Column(Boolean, default=False)
    jockey = Column(String)
    trainer_name = Column(String)
    age = Column(Integer)
    sex = Column(String)
    weight_total = Column(Float)
    weight_allocated = Column(Float)
    handicap_rating = Column(Float)
    spr = Column(Float)
    class_level = Column(String)
    colour = Column(String)
    is_first_start = Column(Boolean, default=False)
    apprentice_indicator = Column(String)
    gear = Column(String)

    # Market snapshot
    tab_fixed_win = Column(Float)
    tab_fixed_place = Column(Float)
    tab_pool_win = Column(Float)
    tab_pool_place = Column(Float)
    tab_implied_prob = Column(Float)  # margin-removed
    fluc_open = Column(Float)
    fluc_9am = Column(Float)
    fluc_high = Column(Float)
    fluc_low = Column(Float)
    fluc_drift = Column(Float)
    is_market_mover = Column(Boolean, default=False)
    is_favourite = Column(Boolean, default=False)
    hold_pct = Column(Float)
    bet_pct = Column(Float)

    # Speedmap
    speedmap_label = Column(String)
    barrier_speed = Column(Float)
    finish_speed = Column(Float)
    settling_lengths = Column(Float)

    # Raw JSON snapshot (for re-deriving features without re-fetching API)
    raw_json = Column(Text)

    snapshotted_at = Column(DateTime, default=datetime.utcnow)


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True)
    entrant_id = Column(String)
    name = Column(String)
    position = Column(Integer)
    runner_number = Column(Integer)
    barrier = Column(Integer)
    margin_lengths = Column(Float)
    time_ran = Column(Float)
    winning_time = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class ValueBet(Base):
    """Records every bet flagged as value by the model, for tracker view."""

    __tablename__ = "value_bets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True)
    entrant_id = Column(String)
    runner_name = Column(String)
    race_label = Column(String)  # e.g. "R4 RANDWICK"
    model_prob = Column(Float)
    model_odds = Column(Float)
    tab_odds = Column(Float)
    tab_implied_prob = Column(Float)
    value_edge = Column(Float)
    flagged_at = Column(DateTime, default=datetime.utcnow)
    # Filled after race settles
    result_position = Column(Integer, nullable=True)
    won = Column(Boolean, nullable=True)
    placed = Column(Boolean, nullable=True)
    pl_flat_stake = Column(Float, nullable=True)  # P&L on $1 flat stake


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
