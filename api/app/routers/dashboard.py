from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..database import get_db

# Timezone configuration - all date calculations use Eastern time
EASTERN = ZoneInfo("America/New_York")


def get_eastern_today() -> date:
    """Get today's date in Eastern time"""
    return datetime.now(EASTERN).date()


def get_eastern_day_boundaries(day: date) -> tuple[datetime, datetime]:
    """Get UTC datetime boundaries for a day in Eastern time"""
    # Create Eastern time boundaries
    day_start_eastern = datetime.combine(day, datetime.min.time()).replace(tzinfo=EASTERN)
    day_end_eastern = datetime.combine(day, datetime.max.time()).replace(tzinfo=EASTERN)
    # Convert to UTC for database queries
    day_start_utc = day_start_eastern.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    day_end_utc = day_end_eastern.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return day_start_utc, day_end_utc


from ..models import User, WeightLog, NutritionLog, Workout, DailyMetric
from ..schemas import DailySummary, UserGoals

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_or_create_user(db: Session, discord_id: str) -> User:
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/today", response_model=DailySummary)
def get_today_summary(discord_id: str, db: Session = Depends(get_db)):
    """Get aggregated summary for today (Eastern time)"""
    user = get_or_create_user(db, discord_id)
    today = get_eastern_today()
    day_start, day_end = get_eastern_day_boundaries(today)

    # Get latest weight
    weight_log = db.query(WeightLog).filter(
        WeightLog.user_id == user.id
    ).order_by(WeightLog.date.desc()).first()

    # Aggregate nutrition for today (using Eastern time boundaries)
    nutrition = db.query(
        func.coalesce(func.sum(NutritionLog.calories), 0).label("calories"),
        func.coalesce(func.sum(NutritionLog.protein_g), 0).label("protein"),
        func.coalesce(func.sum(NutritionLog.carbs_g), 0).label("carbs"),
        func.coalesce(func.sum(NutritionLog.fat_g), 0).label("fat"),
        func.coalesce(func.sum(NutritionLog.fiber_g), 0).label("fiber"),
        func.coalesce(func.sum(NutritionLog.water_oz), 0).label("water"),
    ).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= day_start,
        NutritionLog.logged_at < day_end
    ).first()

    # Aggregate workouts for today
    workout_minutes = db.query(
        func.coalesce(func.sum(Workout.duration_minutes), 0)
    ).filter(
        Workout.user_id == user.id,
        Workout.date == today
    ).scalar()

    # Get daily metrics
    daily_metric = db.query(DailyMetric).filter(
        DailyMetric.user_id == user.id,
        DailyMetric.date == today
    ).first()

    # Build summary
    calorie_goal = user.daily_calorie_goal or 2000
    protein_goal = user.daily_protein_goal or 150
    water_goal = user.daily_water_goal or 64

    calories = int(nutrition.calories) if nutrition else 0
    protein = float(nutrition.protein) if nutrition else 0
    water = float(nutrition.water) if nutrition else 0

    return DailySummary(
        date=today,
        weight=float(weight_log.weight_lbs) if weight_log else None,
        calories=calories,
        protein_g=protein,
        carbs_g=float(nutrition.carbs) if nutrition else 0,
        fat_g=float(nutrition.fat) if nutrition else 0,
        fiber_g=float(nutrition.fiber) if nutrition else 0,
        water_oz=water,
        workout_minutes=workout_minutes or 0,
        sleep_hours=float(daily_metric.sleep_hours) if daily_metric and daily_metric.sleep_hours else None,
        mood=daily_metric.mood.name if daily_metric and daily_metric.mood else None,
        calorie_goal=calorie_goal,
        protein_goal=protein_goal,
        water_goal=water_goal,
        calorie_pct=round((calories / calorie_goal) * 100, 1) if calorie_goal else 0,
        protein_pct=round((protein / protein_goal) * 100, 1) if protein_goal else 0,
        water_pct=round((water / water_goal) * 100, 1) if water_goal else 0,
    )


