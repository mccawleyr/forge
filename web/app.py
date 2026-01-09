import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from collections import defaultdict
import httpx
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

API_URL = os.getenv("API_URL", "http://forge-api:8000")
# Default discord ID for single-user mode (set via env or hardcode yours)
DEFAULT_DISCORD_ID = os.getenv("DEFAULT_DISCORD_ID", "default_user")

# Timezone configuration
EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def convert_utc_to_eastern(iso_string: str) -> str:
    """Convert UTC ISO datetime string to Eastern time ISO string"""
    if not iso_string:
        return iso_string
    try:
        # Parse the UTC datetime
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        # Convert to Eastern
        eastern_dt = dt.astimezone(EASTERN)
        return eastern_dt.isoformat()
    except (ValueError, TypeError):
        return iso_string


def api_get(endpoint: str, params: dict = None):
    """Helper to call the Forge API"""
    params = params or {}
    params["discord_id"] = DEFAULT_DISCORD_ID
    with httpx.Client() as client:
        response = client.get(f"{API_URL}/api{endpoint}", params=params)
        return response.json()


def api_post(endpoint: str, data: dict, params: dict = None):
    """Helper for POST requests"""
    params = params or {}
    params["discord_id"] = DEFAULT_DISCORD_ID
    with httpx.Client() as client:
        response = client.post(f"{API_URL}/api{endpoint}", json=data, params=params)
        return response.json()


@app.route("/")
def dashboard():
    """Main dashboard view"""
    today = api_get("/dashboard/today")
    week = api_get("/dashboard/week")
    goals = api_get("/dashboard/goals")
    weight_history = api_get("/weight/history", {"days": 30})

    return render_template(
        "dashboard.html",
        today=today,
        week=week,
        goals=goals,
        weight_history=weight_history
    )


@app.route("/log", methods=["GET", "POST"])
def manual_log():
    """Log history view - forms are now on dashboard"""
    if request.method == "POST":
        form_type = request.form.get("type")

        if form_type == "nutrition":
            data = {
                "description": request.form.get("description"),
                "calories": int(request.form.get("calories") or 0),
                "protein_g": float(request.form.get("protein") or 0),
                "carbs_g": float(request.form.get("carbs") or 0),
                "fat_g": float(request.form.get("fat") or 0),
                "fiber_g": float(request.form.get("fiber") or 0),
                "meal_type": request.form.get("meal_type"),
            }
            api_post("/nutrition/", data)

        elif form_type == "water":
            data = {
                "description": "Water",
                "water_oz": float(request.form.get("water_oz") or 0),
            }
            api_post("/nutrition/", data)

        elif form_type == "weight":
            data = {"weight_lbs": float(request.form.get("weight"))}
            api_post("/weight/", data)

        elif form_type == "workout":
            data = {
                "workout_type": request.form.get("workout_type", "other"),
                "duration_minutes": int(request.form.get("duration") or 0),
                "calories_burned": int(request.form.get("calories_burned") or 0),
                "description": request.form.get("workout_description"),
            }
            api_post("/workouts/", data)

        return redirect(url_for("dashboard"))

    # Fetch history for log page
    days = request.args.get("days", 7, type=int)
    history = api_get(f"/nutrition/history?days={days}")
    fasting_history = api_get(f"/fasting/history?days={days}")

    # Convert UTC timestamps to Eastern time and group by date
    history_by_date = defaultdict(list)
    for log in history:
        # Convert logged_at from UTC to Eastern
        if log.get("logged_at"):
            log["logged_at"] = convert_utc_to_eastern(log["logged_at"])
        log_date = log.get("logged_at", "")[:10]
        history_by_date[log_date].append(log)

    # Convert fasting timestamps to Eastern time and group by date
    fasting_by_date = defaultdict(list)
    for fast in fasting_history:
        if fast.get("started_at"):
            fast["started_at"] = convert_utc_to_eastern(fast["started_at"])
        if fast.get("ended_at"):
            fast["ended_at"] = convert_utc_to_eastern(fast["ended_at"])
        fast_date = fast.get("started_at", "")[:10]
        fasting_by_date[fast_date].append(fast)

    return render_template(
        "log.html",
        history_by_date=dict(history_by_date),
        fasting_by_date=dict(fasting_by_date),
        days=days
    )


@app.route("/trends")
def trends():
    """Trends and charts view"""
    days = int(request.args.get("days", 30))
    weight_history = api_get("/weight/history", {"days": days})
    week = api_get("/dashboard/week")

    return render_template(
        "trends.html",
        weight_history=weight_history,
        week=week,
        days=days
    )


@app.route("/api/chart/weight")
def chart_weight_data():
    """JSON endpoint for weight chart"""
    days = int(request.args.get("days", 30))
    history = api_get("/weight/history", {"days": days})

    return jsonify({
        "labels": [entry["date"] for entry in history],
        "data": [float(entry["weight_lbs"]) for entry in history]
    })


@app.route("/api/chart/nutrition")
def chart_nutrition_data():
    """JSON endpoint for nutrition chart"""
    week = api_get("/dashboard/week")

    return jsonify({
        "labels": [day["date"] for day in reversed(week)],
        "calories": [day["calories"] for day in reversed(week)],
        "protein": [day["protein_g"] for day in reversed(week)],
        "water": [day["water_oz"] for day in reversed(week)]
    })


@app.route("/api/nutrition/<int:log_id>", methods=["DELETE"])
def delete_nutrition_log(log_id: int):
    """Delete a nutrition log entry"""
    with httpx.Client() as client:
        response = client.delete(
            f"{API_URL}/api/nutrition/{log_id}",
            params={"discord_id": DEFAULT_DISCORD_ID}
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({"error": "Failed to delete"}), response.status_code


@app.route("/api/fasting/<int:fast_id>", methods=["DELETE"])
def delete_fasting_log(fast_id: int):
    """Delete a fasting window entry"""
    with httpx.Client() as client:
        response = client.delete(
            f"{API_URL}/api/fasting/{fast_id}",
            params={"discord_id": DEFAULT_DISCORD_ID}
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({"error": "Failed to delete"}), response.status_code


@app.route("/api/fasting/start", methods=["POST"])
def start_fasting():
    """Start a new fasting window"""
    data = request.get_json()
    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/api/fasting/",
            json=data,
            params={"discord_id": DEFAULT_DISCORD_ID}
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({"error": "Failed to start fast"}), response.status_code


@app.route("/api/fasting/end", methods=["POST"])
def end_fasting():
    """End the active fasting window"""
    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/api/fasting/end",
            params={"discord_id": DEFAULT_DISCORD_ID}
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({"error": "Failed to end fast"}), response.status_code


@app.route("/api/fasting/active")
def get_active_fasting():
    """Get the currently active fasting window"""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/api/fasting/active",
            params={"discord_id": DEFAULT_DISCORD_ID}
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify(None)


@app.route("/api/nutrition/usda/search")
def usda_search():
    """Proxy USDA search requests to the API"""
    query = request.args.get("query", "")
    limit = request.args.get("limit", 5)

    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/api/nutrition/usda/search",
            params={"query": query, "limit": limit}
        )
        return jsonify(response.json())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
