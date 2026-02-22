"""
Weekly meal plan generation and grocery list management.
"""
import json
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from anthropic import Anthropic

from ..config import get_settings
from ..models import User, MealPlan, GroceryList, Recipe
from . import openai_service

settings = get_settings()
anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

MEAL_PLAN_SYSTEM_PROMPT = """You are a meal planning assistant that creates balanced weekly meal plans.

User's daily macro goals:
- Calories: {calorie_goal}
- Protein: {protein_goal}g
- Carbs: {carb_goal}g
- Fat: {fat_goal}g

Create a {days}-day meal plan that:
1. Helps the user meet their daily macro goals
2. Provides variety in meals
3. Uses practical, common ingredients
4. Includes simple, quick options for busy days
5. Has some meal prep friendly options

Respond with ONLY valid JSON:
{{
  "monday": {{
    "breakfast": "meal description (approx Xcal, Xg protein)",
    "lunch": "meal description (approx Xcal, Xg protein)",
    "dinner": "meal description (approx Xcal, Xg protein)",
    "snacks": ["snack 1", "snack 2"]
  }},
  "tuesday": {{ ... }},
  ...
}}

Use lowercase day names. Include approximate calories and protein for each main meal."""


GROCERY_LIST_PROMPT = """Based on this meal plan, create a consolidated grocery list.
Group items by category (Produce, Protein, Dairy, Pantry, etc.) and combine quantities for items used multiple times.

Meal Plan:
{meal_plan}

Respond with ONLY valid JSON:
{{
  "Produce": ["item 1 with quantity", "item 2 with quantity"],
  "Protein": ["item 1 with quantity"],
  "Dairy": ["item 1 with quantity"],
  "Pantry": ["item 1 with quantity"],
  "Other": ["item 1 with quantity"]
}}"""


def generate_meal_plan(
    user: User,
    db: Session,
    days: int = 7,
    preferences: str = None
) -> dict:
    """
    Generate a weekly meal plan based on user's macro goals.

    Args:
        user: User with macro goals
        db: Database session
        days: Number of days to plan (default 7)
        preferences: Optional dietary preferences/restrictions

    Returns:
        Meal plan dict with daily meals
    """
    system_prompt = MEAL_PLAN_SYSTEM_PROMPT.format(
        calorie_goal=user.daily_calorie_goal,
        protein_goal=user.daily_protein_goal,
        carb_goal=user.daily_carb_goal,
        fat_goal=user.daily_fat_goal,
        days=days
    )

    user_prompt = f"Create a {days}-day meal plan for me."
    if preferences:
        user_prompt += f"\n\nPreferences/restrictions: {preferences}"

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        result_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        plan_data = json.loads(result_text)

        # Save to database
        week_start = get_week_start(date.today())
        meal_plan = MealPlan(
            user_id=user.id,
            week_start=week_start,
            plan_data=json.dumps(plan_data)
        )
        db.add(meal_plan)
        db.commit()
        db.refresh(meal_plan)

        return {
            "id": meal_plan.id,
            "week_start": week_start.isoformat(),
            "plan_data": plan_data
        }

    except json.JSONDecodeError as e:
        return {"error": "Failed to parse meal plan", "reason": str(e)}
    except Exception as e:
        print(f"Meal plan generation error: {e}")

        # Fallback to OpenAI
        result = openai_service.parse_json_response(
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        if result:
            week_start = get_week_start(date.today())
            meal_plan = MealPlan(
                user_id=user.id,
                week_start=week_start,
                plan_data=json.dumps(result)
            )
            db.add(meal_plan)
            db.commit()
            db.refresh(meal_plan)

            return {
                "id": meal_plan.id,
                "week_start": week_start.isoformat(),
                "plan_data": result
            }

        return {"error": "Meal plan generation failed", "reason": str(e)}


def get_week_start(d: date) -> date:
    """Get the Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def get_current_meal_plan(user_id: int, db: Session) -> Optional[MealPlan]:
    """Get the meal plan for the current week."""
    week_start = get_week_start(date.today())

    return db.query(MealPlan).filter(
        MealPlan.user_id == user_id,
        MealPlan.week_start == week_start
    ).first()


def generate_grocery_list(
    meal_plan_id: int,
    user_id: int,
    db: Session
) -> dict:
    """
    Generate a grocery list from a meal plan.

    Args:
        meal_plan_id: ID of the meal plan
        user_id: User ID for ownership verification
        db: Database session

    Returns:
        Grocery list dict with categorized items
    """
    meal_plan = db.query(MealPlan).filter(
        MealPlan.id == meal_plan_id,
        MealPlan.user_id == user_id
    ).first()

    if not meal_plan:
        return {"error": "Meal plan not found"}

    plan_data = json.loads(meal_plan.plan_data)

    prompt = GROCERY_LIST_PROMPT.format(meal_plan=json.dumps(plan_data, indent=2))

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system="You are a helpful assistant that creates organized grocery lists.",
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        grocery_data = json.loads(result_text)

        # Convert to flat list with categories
        items = []
        for category, category_items in grocery_data.items():
            for item in category_items:
                items.append({
                    "name": item,
                    "category": category,
                    "checked": False
                })

        # Save grocery list
        grocery_list = GroceryList(
            user_id=user_id,
            name=f"Groceries for week of {meal_plan.week_start.strftime('%b %d')}",
            items=json.dumps(items)
        )
        db.add(grocery_list)
        db.commit()
        db.refresh(grocery_list)

        return {
            "id": grocery_list.id,
            "name": grocery_list.name,
            "items": items,
            "categories": grocery_data
        }

    except Exception as e:
        print(f"Grocery list generation error: {e}")
        return {"error": "Grocery list generation failed", "reason": str(e)}


def get_grocery_lists(user_id: int, db: Session, limit: int = 10) -> list[GroceryList]:
    """Get user's grocery lists."""
    return db.query(GroceryList).filter(
        GroceryList.user_id == user_id
    ).order_by(GroceryList.created_at.desc()).limit(limit).all()


def format_meal_plan_for_discord(plan_data: dict) -> str:
    """Format a meal plan for Discord display."""
    output = "**Weekly Meal Plan**\n\n"

    day_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    for day in day_order:
        if day in plan_data:
            day_data = plan_data[day]
            output += f"**{day.capitalize()}**\n"

            if day_data.get("breakfast"):
                output += f"- Breakfast: {day_data['breakfast']}\n"
            if day_data.get("lunch"):
                output += f"- Lunch: {day_data['lunch']}\n"
            if day_data.get("dinner"):
                output += f"- Dinner: {day_data['dinner']}\n"
            if day_data.get("snacks"):
                snacks = ", ".join(day_data["snacks"])
                output += f"- Snacks: {snacks}\n"

            output += "\n"

    return output


def format_grocery_list_for_discord(items: list[dict]) -> str:
    """Format a grocery list for Discord display."""
    output = "**Grocery List**\n\n"

    # Group by category
    categories = {}
    for item in items:
        cat = item.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    for category, cat_items in categories.items():
        output += f"**{category}**\n"
        for item in cat_items:
            checkbox = "[x]" if item.get("checked") else "[ ]"
            output += f"{checkbox} {item['name']}\n"
        output += "\n"

    return output