@router.get("/week", response_model=list[DailySummary])
def get_week_summary(discord_id: str, db: Session = Depends(get_db)):
    """Get daily summaries for the past 7 days (Eastern time)"""
    user = get_or_create_user(db, discord_id)
    summaries = []

    for i in range(7):
        day = get_eastern_today() - timedelta(days=i)
        day_start, day_end = get_eastern_day_boundaries(day)

        # Weight for this day (or most recent before)
        weight_log = db.query(WeightLog).filter(
            WeightLog.user_id == user.id,
            WeightLog.date <= day
        ).order_by(WeightLog.date.desc()).first()

        # Nutrition aggregates (using Eastern time boundaries)
        nutrition = db.query(
            func.coalesce(func.sum(NutritionLog.calories), 0).label("calories"),
            func.coalesce(func.sum(NutritionLog.protein_g), 0).label("protein"),
            func.coalesce(func.sum(NutritionLog.carbs_g), 0).label("carbs"),
            func.coalesce(func.sum(NutritionLog.fat_g), 0).label("fat"),
            func.coalesce(func.sum(NutritionLog.fiber_g), 0).label("fiber"),
            func.coalesce(func.sum(NutritionLog.water_oz), 0).label("water"),
        ).filter(
            NutritionLog.user_id == user.id,
            NutritionLog.logged_at >= day_start,
            NutritionLog.logged_at < day_end
        ).first()

        workout_minutes = db.query(
            func.coalesce(func.sum(Workout.duration_minutes), 0)
        ).filter(
            Workout.user_id == user.id,
            Workout.date == day
        ).scalar()

        daily_metric = db.query(DailyMetric).filter(
            DailyMetric.user_id == user.id,
            DailyMetric.date == day
        ).first()

        calorie_goal = user.daily_calorie_goal or 2000
        protein_goal = user.daily_protein_goal or 150
        water_goal = user.daily_water_goal or 64

        calories = int(nutrition.calories) if nutrition else 0
        protein = float(nutrition.protein) if nutrition else 0
        water = float(nutrition.water) if nutrition else 0

        summaries.append(DailySummary(
            date=day,
            weight=float(weight_log.weight_lbs) if weight_log else None,
            calories=calories,
            protein_g=protein,
            carbs_g=float(nutrition.carbs) if nutrition else 0,
            fat_g=float(nutrition.fat) if nutrition else 0,
            fiber_g=float(nutrition.fiber) if nutrition else 0,
            water_oz=water,
            workout_minutes=workout_minutes or 0,
            sleep_hours=float(daily_metric.sleep_hours) if daily_metric and daily_metric.sleep_hours else None,
            mood=daily_metric.mood.name if daily_metric and daily_metric.mood else None,
            calorie_goal=calorie_goal,
            protein_goal=protein_goal,
            water_goal=water_goal,
            calorie_pct=round((calories / calorie_goal) * 100, 1) if calorie_goal else 0,
            protein_pct=round((protein / protein_goal) * 100, 1) if protein_goal else 0,
            water_pct=round((water / water_goal) * 100, 1) if water_goal else 0,
        ))

    return summaries


@router.get("/goals", response_model=UserGoals)
def get_user_goals(discord_id: str, db: Session = Depends(get_db)):
    """Get user's current goals"""
    user = get_or_create_user(db, discord_id)

    return UserGoals(
        target_weight=float(user.target_weight) if user.target_weight else 180.0,
        daily_calorie_goal=user.daily_calorie_goal or 2000,
        daily_protein_goal=user.daily_protein_goal or 150,
        daily_carb_goal=user.daily_carb_goal or 200,
        daily_fat_goal=user.daily_fat_goal or 65,
        daily_water_goal=user.daily_water_goal or 64,
    )


@router.put("/goals", response_model=UserGoals)
def update_user_goals(
    goals: UserGoals,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Update user's goals"""
    user = get_or_create_user(db, discord_id)

    user.target_weight = goals.target_weight
    user.daily_calorie_goal = goals.daily_calorie_goal
    user.daily_protein_goal = goals.daily_protein_goal
    user.daily_carb_goal = goals.daily_carb_goal
    user.daily_fat_goal = goals.daily_fat_goal
    user.daily_water_goal = goals.daily_water_goal

    db.commit()
    db.refresh(user)

    return goals
