"""
Conversation router for AI-powered chat, recipes, meal plans, and reminders.
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Conversation, Message, Recipe, MealPlan, GroceryList, Reminder
from ..schemas import (
    ChatRequest, ChatResponse,
    ConversationResponse, MessageResponse,
    RecipeCreate, RecipeResponse,
    MealPlanResponse, GroceryListResponse,
    ReminderCreate, ReminderResponse,
    ReminderTrigger
)
from ..services.conversation_manager import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
    process_message
)
from ..services.recipe_service import (
    generate_recipe,
    save_recipe,
    get_user_recipes,
    format_recipe_for_discord,
    recipe_to_response
)
from ..services.meal_planner import (
    generate_meal_plan,
    get_current_meal_plan,
    generate_grocery_list,
    get_grocery_lists,
    format_meal_plan_for_discord,
    format_grocery_list_for_discord
)
from ..services.reminder_scheduler import (
    create_default_reminders,
    get_user_reminders,
    toggle_reminder,
    schedule_reminder
)

router = APIRouter(tags=["conversation"])


# --- Chat Endpoints ---

@router.post("/conversation/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Main conversational endpoint. Processes natural language messages
    and routes to appropriate handlers based on intent.

    Input: {discord_id, message, image_base64?}
    Output: {response, intent, suggestions?, recipe?, meal_plan?, parsed_nutrition?}
    """
    user = get_or_create_user(db, request.discord_id)
    conversation = get_or_create_conversation(db, user.id)

    # Ensure user has default reminders
    existing_reminders = db.query(Reminder).filter(Reminder.user_id == user.id).count()
    if existing_reminders == 0:
        create_default_reminders(user.id, db)

    # Save inbound message
    save_message(db, conversation.id, "inbound", request.message)

    # Process with AI
    result = process_message(
        request.message,
        user,
        conversation,
        db,
        image_base64=request.image_base64
    )

    # Save outbound response
    save_message(db, conversation.id, "outbound", result.response, result.intent)

    return result


@router.get("/conversation/history", response_model=ConversationResponse)
def get_conversation_history(
    discord_id: str,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """Get conversation history for a user."""
    user = get_or_create_user(db, discord_id)
    conversation = get_or_create_conversation(db, user.id)

    # Get messages
    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.desc()).limit(limit).all()

    # Reverse to get chronological order
    messages = list(reversed(messages))

    return ConversationResponse(
        id=conversation.id,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        messages=[MessageResponse(
            id=m.id,
            direction=m.direction,
            content=m.content,
            ai_intent=m.ai_intent,
            created_at=m.created_at
        ) for m in messages]
    )


# --- Recipe Endpoints ---

@router.get("/recipes", response_model=list[dict])
def list_recipes(
    discord_id: str,
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db)
):
    """List user's saved recipes."""
    user = get_or_create_user(db, discord_id)
    recipes = get_user_recipes(user.id, db, limit)
    return [recipe_to_response(r) for r in recipes]


@router.post("/recipes", response_model=dict)
def create_recipe(
    recipe: RecipeCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Save a recipe."""
    user = get_or_create_user(db, discord_id)

    recipe_data = recipe.model_dump()
    saved = save_recipe(recipe_data, user.id, db)

    return recipe_to_response(saved)


@router.post("/recipes/generate", response_model=dict)
def generate_recipe_endpoint(
    query: str,
    discord_id: str,
    preferences: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Generate an AI recipe based on query and user's macro goals."""
    user = get_or_create_user(db, discord_id)

    dietary_prefs = preferences.split(",") if preferences else None
    result = generate_recipe(query, user, dietary_prefs, db)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("reason", "Recipe generation failed"))

    return result


@router.get("/recipes/{recipe_id}", response_model=dict)
def get_recipe(
    recipe_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific recipe."""
    user = get_or_create_user(db, discord_id)

    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.user_id == user.id
    ).first()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe_to_response(recipe)


@router.delete("/recipes/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Delete a recipe."""
    user = get_or_create_user(db, discord_id)

    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.user_id == user.id
    ).first()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    db.delete(recipe)
    db.commit()

    return {"message": "Recipe deleted"}


# --- Meal Plan Endpoints ---

@router.get("/meal-plans/current", response_model=dict)
def get_current_meal_plan_endpoint(
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Get current week's meal plan."""
    user = get_or_create_user(db, discord_id)
    meal_plan = get_current_meal_plan(user.id, db)

    if not meal_plan:
        raise HTTPException(status_code=404, detail="No meal plan for current week")

    return {
        "id": meal_plan.id,
        "week_start": meal_plan.week_start.isoformat(),
        "plan_data": json.loads(meal_plan.plan_data),
        "created_at": meal_plan.created_at.isoformat()
    }


@router.post("/meal-plans/generate", response_model=dict)
def generate_meal_plan_endpoint(
    discord_id: str,
    days: int = Query(default=7, le=14),
    preferences: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Generate a new meal plan based on user goals."""
    user = get_or_create_user(db, discord_id)
    result = generate_meal_plan(user, db, days, preferences)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("reason", "Meal plan generation failed"))

    return result


@router.get("/meal-plans", response_model=list[dict])
def list_meal_plans(
    discord_id: str,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db)
):
    """List user's meal plans."""
    user = get_or_create_user(db, discord_id)

    plans = db.query(MealPlan).filter(
        MealPlan.user_id == user.id
    ).order_by(MealPlan.created_at.desc()).limit(limit).all()

    return [{
        "id": p.id,
        "week_start": p.week_start.isoformat(),
        "plan_data": json.loads(p.plan_data),
        "created_at": p.created_at.isoformat()
    } for p in plans]


# --- Grocery List Endpoints ---

@router.get("/grocery-lists", response_model=list[dict])
def list_grocery_lists_endpoint(
    discord_id: str,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db)
):
    """List grocery lists."""
    user = get_or_create_user(db, discord_id)
    lists = get_grocery_lists(user.id, db, limit)

    return [{
        "id": g.id,
        "name": g.name,
        "items": json.loads(g.items) if g.items else [],
        "created_at": g.created_at.isoformat(),
        "completed_at": g.completed_at.isoformat() if g.completed_at else None
    } for g in lists]


@router.post("/grocery-lists/from-plan", response_model=dict)
def generate_grocery_list_endpoint(
    discord_id: str,
    meal_plan_id: int,
    db: Session = Depends(get_db)
):
    """Generate grocery list from meal plan."""
    user = get_or_create_user(db, discord_id)
    result = generate_grocery_list(meal_plan_id, user.id, db)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result.get("reason", "Grocery list generation failed"))

    return result


