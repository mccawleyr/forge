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
    conversations = relationship("Conversation", back_populates="user")
    recipes = relationship("Recipe", back_populates="user")
    meal_plans = relationship("MealPlan", back_populates="user")
    grocery_lists = relationship("GroceryList", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")


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


# --- Conversational AI Models ---

class Conversation(Base):
    """Tracks conversation sessions with users"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    context = Column(Text)  # JSON: current topic, intent history

    messages = relationship("Message", back_populates="conversation")
    user = relationship("User", back_populates="conversations")


class Message(Base):
    """Individual messages in a conversation"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    direction = Column(String(10))  # 'inbound' or 'outbound'
    content = Column(Text)
    ai_intent = Column(String(50))  # parsed intent
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Recipe(Base):
    """User recipes with macros"""
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    ingredients = Column(Text)  # JSON array
    instructions = Column(Text)
    servings = Column(Integer, default=1)
    calories_per_serving = Column(Integer)
    protein_g = Column(Numeric(5, 1))
    carbs_g = Column(Numeric(5, 1))
    fat_g = Column(Numeric(5, 1))
    source = Column(String(50))  # 'ai', 'user', 'url'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="recipes")


class MealPlan(Base):
    """Weekly meal plans"""
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    plan_data = Column(Text)  # JSON: {mon: {breakfast, lunch, dinner}, ...}
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="meal_plans")


class GroceryList(Base):
    """Shopping lists"""
    __tablename__ = "grocery_lists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100))
    items = Column(Text)  # JSON array: [{name, quantity, checked}]
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="grocery_lists")


class Reminder(Base):
    """Scheduled reminder configurations"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reminder_type = Column(String(30))  # water, log_meal, check_in, custom
    schedule = Column(String(50))  # cron: "0 8 * * *" or interval: "every 2h"
    message_template = Column(Text)
    enabled = Column(Boolean, default=True)
    last_sent_at = Column(DateTime)

    user = relationship("User", back_populates="reminders")
