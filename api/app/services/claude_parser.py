import json
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

For quantities:
- "a" or "an" = 1
- "couple" = 2
- Standard serving sizes when not specified

Respond ONLY with valid JSON, no markdown or explanation. Example:
{"description": "apple", "calories": 95, "protein_g": 0.5, "carbs_g": 25, "fat_g": 0.3, "fiber_g": 4.4, "water_oz": null, "meal_type": "snack"}

For water/drinks without calories:
{"description": "water", "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0, "water_oz": 24, "meal_type": null}

If you cannot parse the input or it's not food/fitness related, respond with:
{"error": "Could not parse input", "reason": "brief explanation"}"""


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
