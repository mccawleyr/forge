"""
Conversation manager service for intent classification, context management, and AI routing.
"""
import json
from datetime import datetime, timedelta, date
from typing import Optional
from sqlalchemy.orm import Session
from anthropic import Anthropic

from ..config import get_settings
from ..models import User, Conversation, Message, NutritionLog
from ..schemas import ChatResponse, ParsedNutrition
from . import openai_service
from .claude_parser import parse_nutrition_input

settings = get_settings()
anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

# Intent classification system prompt
INTENT_SYSTEM_PROMPT = """You are an intent classifier for a health and fitness tracking assistant. Classify the user's message into one of these intents:

- log_meal: User wants to log food they ate (e.g., "I had eggs for breakfast", "just ate a salad")
- log_water: User is logging water intake (e.g., "32oz water", "drank 2 glasses of water")
- log_exercise: User is logging exercise (e.g., "walked 30 min", "did upper body workout")
- ask_recipe: User wants a recipe suggestion (e.g., "what should I make for dinner?", "give me a high protein recipe")
- meal_plan: User wants a meal plan (e.g., "plan my meals for the week", "what should I eat this week?")
- grocery_list: User wants a shopping list (e.g., "make me a grocery list", "what do I need to buy?")
- set_goal: User wants to update goals (e.g., "set my protein goal to 180g", "I want to eat 2000 calories")
- get_status: User wants to see their progress (e.g., "how am I doing today?", "show me my stats")
- verify_logs: User says something is wrong/incorrect with their logs (e.g., "that's not right", "this is incorrect", "that's wrong")
- delete_log: User wants to remove a log entry (e.g., "delete that", "remove the last entry")
- followup: User is continuing a previous topic (e.g., "tell me more", "what about the recipe?")
- conversation: General chat or questions (e.g., "what's a good high-protein snack?", "hello")
- unknown: Cannot determine intent

Respond with ONLY a JSON object:
{"intent": "intent_name", "confidence": 0.0-1.0, "entities": {"key": "value"}}

For log_meal, extract meal_type if mentioned (breakfast, lunch, dinner, snack).
For set_goal, extract goal_type and value if possible.
For ask_recipe, extract any cuisine, ingredients, or dietary preferences mentioned.
For verify_logs or delete_log, note if user mentions which log or time period."""


CONVERSATION_SYSTEM_PROMPT = """You are a friendly and supportive health and fitness assistant named Forge. You help users:
- Track their meals, water, and exercise
- Get recipe suggestions based on their macro goals
- Plan meals for the week
- Stay motivated on their fitness journey

User's current goals:
- Daily calories: {calorie_goal}
- Daily protein: {protein_goal}g
- Daily carbs: {carb_goal}g
- Daily fat: {fat_goal}g
- Daily water: {water_goal}oz

Today's progress:
- Calories: {calories_today} / {calorie_goal}
- Protein: {protein_today}g / {protein_goal}g
- Water: {water_today}oz / {water_goal}oz

Keep responses concise and actionable. Use a warm, encouraging tone. When suggesting recipes or meals, always consider their macro goals. Don't be overly enthusiastic or use excessive emojis."""


def get_or_create_user(db: Session, discord_id: str) -> User:
    """Get existing user or create a new one."""
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:6]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_conversation(db: Session, user_id: int) -> Conversation:
    """Get active conversation or create a new one. Sessions expire after 30 min of inactivity."""
    cutoff = datetime.utcnow() - timedelta(minutes=30)

    conversation = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.last_message_at > cutoff
    ).order_by(Conversation.last_message_at.desc()).first()

    if not conversation:
        conversation = Conversation(user_id=user_id, context=json.dumps({}))
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    return conversation


def save_message(
    db: Session,
    conversation_id: int,
    direction: str,
    content: str,
    intent: str = None
) -> Message:
    """Save a message to the conversation."""
    message = Message(
        conversation_id=conversation_id,
        direction=direction,
        content=content,
        ai_intent=intent
    )
    db.add(message)

    # Update conversation last_message_at
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conversation:
        conversation.last_message_at = datetime.utcnow()

    db.commit()
    db.refresh(message)
    return message


