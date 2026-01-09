from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Text,
    Numeric, Boolean, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


class MoodLevel(enum.Enum):
    TERRIBLE = 1
    BAD = 2
    OKAY = 3
    GOOD = 4
    GREAT = 5


class WorkoutType(enum.Enum):
    CARDIO = "cardio"
    STRENGTH = "strength"
    FLEXIBILITY = "flexibility"
    SPORTS = "sports"
    WALKING = "walking"
    OTHER = "other"


class User(Base):
    """User profile - ready for multi-user in v3"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    discord_id = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Goals
    target_weight = Column(Numeric(5, 1))  # e.g., 180.0 lbs
    daily_calorie_goal = Column(Integer, default=2000)
    daily_protein_goal = Column(Integer, default=150)  # grams
    daily_carb_goal = Column(Integer, default=200)
    daily_fat_goal = Column(Integer, default=65)
    daily_water_goal = Column(Integer, default=64)  # oz

    # Relationships
    weight_logs = relationship("WeightLog", back_populates="user")
    nutrition_logs = relationship("NutritionLog", back_populates="user")
    fasting_windows = relationship("FastingWindow", back_populates="user")
    workouts = relationship("Workout", back_populates="user")
    daily_metrics = relationship("DailyMetric", back_populates="user")


class WeightLog(Base):
    """Daily weight measurements"""
    __tablename__ = "weight_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    logged_at = Column(DateTime, default=datetime.utcnow)
    date = Column(Date, nullable=False)
    weight_lbs = Column(Numeric(5, 1), nullable=False)  # e.g., 273.5
    notes = Column(Text)

    user = relationship("User", back_populates="weight_logs")


class NutritionLog(Base):
    """Food and water intake"""
    __tablename__ = "nutrition_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    logged_at = Column(DateTime, default=datetime.utcnow)

    # Raw input for debugging/reprocessing
    raw_input = Column(Text)

    # Parsed data
    description = Column(String(500))
    calories = Column(Integer)
    protein_g = Column(Numeric(5, 1))
    carbs_g = Column(Numeric(5, 1))
    fat_g = Column(Numeric(5, 1))
    fiber_g = Column(Numeric(5, 1))
    water_oz = Column(Numeric(5, 1))

    # USDA reference (if looked up)
    usda_fdc_id = Column(Integer)

    # Meal categorization
    meal_type = Column(String(20))  # breakfast, lunch, dinner, snack

    user = relationship("User", back_populates="nutrition_logs")


class FastingWindow(Base):
    """Intermittent fasting tracking"""
    __tablename__ = "fasting_windows"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime)
    fasting_type = Column(String(20))  # 16:8, 18:6, 24hr, etc.
    notes = Column(Text)

    user = relationship("User", back_populates="fasting_windows")


class Workout(Base):
    """Exercise sessions"""
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    logged_at = Column(DateTime, default=datetime.utcnow)
    date = Column(Date, nullable=False)

    workout_type = Column(SQLEnum(WorkoutType), default=WorkoutType.OTHER)
    duration_minutes = Column(Integer)
    calories_burned = Column(Integer)
    description = Column(Text)
    raw_input = Column(Text)

    user = relationship("User", back_populates="workouts")


class DailyMetric(Base):
    """Daily wellness metrics (sleep, mood)"""
    __tablename__ = "daily_metrics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, unique=True)

    sleep_hours = Column(Numeric(3, 1))
    sleep_quality = Column(Integer)  # 1-5 scale
    mood = Column(SQLEnum(MoodLevel))
    energy_level = Column(Integer)  # 1-5 scale
    notes = Column(Text)

    user = relationship("User", back_populates="daily_metrics")
