from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..database import get_db
from ..models import FastingWindow, User
from ..schemas import FastingCreate, FastingResponse

router = APIRouter(prefix="/fasting", tags=["fasting"])

# Timezone configuration - all date calculations use Eastern time
EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def get_eastern_now() -> datetime:
    """Get current datetime in Eastern time"""
    return datetime.now(EASTERN)


def get_or_create_user(db: Session, discord_id: str) -> User:
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def calculate_duration(started_at: datetime, ended_at: datetime | None) -> float | None:
    """Calculate fasting duration in hours"""
    if ended_at:
        delta = ended_at - started_at
        return round(delta.total_seconds() / 3600, 1)
    return None


@router.post("/", response_model=FastingResponse)
def create_fasting_window(
    data: FastingCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Start or log a fasting window"""
    user = get_or_create_user(db, discord_id)

    fasting = FastingWindow(
        user_id=user.id,
        started_at=data.started_at,
        ended_at=data.ended_at,
        fasting_type=data.fasting_type,
        notes=data.notes
    )
    db.add(fasting)
    db.commit()
    db.refresh(fasting)

    response = FastingResponse.model_validate(fasting)
    response.duration_hours = calculate_duration(fasting.started_at, fasting.ended_at)
    return response


@router.get("/active", response_model=FastingResponse | None)
def get_active_fast(discord_id: str, db: Session = Depends(get_db)):
    """Get currently active fasting window (if any)"""
    user = get_or_create_user(db, discord_id)

    fasting = db.query(FastingWindow).filter(
        FastingWindow.user_id == user.id,
        FastingWindow.ended_at.is_(None)
    ).order_by(FastingWindow.started_at.desc()).first()

    if not fasting:
        return None

    response = FastingResponse.model_validate(fasting)
    response.duration_hours = calculate_duration(fasting.started_at, datetime.utcnow())
    return response


@router.post("/end", response_model=FastingResponse)
def end_fasting_window(discord_id: str, db: Session = Depends(get_db)):
    """End the currently active fasting window"""
    user = get_or_create_user(db, discord_id)

    fasting = db.query(FastingWindow).filter(
        FastingWindow.user_id == user.id,
        FastingWindow.ended_at.is_(None)
    ).order_by(FastingWindow.started_at.desc()).first()

    if not fasting:
        raise HTTPException(status_code=404, detail="No active fasting window")

    fasting.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(fasting)

    response = FastingResponse.model_validate(fasting)
    response.duration_hours = calculate_duration(fasting.started_at, fasting.ended_at)
    return response


@router.get("/history", response_model=list[FastingResponse])
def get_fasting_history(
    discord_id: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get fasting history for the last N days"""
    user = get_or_create_user(db, discord_id)
    start_date = datetime.utcnow() - timedelta(days=days)

    fasts = db.query(FastingWindow).filter(
        FastingWindow.user_id == user.id,
        FastingWindow.started_at >= start_date
    ).order_by(FastingWindow.started_at.desc()).all()

    results = []
    for fast in fasts:
        response = FastingResponse.model_validate(fast)
        response.duration_hours = calculate_duration(
            fast.started_at,
            fast.ended_at or datetime.utcnow()
        )
        results.append(response)

    return results


@router.delete("/{fast_id}")
def delete_fasting_window(fast_id: int, discord_id: str, db: Session = Depends(get_db)):
    """Delete a fasting window"""
    user = get_or_create_user(db, discord_id)

    fasting = db.query(FastingWindow).filter(
        FastingWindow.id == fast_id,
        FastingWindow.user_id == user.id
    ).first()

    if not fasting:
        raise HTTPException(status_code=404, detail="Fasting window not found")

    db.delete(fasting)
    db.commit()
    return {"message": "Deleted", "id": fast_id}