def build_context(conversation: Conversation, limit: int = 10) -> list[dict]:
    """Build conversation context from recent messages."""
    messages = sorted(conversation.messages, key=lambda m: m.created_at)[-limit:]

    context = []
    for msg in messages:
        role = "user" if msg.direction == "inbound" else "assistant"
        context.append({"role": role, "content": msg.content})

    return context


def get_daily_progress(db: Session, user_id: int) -> dict:
    """Get today's nutrition totals."""
    from datetime import date
    today = date.today()

    logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user_id,
        NutritionLog.logged_at >= datetime.combine(today, datetime.min.time())
    ).all()

    totals = {
        "calories": sum(log.calories or 0 for log in logs),
        "protein": sum(float(log.protein_g or 0) for log in logs),
        "carbs": sum(float(log.carbs_g or 0) for log in logs),
        "fat": sum(float(log.fat_g or 0) for log in logs),
        "water": sum(float(log.water_oz or 0) for log in logs),
    }

    return totals


def classify_intent(message: str, context: list[dict] = None) -> dict:
    """Classify user intent using Claude (with OpenAI fallback)."""
    try:
        # Build messages for context
        messages = []
        if context:
            # Include last few messages for context
            messages.extend(context[-4:])
        messages.append({"role": "user", "content": message})

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=INTENT_SYSTEM_PROMPT,
            messages=messages
        )

        result_text = response.content[0].text.strip()

        # Parse JSON response
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        return json.loads(result_text)

    except Exception as e:
        print(f"Claude intent classification error: {e}")

        # Fallback to OpenAI
        result = openai_service.parse_json_response(
            prompt=message,
            system_prompt=INTENT_SYSTEM_PROMPT
        )

        if result:
            return result

        # Final fallback: return unknown
        return {"intent": "unknown", "confidence": 0.0, "entities": {}}


def generate_response(
    intent: str,
    message: str,
    user: User,
    context: list[dict],
    db: Session
) -> str:
    """Generate an AI response based on intent and context."""
    from .recipe_service import get_user_recipes
    from ..models import Recipe

    progress = get_daily_progress(db, user.id)

    system_prompt = CONVERSATION_SYSTEM_PROMPT.format(
        calorie_goal=user.daily_calorie_goal,
        protein_goal=user.daily_protein_goal,
        carb_goal=user.daily_carb_goal,
        fat_goal=user.daily_fat_goal,
        water_goal=user.daily_water_goal,
        calories_today=progress["calories"],
        protein_today=round(progress["protein"], 1),
        water_today=round(progress["water"], 1)
    )

    # Add user's saved recipes to context with FULL details
    recipes = get_user_recipes(user.id, db, limit=5)
    if recipes:
        recipe_list = "\n\nUser's saved recipes (you have FULL access to these details):\n"
        for r in recipes:
            recipe_list += f"\n**{r.name}**\n"
            if r.servings:
                recipe_list += f"  Servings: {r.servings}\n"
            if r.calories_per_serving:
                recipe_list += f"  Calories per serving: {r.calories_per_serving}\n"
            if r.protein_g:
                recipe_list += f"  Protein: {float(r.protein_g)}g\n"
            if r.carbs_g:
                recipe_list += f"  Carbs: {float(r.carbs_g)}g\n"
            if r.fat_g:
                recipe_list += f"  Fat: {float(r.fat_g)}g\n"
            if r.ingredients:
                try:
                    ingredients = json.loads(r.ingredients)
                    recipe_list += f"  Ingredients: {', '.join(ingredients)}\n"
                except:
                    recipe_list += f"  Ingredients: {r.ingredients}\n"
            if r.instructions:
                # Truncate long instructions
                instructions = r.instructions[:500] + "..." if len(r.instructions) > 500 else r.instructions
                recipe_list += f"  Instructions: {instructions}\n"
        system_prompt += recipe_list

    # Add recent food logs to context
    today_logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= datetime.combine(date.today(), datetime.min.time())
    ).order_by(NutritionLog.logged_at.desc()).limit(5).all()

    if today_logs:
        log_list = "\n\nToday's food log:\n"
        for log in today_logs:
            log_list += f"- {log.description}"
            if log.calories:
                log_list += f" ({log.calories} cal)"
            log_list += "\n"
        system_prompt += log_list

    # Add intent context to the prompt
    intent_context = f"\n\nUser's detected intent: {intent}"
    if intent == "get_status":
        intent_context += "\nProvide a friendly summary of their daily progress."
    elif intent == "ask_recipe":
        intent_context += "\nSuggest a recipe that fits their macro goals."
    elif intent == "meal_plan":
        intent_context += "\nHelp them plan meals for the requested period."

    full_system = system_prompt + intent_context

    # Build messages
    messages = context[-6:] if context else []
    messages.append({"role": "user", "content": message})

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=full_system,
            messages=messages
        )
        return response.content[0].text

    except Exception as e:
        print(f"Claude response generation error: {e}")

        # Fallback to OpenAI
        openai_response = openai_service.chat_completion(
            messages=messages,
            system_prompt=full_system
        )

        if openai_response:
            return openai_response

        return "I'm having trouble responding right now. Please try again in a moment."


