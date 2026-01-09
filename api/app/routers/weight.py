from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..database import get_db

# Timezone configuration - all date calculations use Eastern time
EASTERN = ZoneInfo("America/New_York")


def get_eastern_today() -> date:
    """Get today's date in Eastern time"""
    return datetime.now(EASTERN).date()


from ..models import WeightLog, User
from ..schemas import WeightCreate, WeightResponse

router = APIRouter(prefix="/weight", tags=["weight"])


def get_or_create_user(db: Session, discord_id: str) -> User:
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/", response_model=WeightResponse)
def log_weight(
    data: WeightCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Log a weight measurement"""
    user = get_or_create_user(db, discord_id)

    log = WeightLog(
        user_id=user.id,
        date=data.date or get_eastern_today(),
        weight_lbs=data.weight_lbs,
        notes=data.notes
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/latest", response_model=Optional[WeightResponse])
def get_latest_weight(discord_id: str, db: Session = Depends(get_db)):
    """Get the most recent weight log"""
    user = get_or_create_user(db, discord_id)

    log = db.query(WeightLog).filter(
        WeightLog.user_id == user.id
    ).order_by(WeightLog.date.desc()).first()

    return log


@router.get("/history", response_model=list[WeightResponse])
def get_weight_history(
    discord_id: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get weight history for the last N days"""
    user = get_or_create_user(db, discord_id)
    start_date = get_eastern_today() - timedelta(days=days)

    logs = db.query(WeightLog).filter(
        WeightLog.user_id == user.id,
        WeightLog.date >= start_date
    ).order_by(WeightLog.date.asc()).all()

    return logs


@router.delete("/{log_id}")
def delete_weight_log(log_id: int, discord_id: str, db: Session = Depends(get_db)):
    """Delete a weight log"""
    user = get_or_create_user(db, discord_id)

    log = db.query(WeightLog).filter(
        WeightLog.id == log_id,
        WeightLog.user_id == user.id
    ).first()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    db.delete(log)
    db.commit()
    return {"message": "Deleted", "id": log_id}
