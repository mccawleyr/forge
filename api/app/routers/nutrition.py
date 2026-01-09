from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..database import get_db

# Timezone configuration - all date calculations use Eastern time
EASTERN = ZoneInfo("America/New_York")


def get_eastern_today() -> date:
    """Get today's date in Eastern time"""
    return datetime.now(EASTERN).date()


def get_eastern_day_boundaries(day: date) -> tuple[datetime, datetime]:
    """Get UTC datetime boundaries for a day in Eastern time"""
    day_start_eastern = datetime.combine(day, datetime.min.time()).replace(tzinfo=EASTERN)
    day_end_eastern = datetime.combine(day, datetime.max.time()).replace(tzinfo=EASTERN)
    day_start_utc = day_start_eastern.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    day_end_utc = day_end_eastern.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return day_start_utc, day_end_utc


from ..models import NutritionLog, User
from ..schemas import NutritionCreate, NutritionResponse, ParseRequest, ParseResponse, ParsedNutrition
from ..services.claude_parser import parse_nutrition_input
from ..services.usda import search_food, get_food_details, extract_nutrients

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


def get_or_create_user(db: Session, discord_id: str) -> User:
    """Get existing user or create a new one"""
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if not user:
        user = User(discord_id=discord_id, display_name=f"User_{discord_id[:8]}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/parse", response_model=ParseResponse)
def parse_and_log(request: ParseRequest, db: Session = Depends(get_db)):
    """Parse natural language input and log nutrition data"""
    user = get_or_create_user(db, request.discord_id)

    # Parse with Claude
    parsed = parse_nutrition_input(request.text)

    if "error" in parsed:
        return ParseResponse(
            success=False,
            message=parsed.get("reason", parsed.get("error", "Unknown error"))
        )

    # Create nutrition log
    log = NutritionLog(
        user_id=user.id,
        raw_input=request.text,
        description=parsed.get("description"),
        calories=parsed.get("calories"),
        protein_g=parsed.get("protein_g"),
        carbs_g=parsed.get("carbs_g"),
        fat_g=parsed.get("fat_g"),
        fiber_g=parsed.get("fiber_g"),
        water_oz=parsed.get("water_oz"),
        meal_type=parsed.get("meal_type"),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return ParseResponse(
        success=True,
        message=f"Logged: {log.description}",
        parsed=ParsedNutrition(**parsed),
        log_id=log.id
    )


@router.post("/", response_model=NutritionResponse)
def create_nutrition_log(
    data: NutritionCreate,
    discord_id: str,
    db: Session = Depends(get_db)
):
    """Manual nutrition entry"""
    user = get_or_create_user(db, discord_id)

    log = NutritionLog(
        user_id=user.id,
        **data.model_dump()
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/today", response_model=list[NutritionResponse])
def get_today_nutrition(discord_id: str, db: Session = Depends(get_db)):
    """Get all nutrition logs for today (Eastern time)"""
    user = get_or_create_user(db, discord_id)
    today = get_eastern_today()
    day_start, day_end = get_eastern_day_boundaries(today)

    logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= day_start,
        NutritionLog.logged_at < day_end
    ).all()

    return logs


@router.get("/history", response_model=list[NutritionResponse])
def get_nutrition_history(discord_id: str, days: int = 7, db: Session = Depends(get_db)):
    """Get nutrition logs for the past N days (Eastern time)"""
    user = get_or_create_user(db, discord_id)
    # Get Eastern time start boundary for N days ago
    start_day = get_eastern_today() - timedelta(days=days-1)
    start_date, _ = get_eastern_day_boundaries(start_day)

    logs = db.query(NutritionLog).filter(
        NutritionLog.user_id == user.id,
        NutritionLog.logged_at >= start_date
    ).order_by(NutritionLog.logged_at.desc()).all()

    return logs


@router.delete("/{log_id}")
def delete_nutrition_log(log_id: int, discord_id: str, db: Session = Depends(get_db)):
    """Delete a nutrition log (undo)"""
    user = get_or_create_user(db, discord_id)

    log = db.query(NutritionLog).filter(
        NutritionLog.id == log_id,
        NutritionLog.user_id == user.id
    ).first()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    db.delete(log)
    db.commit()
    return {"message": "Deleted", "id": log_id}


@router.get("/usda/search")
async def usda_search(query: str, limit: int = 5):
    """Search USDA FoodData Central for foods"""
    if not query or len(query) < 2:
        return {"results": []}

    foods = await search_food(query, limit)

    results = []
    for food in foods:
        # Extract nutrients from search results (they include basic info)
        nutrients = {}
        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrientName", "").lower()
            value = nutrient.get("value", 0)
            if "energy" in name and "kcal" in nutrient.get("unitName", "").lower():
                nutrients["calories"] = round(value)
            elif name == "protein":
                nutrients["protein_g"] = round(value, 1)
            elif "carbohydrate" in name:
                nutrients["carbs_g"] = round(value, 1)
            elif "total lipid" in name or name == "fat":
                nutrients["fat_g"] = round(value, 1)
            elif "fiber" in name:
                nutrients["fiber_g"] = round(value, 1)

        results.append({
            "fdc_id": food.get("fdcId"),
            "description": food.get("description", ""),
            "brand": food.get("brandOwner", ""),
            "serving_size": food.get("servingSize"),
            "serving_unit": food.get("servingSizeUnit", "g"),
            **nutrients
        })

    return {"results": results}


@router.get("/usda/food/{fdc_id}")
async def usda_food_details(fdc_id: int):
    """Get detailed nutrition info for a specific USDA food"""
    food = await get_food_details(fdc_id)

    if not food:
        raise HTTPException(status_code=404, detail="Food not found")

    nutrients = extract_nutrients(food)

    return {
        "fdc_id": fdc_id,
        "description": food.get("description", ""),
        "serving_size": food.get("servingSize", 100),
        "serving_unit": food.get("servingSizeUnit", "g"),
        **nutrients
    }