def process_message(
    message: str,
    user: User,
    conversation: Conversation,
    db: Session,
    image_base64: str = None
) -> ChatResponse:
    """
    Main entry point for processing a conversational message.
    Routes to appropriate handlers based on classified intent.
    """
    context = build_context(conversation)

    # Handle image-based food logging
    if image_base64:
        from .vision_parser import parse_food_image
        vision_result = parse_food_image(image_base64, message)

        if vision_result and "error" not in vision_result:
            # Log the nutrition
            nutrition_log = NutritionLog(
                user_id=user.id,
                raw_input=f"[Photo] {message}" if message else "[Photo]",
                description=vision_result.get("description", "Food from photo"),
                calories=vision_result.get("calories"),
                protein_g=vision_result.get("protein_g"),
                carbs_g=vision_result.get("carbs_g"),
                fat_g=vision_result.get("fat_g"),
                meal_type=vision_result.get("meal_type")
            )
            db.add(nutrition_log)
            db.commit()

            parsed = ParsedNutrition(
                description=vision_result.get("description", "Food from photo"),
                calories=vision_result.get("calories"),
                protein_g=vision_result.get("protein_g"),
                carbs_g=vision_result.get("carbs_g"),
                fat_g=vision_result.get("fat_g")
            )

            response_text = f"Logged from photo: **{parsed.description}** ({parsed.calories or '?'} cal, {parsed.protein_g or '?'}g protein)"

            return ChatResponse(
                response=response_text,
                intent="log_meal_photo",
                parsed_nutrition=parsed
            )

    # Classify intent
    intent_result = classify_intent(message, context)
    intent = intent_result.get("intent", "unknown")
    entities = intent_result.get("entities", {})

    # Route based on intent
    if intent == "log_meal":
        return handle_log_meal(message, user, db)

    elif intent == "log_water":
        return handle_log_water(message, user, db)

    elif intent == "log_exercise":
        return handle_log_exercise(message, user, db)

    elif intent == "get_status":
        return handle_get_status(user, db)

    elif intent == "set_goal":
        return handle_set_goal(message, entities, user, db)

    elif intent == "verify_logs":
        return handle_verify_logs(message, user, db)

    elif intent == "delete_log":
        return handle_delete_log(message, user, db)

    elif intent == "ask_recipe":
        return handle_ask_recipe(message, user, context, db)

    elif intent == "meal_plan":
        return handle_meal_plan(message, user, db)

    elif intent == "grocery_list":
        return handle_grocery_list(message, user, db)

    elif intent in ["conversation", "followup", "unknown"]:
        # Generate conversational response with database context
        response_text = generate_response(intent, message, user, context, db)

        suggestions = None
        if intent == "unknown":
            suggestions = [
                "Log a meal: 'I had eggs and toast for breakfast'",
                "Check progress: 'How am I doing today?'",
                "Get a recipe: 'What should I make for dinner?'"
            ]

        return ChatResponse(
            response=response_text,
            intent=intent,
            suggestions=suggestions
        )

    # Default fallback
    return ChatResponse(
        response="I'm not sure what you're asking. Try telling me what you ate, or ask 'how am I doing today?'",
        intent="unknown",
        suggestions=[
            "Log a meal: 'I had a chicken salad for lunch'",
            "Log water: '32oz water'",
            "Check status: 'Show me today's progress'"
        ]
    )


