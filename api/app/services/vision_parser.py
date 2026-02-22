"""
Food photo analysis using Claude Vision API.
"""
import json
from anthropic import Anthropic
from ..config import get_settings
from . import openai_service

settings = get_settings()
anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

VISION_SYSTEM_PROMPT = """You are a nutrition analysis assistant. Analyze the food in this image and estimate its nutritional content.

Return ONLY a valid JSON object with these fields:
{
  "description": "brief description of the food",
  "calories": estimated calories (integer),
  "protein_g": protein in grams (number),
  "carbs_g": carbohydrates in grams (number),
  "fat_g": fat in grams (number),
  "portion_size": "estimated portion size",
  "meal_type": "breakfast|lunch|dinner|snack" (if determinable, otherwise null),
  "confidence": "high|medium|low" (how confident you are in the estimate)
}

Important notes:
- Estimates should be for what's visible in the photo
- If multiple items, estimate totals
- Be conservative in estimates
- If you cannot identify the food clearly, return {"error": "Cannot identify food", "reason": "explanation"}"""


def parse_food_image(
    image_base64: str,
    hint: str = None,
    media_type: str = "image/jpeg"
) -> dict:
    """
    Use Claude Vision to analyze a food photo and estimate nutrition.

    Args:
        image_base64: Base64 encoded image data
        hint: Optional text hint from user (e.g., "lunch", "chicken salad")
        media_type: MIME type of the image

    Returns:
        Dict with nutrition info or error
    """
    user_content = []

    # Add the image
    user_content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": image_base64
        }
    })

    # Add text prompt
    prompt = "Identify this food and estimate its nutritional content per serving."
    if hint:
        prompt += f" The user mentioned: '{hint}'"
    prompt += " Return ONLY valid JSON."

    user_content.append({
        "type": "text",
        "text": prompt
    })

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=VISION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": user_content
            }]
        )

        result_text = response.content[0].text.strip()

        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        result = json.loads(result_text)

        # Add disclaimer about estimates
        if "error" not in result:
            result["is_estimate"] = True
            result["disclaimer"] = "AI vision estimates are approximate (typically within 20-30% of actual). Adjust if needed."

        return result

    except json.JSONDecodeError as e:
        return {"error": "Failed to parse vision response", "reason": str(e)}
    except Exception as e:
        print(f"Vision API error: {e}")

        # Fallback to OpenAI if available
        if settings.openai_api_key:
            return parse_food_image_openai(image_base64, hint, media_type)

        return {"error": "Vision analysis failed", "reason": str(e)}


def parse_food_image_openai(
    image_base64: str,
    hint: str = None,
    media_type: str = "image/jpeg"
) -> dict:
    """
    Fallback to OpenAI GPT-4 Vision for food analysis.
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    prompt = "Identify this food and estimate its nutritional content per serving."
    if hint:
        prompt += f" The user mentioned: '{hint}'"
    prompt += f"\n\n{VISION_SYSTEM_PROMPT}"

    try:
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )

        result_text = response.choices[0].message.content.strip()

        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        result = json.loads(result_text)
        result["is_estimate"] = True
        result["disclaimer"] = "AI vision estimates are approximate. Adjust if needed."

        return result

    except Exception as e:
        return {"error": "OpenAI vision analysis failed", "reason": str(e)}