@router.get("/grocery-lists/{list_id}", response_model=dict)
def get_grocery_list(
    list_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific grocery list."""
    user = get_or_create_user(db, discord_id)

    grocery_list = db.query(GroceryList).filter(
        GroceryList.id == list_id,
        GroceryList.user_id == user.id
    ).first()

    if not grocery_list:
        raise HTTPException(status_code=404, detail="Grocery list not found")

    return {
        "id": grocery_list.id,
        "name": grocery_list.name,
        "items": json.loads(grocery_list.items) if grocery_list.items else [],
        "created_at": grocery_list.created_at.isoformat(),
        "completed_at": grocery_list.completed_at.isoformat() if grocery_list.completed_at else None
    }


@router.delete("/grocery-lists/{list_id}")
def delete_grocery_list(
    list_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Delete a grocery list."""
    user = get_or_create_user(db, discord_id)

    grocery_list = db.query(GroceryList).filter(
        GroceryList.id == list_id,
        GroceryList.user_id == user.id
    ).first()

    if not grocery_list:
        raise HTTPException(status_code=404, detail="Grocery list not found")

    db.delete(grocery_list)
    db.commit()

    return {"message": "Grocery list deleted"}


# --- Reminder Endpoints ---

@router.get("/reminders", response_model=list[ReminderResponse])
def list_reminders(
    discord_id: str,
    db: Session = Depends(get_db)
):
    """List active reminders."""
    user = get_or_create_user(db, discord_id)

    # Create defaults if none exist
    existing = db.query(Reminder).filter(Reminder.user_id == user.id).count()
    if existing == 0:
        create_default_reminders(user.id, db)

    reminders = get_user_reminders(user.id, db)

    return [ReminderResponse(
        id=r.id,
        reminder_type=r.reminder_type,
        schedule=r.schedule,
        message_template=r.message_template,
        enabled=r.enabled,
        last_sent_at=r.last_sent_at
    ) for r in reminders]


@router.post("/reminders", response_model=ReminderResponse)
def create_reminder(
    reminder: ReminderCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Create or update a reminder."""
    user = get_or_create_user(db, discord_id)

    # Check if reminder of this type already exists
    existing = db.query(Reminder).filter(
        Reminder.user_id == user.id,
        Reminder.reminder_type == reminder.reminder_type
    ).first()

    if existing:
        # Update existing
        existing.schedule = reminder.schedule
        existing.message_template = reminder.message_template
        existing.enabled = reminder.enabled
        db.commit()
        db.refresh(existing)

        # Update scheduler
        if existing.enabled:
            schedule_reminder(existing, user)

        return ReminderResponse(
            id=existing.id,
            reminder_type=existing.reminder_type,
            schedule=existing.schedule,
            message_template=existing.message_template,
            enabled=existing.enabled,
            last_sent_at=existing.last_sent_at
        )
    else:
        # Create new
        new_reminder = Reminder(
            user_id=user.id,
            reminder_type=reminder.reminder_type,
            schedule=reminder.schedule,
            message_template=reminder.message_template,
            enabled=reminder.enabled
        )
        db.add(new_reminder)
        db.commit()
        db.refresh(new_reminder)

        # Schedule if enabled
        if new_reminder.enabled:
            schedule_reminder(new_reminder, user)

        return ReminderResponse(
            id=new_reminder.id,
            reminder_type=new_reminder.reminder_type,
            schedule=new_reminder.schedule,
            message_template=new_reminder.message_template,
            enabled=new_reminder.enabled,
            last_sent_at=new_reminder.last_sent_at
        )


@router.put("/reminders/{reminder_id}/toggle", response_model=ReminderResponse)
def toggle_reminder_endpoint(
    reminder_id: int,
    enabled: bool,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Enable or disable a reminder."""
    user = get_or_create_user(db, discord_id)
    reminder = toggle_reminder(reminder_id, user.id, enabled, db)

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    return ReminderResponse(
        id=reminder.id,
        reminder_type=reminder.reminder_type,
        schedule=reminder.schedule,
        message_template=reminder.message_template,
        enabled=reminder.enabled,
        last_sent_at=reminder.last_sent_at
    )


@router.delete("/reminders/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Delete a reminder."""
    user = get_or_create_user(db, discord_id)

    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == user.id
    ).first()

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    # Remove from scheduler
    from ..services.reminder_scheduler import remove_reminder
    remove_reminder(reminder_id)

    db.delete(reminder)
    db.commit()

    return {"message": "Reminder deleted"}


@router.post("/reminders/send/{reminder_id}")
async def trigger_reminder(
    reminder_id: int,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Manually trigger a reminder (for testing)."""
    user = get_or_create_user(db, discord_id)

    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == user.id
    ).first()

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    from ..services.reminder_scheduler import execute_reminder
    await execute_reminder(reminder_id, user.id)

    return {"message": "Reminder triggered"}