def handle_log_meal(message: str, user: User, db: Session) -> ChatResponse:
    """Handle meal logging intent with time context support."""
    from .claude_parser import parse_time_reference

    parsed = parse_nutrition_input(message)

    if "error" in parsed:
        return ChatResponse(
            response=f"I couldn't parse that food entry: {parsed.get('reason', 'Unknown error')}",
            intent="log_meal"
        )

    # Parse time reference if provided
    time_ref = parsed.get("time_reference")
    logged_at = parse_time_reference(time_ref) if time_ref else datetime.utcnow()

    # Create nutrition log
    nutrition_log = NutritionLog(
        user_id=user.id,
        raw_input=message,
        description=parsed.get("description", "Unknown food"),
        calories=parsed.get("calories"),
        protein_g=parsed.get("protein_g"),
        carbs_g=parsed.get("carbs_g"),
        fat_g=parsed.get("fat_g"),
        fiber_g=parsed.get("fiber_g"),
        water_oz=parsed.get("water_oz"),
        meal_type=parsed.get("meal_type"),
        logged_at=logged_at
    )
    db.add(nutrition_log)
    db.commit()

    # Remove time_reference from parsed before creating ParsedNutrition
    parsed_copy = {k: v for k, v in parsed.items() if k != "time_reference"}
    parsed_nutrition = ParsedNutrition(**parsed_copy)

    # Build response
    details = []
    if parsed.get("calories"):
        details.append(f"{parsed['calories']} cal")
    if parsed.get("protein_g"):
        details.append(f"{parsed['protein_g']}g protein")
    if parsed.get("water_oz"):
        details.append(f"{parsed['water_oz']}oz water")

    detail_str = f" ({', '.join(details)})" if details else ""

    # Add time context to response
    time_str = ""
    if time_ref:
        log_date = logged_at.date()
        today = date.today()
        if log_date == today:
            time_str = f" at {logged_at.strftime('%I:%M %p')}"
        elif log_date == today - timedelta(days=1):
            time_str = f" (yesterday at {logged_at.strftime('%I:%M %p')})"
        else:
            time_str = f" ({logged_at.strftime('%b %d at %I:%M %p')})"

    return ChatResponse(
        response=f"Logged: **{parsed.get('description', 'item')}**{detail_str}{time_str}",
        intent="log_meal",
        parsed_nutrition=parsed_nutrition
    )


def handle_log_water(message: str, user: User, db: Session) -> ChatResponse:
    """Handle water logging intent."""
    parsed = parse_nutrition_input(message)

    if "error" in parsed or not parsed.get("water_oz"):
        # Try to extract water amount directly
        import re
        water_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:oz|ounce|fl oz|glass)', message.lower())
        if water_match:
            water_oz = float(water_match.group(1))
            if "glass" in message.lower():
                water_oz *= 8  # Assume 8oz per glass
        else:
            return ChatResponse(
                response="I couldn't determine how much water. Try '32oz water' or '2 glasses of water'.",
                intent="log_water"
            )
    else:
        water_oz = parsed.get("water_oz")

    # Log the water
    nutrition_log = NutritionLog(
        user_id=user.id,
        raw_input=message,
        description=f"Water ({water_oz}oz)",
        calories=0,
        water_oz=water_oz
    )
    db.add(nutrition_log)
    db.commit()

    # Get daily total
    progress = get_daily_progress(db, user.id)

    return ChatResponse(
        response=f"Logged: **{water_oz}oz water**. Daily total: {progress['water']}oz / {user.daily_water_goal}oz",
        intent="log_water",
        parsed_nutrition=ParsedNutrition(description=f"Water", water_oz=water_oz, calories=0)
    )


