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


from ..models import Workout, User
from ..schemas import WorkoutCreate, WorkoutResponse

router = APIRouter(prefix="/workouts", tags=["workouts"])


def get_or_create_user(db: Session, discord_id: str) -> User:
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/", response_model=WorkoutResponse)
def log_workout(
    data: WorkoutCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Log a workout session"""
    user = get_or_create_user(db, discord_id)

    workout = Workout(
        user_id=user.id,
        date=data.date or get_eastern_today(),
        workout_type=data.workout_type,
        duration_minutes=data.duration_minutes,
        calories_burned=data.calories_burned,
        description=data.description
    )
    db.add(workout)
    db.commit()
    db.refresh(workout)
    return workout


@router.get("/today", response_model=list[WorkoutResponse])
def get_today_workouts(discord_id: str, db: Session = Depends(get_db)):
    """Get all workouts for today"""
    user = get_or_create_user(db, discord_id)
    today = get_eastern_today()

    workouts = db.query(Workout).filter(
        Workout.user_id == user.id,
        Workout.date == today
    ).all()

    return workouts


@router.get("/history", response_model=list[WorkoutResponse])
def get_workout_history(
    discord_id: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get workout history for the last N days"""
    user = get_or_create_user(db, discord_id)
    start_date = get_eastern_today() - timedelta(days=days)

    workouts = db.query(Workout).filter(
        Workout.user_id == user.id,
        Workout.date >= start_date
    ).order_by(Workout.date.desc()).all()

    return workouts


@router.delete("/{workout_id}")
def delete_workout(workout_id: int, discord_id: str, db: Session = Depends(get_db)):
    """Delete a workout log"""
    user = get_or_create_user(db, discord_id)

    workout = db.query(Workout).filter(
        Workout.id == workout_id,
        Workout.user_id == user.id
    ).first()

    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    db.delete(workout)
    db.commit()
    return {"message": "Deleted", "id": workout_id}
