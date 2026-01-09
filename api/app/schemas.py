from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from .models import MoodLevel, WorkoutType


# --- Parse Request/Response ---
class ParseRequest(BaseModel):
    text: str
    discord_id: str


class ParsedNutrition(BaseModel):
    description: str
    calories: Optional[int] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    water_oz: Optional[float] = None
    meal_type: Optional[str] = None
    usda_fdc_id: Optional[int] = None


class ParseResponse(BaseModel):
    success: bool
    message: str
    parsed: Optional[ParsedNutrition] = None
    log_id: Optional[int] = None


# --- Weight ---
class WeightCreate(BaseModel):
    weight_lbs: float
    date: Optional[date] = None
    notes: Optional[str] = None


class WeightResponse(BaseModel):
    id: int
    date: date
    weight_lbs: float
    notes: Optional[str]
    logged_at: datetime

    class Config:
        from_attributes = True


# --- Nutrition ---
class NutritionCreate(BaseModel):
    description: str
    calories: Optional[int] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    water_oz: Optional[float] = None
    meal_type: Optional[str] = None
    raw_input: Optional[str] = None


class NutritionResponse(BaseModel):
    id: int
    description: str
    calories: Optional[int]
    protein_g: Optional[float]
    carbs_g: Optional[float]
    fat_g: Optional[float]
    fiber_g: Optional[float]
    water_oz: Optional[float]
    meal_type: Optional[str]
    logged_at: datetime

    class Config:
        from_attributes = True


# --- Workout ---
class WorkoutCreate(BaseModel):
    workout_type: WorkoutType = WorkoutType.OTHER
    duration_minutes: Optional[int] = None
    calories_burned: Optional[int] = None
    description: Optional[str] = None
    date: Optional[date] = None


class WorkoutResponse(BaseModel):
    id: int
    date: date
    workout_type: WorkoutType
    duration_minutes: Optional[int]
    calories_burned: Optional[int]
    description: Optional[str]
    logged_at: datetime

    class Config:
        from_attributes = True


# --- Fasting ---
class FastingCreate(BaseModel):
    started_at: datetime
    ended_at: Optional[datetime] = None
    fasting_type: Optional[str] = "16:8"
    notes: Optional[str] = None


class FastingResponse(BaseModel):
    id: int
    started_at: datetime
    ended_at: Optional[datetime]
    fasting_type: Optional[str]
    notes: Optional[str]
    duration_hours: Optional[float] = None

    class Config:
        from_attributes = True


# --- Daily Metrics ---
class DailyMetricCreate(BaseModel):
    date: Optional[date] = None
    sleep_hours: Optional[float] = None
    sleep_quality: Optional[int] = None
    mood: Optional[MoodLevel] = None
    energy_level: Optional[int] = None
    notes: Optional[str] = None


class DailyMetricResponse(BaseModel):
    id: int
    date: date
    sleep_hours: Optional[float]
    sleep_quality: Optional[int]
    mood: Optional[MoodLevel]
    energy_level: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


# --- Dashboard ---
class DailySummary(BaseModel):
    date: date
    weight: Optional[float] = None
    calories: int = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    water_oz: float = 0
    workout_minutes: int = 0
    sleep_hours: Optional[float] = None
    mood: Optional[str] = None

    # Goals comparison
    calorie_goal: int
    protein_goal: int
    water_goal: int
    calorie_pct: float = 0
    protein_pct: float = 0
    water_pct: float = 0


class UserGoals(BaseModel):
    target_weight: Optional[float] = 180.0
    daily_calorie_goal: int = 2000
    daily_protein_goal: int = 150
    daily_carb_goal: int = 200
    daily_fat_goal: int = 65
    daily_water_goal: int = 64