def handle_log_exercise(message: str, user: User, db: Session) -> ChatResponse:
    """Handle exercise logging intent."""
    from ..models import Workout, WorkoutType
    from datetime import date

    # Use Claude to parse the exercise
    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system="""Parse this exercise description into JSON:
{"workout_type": "cardio|strength|flexibility|sports|walking|other", "duration_minutes": number, "calories_burned": number or null, "description": "brief description"}
Respond with ONLY valid JSON.""",
            messages=[{"role": "user", "content": message}]
        )

        result_text = response.content[0].text.strip()
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        parsed = json.loads(result_text)
    except Exception:
        parsed = {"workout_type": "other", "duration_minutes": 30, "description": message}

    # Create workout
    workout = Workout(
        user_id=user.id,
        date=date.today(),
        workout_type=WorkoutType(parsed.get("workout_type", "other")),
        duration_minutes=parsed.get("duration_minutes"),
        calories_burned=parsed.get("calories_burned"),
        description=parsed.get("description", message),
        raw_input=message
    )
    db.add(workout)
    db.commit()

    details = []
    if parsed.get("duration_minutes"):
        details.append(f"{parsed['duration_minutes']} min")
    if parsed.get("calories_burned"):
        details.append(f"~{parsed['calories_burned']} cal burned")

    detail_str = f" ({', '.join(details)})" if details else ""

    return ChatResponse(
        response=f"Logged workout: **{parsed.get('description', 'Exercise')}**{detail_str}",
        intent="log_exercise"
    )


def handle_get_status(user: User, db: Session) -> ChatResponse:
    """Handle status/progress request."""
    progress = get_daily_progress(db, user.id)

    cal_pct = round(progress["calories"] / user.daily_calorie_goal * 100) if user.daily_calorie_goal else 0
    protein_pct = round(progress["protein"] / user.daily_protein_goal * 100) if user.daily_protein_goal else 0
    water_pct = round(progress["water"] / user.daily_water_goal * 100) if user.daily_water_goal else 0

    status = f"""**Today's Progress**
- Calories: {progress['calories']} / {user.daily_calorie_goal} ({cal_pct}%)
- Protein: {round(progress['protein'], 1)}g / {user.daily_protein_goal}g ({protein_pct}%)
- Water: {round(progress['water'], 1)}oz / {user.daily_water_goal}oz ({water_pct}%)"""

    # Add encouragement based on progress
    if cal_pct >= 80 and cal_pct <= 110 and protein_pct >= 80:
        status += "\n\nGreat job staying on track today!"
    elif protein_pct < 50:
        status += f"\n\nTip: You're at {protein_pct}% of your protein goal. Consider a protein-rich snack!"
    elif water_pct < 50:
        status += "\n\nReminder: Don't forget to stay hydrated!"

    return ChatResponse(
        response=status,
        intent="get_status"
    )


