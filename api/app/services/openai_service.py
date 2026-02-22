"""
OpenAI GPT-4 fallback service for when Claude API is unavailable.
"""
from openai import OpenAI
from ..config import get_settings

settings = get_settings()


def get_openai_client() -> OpenAI | None:
    """Get OpenAI client if API key is configured."""
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def chat_completion(
    messages: list[dict],
    system_prompt: str,
    model: str = "gpt-4-turbo-preview",
    max_tokens: int = 1000
) -> str | None:
    """
    Generate a chat completion using OpenAI GPT-4.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        system_prompt: System instruction for the model
        model: OpenAI model to use
        max_tokens: Maximum tokens in response

    Returns:
        Response text or None if failed
    """
    client = get_openai_client()
    if not client:
        return None

    try:
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        response = client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=0.7
        )

        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None


def parse_json_response(
    prompt: str,
    system_prompt: str,
    model: str = "gpt-4-turbo-preview"
) -> dict | None:
    """
    Get a JSON response from GPT-4.

    Args:
        prompt: User prompt
        system_prompt: System instructions (should specify JSON output)
        model: OpenAI model to use

    Returns:
        Parsed JSON dict or None if failed
    """
    import json

    client = get_openai_client()
    if not client:
        return None

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI JSON parse error: {e}")
        return None
