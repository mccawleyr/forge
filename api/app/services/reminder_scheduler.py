"""
APScheduler setup for scheduled reminders.
"""
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import httpx

from ..config import get_settings
from ..models import Reminder, User
from ..database import get_db, engine

settings = get_settings()

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


# Default reminder templates
DEFAULT_REMINDERS = [
    {
        "reminder_type": "morning",
        "schedule": "0 8 * * *",  # 8:00 AM daily
        "message_template": "Good morning! Ready to log breakfast? Just tell me what you had."
    },
    {
        "reminder_type": "water",
        "schedule": "0 9-21/2 * * *",  # Every 2 hours from 9am-9pm
        "message_template": "Hydration check - how much water have you had? Reply with something like '16oz water'"
    },
    {
        "reminder_type": "lunch",
        "schedule": "30 12 * * *",  # 12:30 PM daily
        "message_template": "Lunchtime! What are you having? I can help log it."
    },
    {
        "reminder_type": "dinner",
        "schedule": "30 18 * * *",  # 6:30 PM daily
        "message_template": "Dinner time - what's on the menu tonight?"
    },
    {
        "reminder_type": "summary",
        "schedule": "0 21 * * *",  # 9:00 PM daily
        "message_template": "daily_summary"  # Special template that triggers summary generation
    }
]


def init_scheduler(database_url: str = None) -> AsyncIOScheduler:
    """
    Initialize the APScheduler with SQLAlchemy job store.

    Args:
        database_url: Database URL for job storage (uses settings if not provided)

    Returns:
        Configured AsyncIOScheduler instance
    """
    global scheduler

    if scheduler is not None:
        return scheduler

    db_url = database_url or settings.database_url

    jobstores = {
        'default': SQLAlchemyJobStore(engine=engine)
    }

    job_defaults = {
        'coalesce': True,  # Combine multiple missed runs into one
        'max_instances': 1,  # Only one instance of each job at a time
        'misfire_grace_time': 60 * 15  # 15 min grace period for missed jobs
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        job_defaults=job_defaults,
        timezone='America/New_York'
    )

    return scheduler


def start_scheduler():
    """Start the scheduler if not already running."""
    global scheduler

    if scheduler is None:
        scheduler = init_scheduler()

    if not scheduler.running:
        scheduler.start()
        print("Reminder scheduler started")


def shutdown_scheduler():
    """Gracefully shutdown the scheduler."""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        print("Reminder scheduler stopped")


def parse_schedule(schedule_str: str) -> CronTrigger | IntervalTrigger:
    """
    Parse a schedule string into an APScheduler trigger.

    Supports:
    - Cron format: "0 8 * * *" (minute hour day month day_of_week)
    - Interval format: "every 2h", "every 30m"
    """
    schedule_str = schedule_str.strip().lower()

    # Check for interval format
    if schedule_str.startswith("every "):
        interval_str = schedule_str[6:].strip()

        if interval_str.endswith("h"):
            hours = int(interval_str[:-1])
            return IntervalTrigger(hours=hours)
        elif interval_str.endswith("m"):
            minutes = int(interval_str[:-1])
            return IntervalTrigger(minutes=minutes)
        else:
            raise ValueError(f"Invalid interval format: {schedule_str}")

    # Assume cron format
    parts = schedule_str.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week
        )

    raise ValueError(f"Invalid schedule format: {schedule_str}")


async def execute_reminder(reminder_id: int, user_id: int):
    """
    Execute a reminder by sending notification to the bot.

    This function is called by the scheduler when a reminder is due.
    """
    # Get fresh database session
    db = next(get_db())

    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if not reminder or not user or not reminder.enabled:
            return

        # Build the message
        message = reminder.message_template

        # Handle special templates
        if message == "daily_summary":
            message = await generate_daily_summary(user, db)

        # Send to bot notification endpoint
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{settings.bot_notification_url}/notify",
                    json={
                        "discord_id": user.discord_id,
                        "message": message,
                        "reminder_id": reminder_id
                    }
                )
            except Exception as e:
                print(f"Failed to send reminder notification: {e}")

        # Update last_sent_at
        reminder.last_sent_at = datetime.utcnow()
        db.commit()

    finally:
        db.close()


