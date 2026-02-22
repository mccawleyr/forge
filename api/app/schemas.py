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


# --- Conversation ---
class ChatRequest(BaseModel):
    discord_id: str
    message: str
    image_base64: Optional[str] = None  # For food photo analysis


class ChatResponse(BaseModel):
    response: str
    intent: str
    suggestions: Optional[list[str]] = None
    recipe: Optional[dict] = None
    meal_plan: Optional[dict] = None
    parsed_nutrition: Optional[ParsedNutrition] = None


class MessageResponse(BaseModel):
    id: int
    direction: str
    content: str
    ai_intent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: int
    started_at: datetime
    last_message_at: datetime
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True


# --- Recipe ---
class RecipeCreate(BaseModel):
    name: str
    ingredients: list[str]
    instructions: str
    servings: int = 1
    calories_per_serving: Optional[int] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    source: str = "user"


class RecipeResponse(BaseModel):
    id: int
    name: str
    ingredients: list[str]
    instructions: str
    servings: int
    calories_per_serving: Optional[int]
    protein_g: Optional[float]
    carbs_g: Optional[float]
    fat_g: Optional[float]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Meal Plan ---
class MealPlanDay(BaseModel):
    breakfast: Optional[str] = None
    lunch: Optional[str] = None
    dinner: Optional[str] = None
    snacks: Optional[list[str]] = None


class MealPlanResponse(BaseModel):
    id: int
    week_start: date
    plan_data: dict[str, MealPlanDay]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Grocery List ---
class GroceryItem(BaseModel):
    name: str
    quantity: Optional[str] = None
    checked: bool = False


class GroceryListCreate(BaseModel):
    name: str
    items: list[GroceryItem]


class GroceryListResponse(BaseModel):
    id: int
    name: str
    items: list[GroceryItem]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Reminders ---
class ReminderCreate(BaseModel):
    reminder_type: str  # water, log_meal, check_in, custom
    schedule: str  # cron format or "every Xh"
    message_template: str
    enabled: bool = True


class ReminderResponse(BaseModel):
    id: int
    reminder_type: str
    schedule: str
    message_template: str
    enabled: bool
    last_sent_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReminderTrigger(BaseModel):
    """Used by scheduler to trigger a reminder"""
    reminder_id: int
    discord_id: str
    message: str
