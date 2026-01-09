import httpx
from typing import Optional
from ..config import get_settings

settings = get_settings()

USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"


async def search_food(query: str, limit: int = 5) -> list[dict]:
    """Search USDA FoodData Central for foods"""
    if not settings.usda_api_key:
        return []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{USDA_BASE_URL}/foods/search",
            params={
                "api_key": settings.usda_api_key,
                "query": query,
                "pageSize": limit,
                "dataType": ["Survey (FNDDS)", "Foundation", "SR Legacy"]
            }
        )
        if response.status_code != 200:
            return []

        data = response.json()
        return data.get("foods", [])


async def get_food_details(fdc_id: int) -> Optional[dict]:
    """Get detailed nutrition info for a specific food"""
    if not settings.usda_api_key:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{USDA_BASE_URL}/food/{fdc_id}",
            params={"api_key": settings.usda_api_key}
        )
        if response.status_code != 200:
            return None

        return response.json()


def extract_nutrients(food_data: dict) -> dict:
    """Extract key nutrients from USDA food data"""
    nutrients = {}
    nutrient_map = {
        1008: "calories",      # Energy (kcal)
        1003: "protein_g",     # Protein
        1005: "carbs_g",       # Carbohydrate
        1004: "fat_g",         # Total lipid (fat)
        1079: "fiber_g",       # Fiber
    }

    for nutrient in food_data.get("foodNutrients", []):
        nutrient_id = nutrient.get("nutrient", {}).get("id")
        if nutrient_id in nutrient_map:
            nutrients[nutrient_map[nutrient_id]] = nutrient.get("amount", 0)

    return nutrients