async def generate_daily_summary(user: User, db: Session) -> str:
    """Generate an end-of-day summary message."""
    from .conversation_manager import get_daily_progress

    progress = get_daily_progress(db, user.id)

    cal_pct = round(progress["calories"] / user.daily_calorie_goal * 100) if user.daily_calorie_goal else 0
    protein_pct = round(progress["protein"] / user.daily_protein_goal * 100) if user.daily_protein_goal else 0
    water_pct = round(progress["water"] / user.daily_water_goal * 100) if user.daily_water_goal else 0

    message = f"**Daily Summary**\n"
    message += f"- Calories: {progress['calories']} / {user.daily_calorie_goal} ({cal_pct}%)\n"
    message += f"- Protein: {round(progress['protein'], 1)}g / {user.daily_protein_goal}g ({protein_pct}%)\n"
    message += f"- Water: {round(progress['water'], 1)}oz / {user.daily_water_goal}oz ({water_pct}%)\n"

    # Add encouragement
    if cal_pct >= 80 and cal_pct <= 110 and protein_pct >= 80:
        message += "\nGreat job today! Keep it up!"
    elif protein_pct < 60:
        message += "\nConsider adding more protein tomorrow."
    elif water_pct < 60:
        message += "\nTry to drink more water tomorrow!"

    return message


def schedule_reminder(reminder: Reminder, user: User):
    """
    Add a reminder job to the scheduler.

    Args:
        reminder: Reminder model instance
        user: User model instance
    """
    global scheduler

    if scheduler is None:
        scheduler = init_scheduler()

    job_id = f"reminder_{reminder.id}"

    # Remove existing job if any
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    if not reminder.enabled:
        return

    try:
        trigger = parse_schedule(reminder.schedule)

        scheduler.add_job(
            execute_reminder,
            trigger=trigger,
            id=job_id,
            args=[reminder.id, user.id],
            name=f"{reminder.reminder_type} reminder for user {user.id}",
            replace_existing=True
        )

        print(f"Scheduled reminder {job_id}: {reminder.reminder_type}")

    except Exception as e:
        print(f"Failed to schedule reminder {reminder.id}: {e}")


def remove_reminder(reminder_id: int):
    """Remove a reminder job from the scheduler."""
    global scheduler

    if scheduler is None:
        return

    job_id = f"reminder_{reminder_id}"

    try:
        scheduler.remove_job(job_id)
        print(f"Removed reminder job {job_id}")
    except Exception as e:
        print(f"Failed to remove reminder {job_id}: {e}")


def load_user_reminders(db: Session):
    """Load all enabled reminders from database into scheduler."""
    reminders = db.query(Reminder).filter(Reminder.enabled == True).all()

    for reminder in reminders:
        user = db.query(User).filter(User.id == reminder.user_id).first()
        if user:
            schedule_reminder(reminder, user)

    print(f"Loaded {len(reminders)} reminders into scheduler")


def create_default_reminders(user_id: int, db: Session) -> list[Reminder]:
    """
    Create default reminders for a new user.

    Args:
        user_id: User ID
        db: Database session

    Returns:
        List of created Reminder objects
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []

    # Check if user already has reminders
    existing = db.query(Reminder).filter(Reminder.user_id == user_id).count()
    if existing > 0:
        return []

    created = []

    for template in DEFAULT_REMINDERS:
        reminder = Reminder(
            user_id=user_id,
            reminder_type=template["reminder_type"],
            schedule=template["schedule"],
            message_template=template["message_template"],
            enabled=False  # Start disabled, user can enable
        )
        db.add(reminder)
        created.append(reminder)

    db.commit()

    # Refresh all to get IDs
    for r in created:
        db.refresh(r)

    return created


def get_user_reminders(user_id: int, db: Session) -> list[Reminder]:
    """Get all reminders for a user."""
    return db.query(Reminder).filter(Reminder.user_id == user_id).all()


def toggle_reminder(reminder_id: int, user_id: int, enabled: bool, db: Session) -> Optional[Reminder]:
    """Enable or disable a reminder."""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == user_id
    ).first()

    if not reminder:
        return None

    reminder.enabled = enabled
    db.commit()
    db.refresh(reminder)

    # Update scheduler
    user = db.query(User).filter(User.id == user_id).first()
    if enabled:
        schedule_reminder(reminder, user)
    else:
        remove_reminder(reminder_id)

    return reminder
