"""
AI-powered recipe generation and management service.
"""
import json
from typing import Optional
from sqlalchemy.orm import Session
from anthropic import Anthropic

from ..config import get_settings
from ..models import User, Recipe
from ..schemas import RecipeResponse
from . import openai_service

settings = get_settings()
anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

RECIPE_SYSTEM_PROMPT = """You are a culinary AI assistant that generates healthy recipes based on user preferences and macro goals.

User's daily macro goals:
- Calories: {calorie_goal}
- Protein: {protein_goal}g
- Carbs: {carb_goal}g
- Fat: {fat_goal}g

Generate recipes that:
1. Help the user meet their protein goals
2. Are practical and use common ingredients
3. Include clear, numbered instructions
4. Have accurate macro estimates per serving

Respond with ONLY valid JSON in this format:
{{
  "name": "Recipe Name",
  "ingredients": ["ingredient 1 with amount", "ingredient 2 with amount", ...],
  "instructions": "Numbered step-by-step instructions",
  "servings": number,
  "prep_time_minutes": number,
  "cook_time_minutes": number,
  "calories_per_serving": number,
  "protein_g": number,
  "carbs_g": number,
  "fat_g": number,
  "tags": ["tag1", "tag2"],
  "tips": "optional cooking tips"
}}"""


def generate_recipe(
    query: str,
    user: User,
    dietary_prefs: list[str] = None,
    db: Session = None
) -> dict:
    """
    Generate a recipe based on user query and macro goals.

    Args:
        query: User's recipe request (e.g., "high protein chicken dinner")
        user: User object with macro goals
        dietary_prefs: Optional dietary restrictions/preferences
        db: Database session (to save the recipe)

    Returns:
        Recipe dict with ingredients, instructions, and macros
    """
    system_prompt = RECIPE_SYSTEM_PROMPT.format(
        calorie_goal=user.daily_calorie_goal,
        protein_goal=user.daily_protein_goal,
        carb_goal=user.daily_carb_goal,
        fat_goal=user.daily_fat_goal
    )

    user_prompt = f"Generate a recipe for: {query}"
    if dietary_prefs:
        user_prompt += f"\n\nDietary preferences/restrictions: {', '.join(dietary_prefs)}"

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        result_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        recipe_data = json.loads(result_text)
        recipe_data["source"] = "ai"

        # Save to database if session provided
        if db and user:
            save_recipe(recipe_data, user.id, db)

        return recipe_data

    except json.JSONDecodeError as e:
        return {"error": "Failed to parse recipe", "reason": str(e)}
    except Exception as e:
        print(f"Recipe generation error: {e}")

        # Fallback to OpenAI
        result = openai_service.parse_json_response(
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        if result and "name" in result:
            result["source"] = "ai"
            if db and user:
                save_recipe(result, user.id, db)
            return result

        return {"error": "Recipe generation failed", "reason": str(e)}


def save_recipe(recipe_data: dict, user_id: int, db: Session) -> Recipe:
    """Save a recipe to the database."""
    recipe = Recipe(
        user_id=user_id,
        name=recipe_data.get("name", "Untitled Recipe"),
        ingredients=json.dumps(recipe_data.get("ingredients", [])),
        instructions=recipe_data.get("instructions", ""),
        servings=recipe_data.get("servings", 1),
        calories_per_serving=recipe_data.get("calories_per_serving"),
        protein_g=recipe_data.get("protein_g"),
        carbs_g=recipe_data.get("carbs_g"),
        fat_g=recipe_data.get("fat_g"),
        source=recipe_data.get("source", "ai")
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def search_recipes(
    query: str,
    user_id: int,
    db: Session,
    limit: int = 10
) -> list[Recipe]:
    """Search user's saved recipes."""
    # Simple text search on name
    recipes = db.query(Recipe).filter(
        Recipe.user_id == user_id,
        Recipe.name.ilike(f"%{query}%")
    ).limit(limit).all()

    return recipes


def get_user_recipes(user_id: int, db: Session, limit: int = 20) -> list[Recipe]:
    """Get all recipes for a user."""
    return db.query(Recipe).filter(
        Recipe.user_id == user_id
    ).order_by(Recipe.created_at.desc()).limit(limit).all()


def format_recipe_for_discord(recipe_data: dict) -> str:
    """Format a recipe for Discord display."""
    output = f"**{recipe_data.get('name', 'Recipe')}**\n\n"

    # Macros per serving
    macros = []
    if recipe_data.get("calories_per_serving"):
        macros.append(f"{recipe_data['calories_per_serving']} cal")
    if recipe_data.get("protein_g"):
        macros.append(f"{recipe_data['protein_g']}g protein")
    if recipe_data.get("carbs_g"):
        macros.append(f"{recipe_data['carbs_g']}g carbs")
    if recipe_data.get("fat_g"):
        macros.append(f"{recipe_data['fat_g']}g fat")

    if macros:
        servings = recipe_data.get("servings", 1)
        output += f"*Per serving ({servings} servings): {', '.join(macros)}*\n\n"

    # Ingredients
    ingredients = recipe_data.get("ingredients", [])
    if ingredients:
        output += "**Ingredients:**\n"
        for ing in ingredients:
            output += f"- {ing}\n"
        output += "\n"

    # Instructions
    instructions = recipe_data.get("instructions", "")
    if instructions:
        output += f"**Instructions:**\n{instructions}\n"

    # Tips
    tips = recipe_data.get("tips")
    if tips:
        output += f"\n*Tip: {tips}*"

    return output


def recipe_to_response(recipe: Recipe) -> dict:
    """Convert Recipe model to response dict."""
    return {
        "id": recipe.id,
        "name": recipe.name,
        "ingredients": json.loads(recipe.ingredients) if recipe.ingredients else [],
        "instructions": recipe.instructions,
        "servings": recipe.servings,
        "calories_per_serving": recipe.calories_per_serving,
        "protein_g": float(recipe.protein_g) if recipe.protein_g else None,
        "carbs_g": float(recipe.carbs_g) if recipe.carbs_g else None,
        "fat_g": float(recipe.fat_g) if recipe.fat_g else None,
        "source": recipe.source,
        "created_at": recipe.created_at.isoformat()
    }
