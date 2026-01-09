from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..database import get_db

# Timezone configuration - all date calculations use Eastern time
EASTERN = ZoneInfo("America/New_York")


def get_eastern_today() -> date:
    """Get today's date in Eastern time"""
    return datetime.now(EASTERN).date()


from ..models import DailyMetric, User
from ..schemas import DailyMetricCreate, DailyMetricResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_or_create_user(db: Session, discord_id: str) -> User:
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/", response_model=DailyMetricResponse)
def log_daily_metrics(
    data: DailyMetricCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Log daily metrics (sleep, mood, energy)"""
    user = get_or_create_user(db, discord_id)
    target_date = data.date or get_eastern_today()

    # Check if entry exists for this date - update if so
    existing = db.query(DailyMetric).filter(
        DailyMetric.user_id == user.id,
        DailyMetric.date == target_date
    ).first()

    if existing:
        # Update existing entry
        for key, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    # Create new entry
    metric = DailyMetric(
        user_id=user.id,
        date=target_date,
        sleep_hours=data.sleep_hours,
        sleep_quality=data.sleep_quality,
        mood=data.mood,
        energy_level=data.energy_level,
        notes=data.notes
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


@router.get("/today", response_model=DailyMetricResponse | None)
def get_today_metrics(discord_id: str, db: Session = Depends(get_db)):
    """Get metrics for today"""
    user = get_or_create_user(db, discord_id)

    metric = db.query(DailyMetric).filter(
        DailyMetric.user_id == user.id,
        DailyMetric.date == get_eastern_today()
    ).first()

    return metric


@router.get("/history", response_model=list[DailyMetricResponse])
def get_metrics_history(
    discord_id: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get metrics history for the last N days"""
    user = get_or_create_user(db, discord_id)
    start_date = get_eastern_today() - timedelta(days=days)

    metrics = db.query(DailyMetric).filter(
        DailyMetric.user_id == user.id,
        DailyMetric.date >= start_date
    ).order_by(DailyMetric.date.desc()).all()

    return metrics