def handle_set_goal(message: str, entities: dict, user: User, db: Session) -> ChatResponse:
    """Handle goal update requests."""
    import re

    updates = []

    # Try to extract goals from message
    calorie_match = re.search(r'(\d+)\s*(?:cal|calorie)', message.lower())
    protein_match = re.search(r'(\d+)\s*g?\s*protein', message.lower())
    water_match = re.search(r'(\d+)\s*(?:oz|ounce)\s*water', message.lower())

    if calorie_match:
        user.daily_calorie_goal = int(calorie_match.group(1))
        updates.append(f"Calories: {user.daily_calorie_goal}")

    if protein_match:
        user.daily_protein_goal = int(protein_match.group(1))
        updates.append(f"Protein: {user.daily_protein_goal}g")

    if water_match:
        user.daily_water_goal = int(water_match.group(1))
        updates.append(f"Water: {user.daily_water_goal}oz")

    if updates:
        db.commit()
        return ChatResponse(
            response=f"Updated goals:\n" + "\n".join(f"- {u}" for u in updates),
            intent="set_goal"
        )
    else:
        return ChatResponse(
            response="I couldn't understand the goal you want to set. Try 'set my protein goal to 180g' or 'I want to eat 2000 calories'.",
            intent="set_goal"
        )


def handle_ask_recipe(message: str, user: User, context: list[dict], db: Session) -> ChatResponse:
    """Handle recipe requests - generate new or find existing."""
    from .recipe_service import generate_recipe, search_recipes, get_user_recipes, format_recipe_for_discord, recipe_to_response

    # Check if user is asking about existing recipes
    lookup_keywords = ["my recipe", "saved recipe", "the recipe", "that recipe", "show me", "find", "what recipes"]
    is_lookup = any(kw in message.lower() for kw in lookup_keywords)

    if is_lookup:
        # Search for existing recipes
        recipes = get_user_recipes(user.id, db, limit=5)

        if not recipes:
            return ChatResponse(
                response="You don't have any saved recipes yet. Would you like me to create one for you? Just tell me what kind of recipe you're looking for!",
                intent="ask_recipe"
            )

        # Format recipe list
        recipe_list = "**Your Saved Recipes:**\n\n"
        for i, r in enumerate(recipes, 1):
            macros = []
            if r.calories_per_serving:
                macros.append(f"{r.calories_per_serving} cal")
            if r.protein_g:
                macros.append(f"{float(r.protein_g)}g protein")
            macro_str = f" ({', '.join(macros)})" if macros else ""
            recipe_list += f"{i}. **{r.name}**{macro_str}\n"

        recipe_list += "\nSay the recipe name to see full details, or ask me to create a new one!"

        return ChatResponse(
            response=recipe_list,
            intent="ask_recipe"
        )

    # Generate a new recipe and save it
    recipe_data = generate_recipe(message, user, db=db)

    if "error" in recipe_data:
        return ChatResponse(
            response=f"I couldn't generate a recipe: {recipe_data.get('reason', 'Unknown error')}. Try being more specific about what you want!",
            intent="ask_recipe"
        )

    # Format for Discord
    response_text = format_recipe_for_discord(recipe_data)
    response_text += "\n\n*This recipe has been saved to your collection!*"

    return ChatResponse(
        response=response_text,
        intent="ask_recipe",
        recipe=recipe_data
    )


def handle_meal_plan(message: str, user: User, db: Session) -> ChatResponse:
    """Handle meal plan requests."""
    from .meal_planner import generate_meal_plan, format_meal_plan_for_discord

    # Default to 7 days
    import re
    days_match = re.search(r'(\d+)\s*day', message.lower())
    days = int(days_match.group(1)) if days_match else 7
    days = min(days, 14)  # Cap at 14 days

    result = generate_meal_plan(user, db, days)

    if "error" in result:
        return ChatResponse(
            response=f"I couldn't generate a meal plan: {result.get('reason', 'Unknown error')}",
            intent="meal_plan"
        )

    response_text = format_meal_plan_for_discord(result)
    response_text += "\n\n*This meal plan has been saved! Use /grocerylist to generate a shopping list.*"

    return ChatResponse(
        response=response_text,
        intent="meal_plan",
        meal_plan=result
    )


