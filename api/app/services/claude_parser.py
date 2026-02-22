import json
from datetime import datetime, date, timedelta
from anthropic import Anthropic
from ..config import get_settings

settings = get_settings()
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are a nutrition and fitness logging assistant. Parse user input about food, drinks, or activities into structured data.

For food/drink input, extract:
- description: Brief description of what was consumed
- calories: Estimated calories (integer)
- protein_g: Protein in grams
- carbs_g: Carbohydrates in grams
- fat_g: Fat in grams
- fiber_g: Fiber in grams (if applicable)
- water_oz: Water/liquid in ounces (if applicable)
- meal_type: One of: breakfast, lunch, dinner, snack
- time_reference: Extract any time reference like "yesterday", "last night", "this morning", "at 7pm", "7:30 last night" - return as string or null if not mentioned

For time references:
- "yesterday" → "yesterday"
- "last night" → "yesterday_night" (assume after 6pm yesterday)
- "this morning" → "today_morning"
- "at 7pm" → "today_19:00"
- "7:30 last night" or "at 7:30 yesterday" → "yesterday_19:30"
- If no time mentioned → null

For quantities:
- "a" or "an" = 1
- "couple" = 2
- Standard serving sizes when not specified

Respond ONLY with valid JSON, no markdown or explanation. Example:
{"description": "apple", "calories": 95, "protein_g": 0.5, "carbs_g": 25, "fat_g": 0.3, "fiber_g": 4.4, "water_oz": null, "meal_type": "snack", "time_reference": null}

Example with time:
{"description": "grilled chicken and vegetables", "calories": 450, "protein_g": 42, "carbs_g": 15, "fat_g": 18, "fiber_g": 5, "water_oz": null, "meal_type": "dinner", "time_reference": "yesterday_19:30"}

For water/drinks without calories:
{"description": "water", "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0, "water_oz": 24, "meal_type": null, "time_reference": null}

If you cannot parse the input or it's not food/fitness related, respond with:
{"error": "Could not parse input", "reason": "brief explanation"}"""


def parse_time_reference(time_ref: str) -> datetime:
    """Parse a time reference string into an actual datetime."""
    if not time_ref:
        return datetime.now()

    now = datetime.now()
    today = date.today()
    yesterday = today - timedelta(days=1)

    time_ref = time_ref.lower().strip()

    # Handle "yesterday" references
    if time_ref == "yesterday":
        # Default to noon yesterday
        return datetime.combine(yesterday, datetime.strptime("12:00", "%H:%M").time())

    if time_ref == "yesterday_night" or time_ref == "last_night":
        # Default to 8pm yesterday
        return datetime.combine(yesterday, datetime.strptime("20:00", "%H:%M").time())

    if time_ref == "today_morning" or time_ref == "this_morning":
        # Default to 8am today
        return datetime.combine(today, datetime.strptime("08:00", "%H:%M").time())

    # Handle "yesterday_HH:MM" format
    if time_ref.startswith("yesterday_"):
        time_part = time_ref.replace("yesterday_", "")
        try:
            parsed_time = datetime.strptime(time_part, "%H:%M").time()
            return datetime.combine(yesterday, parsed_time)
        except ValueError:
            pass

    # Handle "today_HH:MM" format
    if time_ref.startswith("today_"):
        time_part = time_ref.replace("today_", "")
        try:
            parsed_time = datetime.strptime(time_part, "%H:%M").time()
            return datetime.combine(today, parsed_time)
        except ValueError:
            pass

    # Try to parse as a time for today
    try:
        # Handle "HH:MM" format
        if ":" in time_ref:
            parsed_time = datetime.strptime(time_ref, "%H:%M").time()
            return datetime.combine(today, parsed_time)
    except ValueError:
        pass

    # Default to now
    return datetime.now()


def parse_nutrition_input(text: str) -> dict:
    """Parse natural language nutrition input using Claude"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": text}
        ]
    )

    response_text = message.content[0].text.strip()

    # Handle potential markdown code blocks
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response_text}