def handle_grocery_list(message: str, user: User, db: Session) -> ChatResponse:
    """Handle grocery list requests."""
    from .meal_planner import get_current_meal_plan, generate_grocery_list, format_grocery_list_for_discord

    # Get current meal plan
    meal_plan = get_current_meal_plan(user.id, db)

    if not meal_plan:
        return ChatResponse(
            response="You don't have a meal plan for this week. Would you like me to create one? Just say 'plan my meals for the week'!",
            intent="grocery_list"
        )

    result = generate_grocery_list(meal_plan.id, user.id, db)

    if "error" in result:
        return ChatResponse(
            response=f"I couldn't generate a grocery list: {result.get('reason', 'Unknown error')}",
            intent="grocery_list"
        )

    response_text = format_grocery_list_for_discord(result)

    return ChatResponse(
        response=response_text,
        intent="grocery_list"
    )


def handle_verify_logs(message: str, user: User, db: Session) -> ChatResponse:
    """Handle when user says something is incorrect with their logs."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Get recent logs from today and yesterday
    recent_logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= datetime.combine(yesterday, datetime.min.time())
    ).order_by(NutritionLog.logged_at.desc()).limit(10).all()

    if not recent_logs:
        return ChatResponse(
            response="I don't see any recent log entries. What would you like to log?",
            intent="verify_logs"
        )

    # Format logs for review
    log_list = "**Recent Log Entries:**\n\n"
    for log in recent_logs:
        log_date = log.logged_at.date()
        if log_date == today:
            date_str = "Today"
        elif log_date == yesterday:
            date_str = "Yesterday"
        else:
            date_str = log_date.strftime("%b %d")

        time_str = log.logged_at.strftime("%I:%M %p")

        macros = []
        if log.calories:
            macros.append(f"{log.calories} cal")
        if log.protein_g:
            macros.append(f"{float(log.protein_g)}g protein")
        macro_str = f" ({', '.join(macros)})" if macros else ""

        log_list += f"• **{log.description}**{macro_str} - {date_str} at {time_str} [ID: {log.id}]\n"

    log_list += "\nTo delete an entry, say 'delete [ID number]' or 'delete the [description]'."
    log_list += "\nTo correct a time, say 'move entry [ID] to yesterday at 7pm'."

    return ChatResponse(
        response=log_list,
        intent="verify_logs"
    )


def handle_delete_log(message: str, user: User, db: Session) -> ChatResponse:
    """Handle log deletion requests."""
    import re

    # Try to find an ID in the message
    id_match = re.search(r'\b(\d+)\b', message)

    if id_match:
        log_id = int(id_match.group(1))

        # Find the log
        log = db.query(NutritionLog).filter(
            NutritionLog.id == log_id,
            NutritionLog.user_id == user.id
        ).first()

        if log:
            description = log.description
            db.delete(log)
            db.commit()

            return ChatResponse(
                response=f"Deleted: **{description}** (ID: {log_id})",
                intent="delete_log"
            )
        else:
            return ChatResponse(
                response=f"I couldn't find a log entry with ID {log_id}. Say 'show my logs' to see your recent entries.",
                intent="delete_log"
            )

    # Try to find by description - get recent logs
    recent_logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
    ).order_by(NutritionLog.logged_at.desc()).limit(5).all()

    # Try to match a description
    keywords = ["last", "recent", "latest", "the"]
    message_lower = message.lower()
    for kw in keywords:
        message_lower = message_lower.replace(kw, "").strip()

    for log in recent_logs:
        if log.description.lower() in message_lower or message_lower in log.description.lower():
            description = log.description
            log_id = log.id
            db.delete(log)
            db.commit()

            return ChatResponse(
                response=f"Deleted: **{description}** (ID: {log_id})",
                intent="delete_log"
            )

    # If we still can't find it, delete the most recent entry if they said "last"
    if "last" in message.lower() and recent_logs:
        log = recent_logs[0]
        description = log.description
        log_id = log.id
        db.delete(log)
        db.commit()

        return ChatResponse(
            response=f"Deleted your last entry: **{description}** (ID: {log_id})",
            intent="delete_log"
        )

    return ChatResponse(
        response="I couldn't determine which entry to delete. Say 'show my logs' to see your recent entries with IDs, then 'delete [ID number]'.",
        intent="delete_log"
    )
