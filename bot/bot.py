import os
import base64
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import httpx
from aiohttp import web
from datetime import date

API_URL = os.getenv("API_URL", "http://forge-api:8000")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOT_PORT = int(os.getenv("BOT_PORT", "8080"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# HTTP server for reminder notifications
notification_routes = web.RouteTableDef()


async def call_api(endpoint: str, method: str = "GET", data: dict = None, params: dict = None):
    """Helper to call the Forge API"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = f"{API_URL}/api{endpoint}"
        try:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=data, params=params)
            elif method == "PUT":
                response = await client.put(url, json=data, params=params)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code not in [200, 201]:
                return {"success": False, "message": f"API error: {response.status_code}"}

            if not response.content:
                return {"success": True, "message": "OK"}

            return response.json()
        except httpx.TimeoutException:
            return {"success": False, "message": "API timeout"}
        except Exception as e:
            return {"success": False, "message": str(e)}


async def call_conversation_api(message: str, discord_id: str, image_base64: str = None):
    """Call the conversation API endpoint"""
    data = {
        "discord_id": str(discord_id),
        "message": message
    }
    if image_base64:
        data["image_base64"] = image_base64

    return await call_api("/conversation/chat", method="POST", data=data)


@bot.event
async def on_ready():
    print(f"Forge Bot connected as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.event
async def on_message(message):
    """Handle messages - DMs are conversational, channel messages check for triggers or mentions"""
    if message.author.bot:
        return

    # Process commands first
    await bot.process_commands(message)

    content = message.content.strip()
    discord_id = str(message.author.id)

    # Check for image attachments (food photos)
    image_base64 = None
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            try:
                image_data = await attachment.read()
                image_base64 = base64.b64encode(image_data).decode()
                break  # Only process first image
            except Exception as e:
                print(f"Failed to read image attachment: {e}")

    # DMs are always conversational
    if isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            result = await call_conversation_api(content, discord_id, image_base64)

        if "response" in result:
            await message.reply(result["response"], mention_author=False)
        elif "message" in result:
            await message.reply(f"Error: {result['message']}", mention_author=False)
        else:
            await message.reply("Something went wrong. Please try again.", mention_author=False)
        return

    # Channel messages: check for mentions or triggers
    is_mentioned = bot.user.mentioned_in(message)
    content_lower = content.lower()

    # Natural language triggers
    triggers = [
        "i had", "i ate", "i drank", "just had", "just ate",
        "i've had", "i've eaten", "ive had", "ive eaten",
        "for breakfast", "for lunch", "for dinner", "for a snack",
        "logged", "log:"
    ]
    has_trigger = any(t in content_lower for t in triggers)

    # If mentioned or has trigger (or has food photo), process via conversation API
    if is_mentioned or has_trigger or image_base64:
        # Remove mention from message
        clean_content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

        async with message.channel.typing():
            result = await call_conversation_api(clean_content or "photo", discord_id, image_base64)

        if "response" in result:
            await message.add_reaction("\u2705")
            await message.reply(result["response"], mention_author=False)
        elif "message" in result:
            await message.add_reaction("\u274c")
            await message.reply(f"Error: {result['message']}", mention_author=False)


# === Slash Commands ===

@bot.tree.command(name="weight", description="Log your weight")
@app_commands.describe(weight="Your weight in pounds")
async def log_weight(interaction: discord.Interaction, weight: float):
    discord_id = str(interaction.user.id)

    result = await call_api(
        "/weight/",
        method="POST",
        data={"weight_lbs": weight},
        params={"discord_id": discord_id}
    )

    await interaction.response.send_message(
        f"Logged weight: **{weight} lbs**",
        ephemeral=True
    )


@bot.tree.command(name="today", description="Show today's summary")
async def show_today(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)

    result = await call_api("/dashboard/today", params={"discord_id": discord_id})

    embed = discord.Embed(
        title=f"Today's Summary - {date.today().strftime('%b %d')}",
        color=discord.Color.green()
    )

    def progress_bar(pct: float, width: int = 10) -> str:
        filled = int(min(pct, 100) / 100 * width)
        empty = width - filled
        bar = "\u2588" * filled + "\u2591" * empty
        return f"{bar} {pct:.0f}%"

    embed.add_field(
        name="Calories",
        value=f"{result['calories']} / {result['calorie_goal']}\n{progress_bar(result['calorie_pct'])}",
        inline=True
    )
    embed.add_field(
        name="Protein",
        value=f"{result['protein_g']:.0f}g / {result['protein_goal']}g\n{progress_bar(result['protein_pct'])}",
        inline=True
    )
    embed.add_field(
        name="Water",
        value=f"{result['water_oz']:.0f}oz / {result['water_goal']}oz\n{progress_bar(result['water_pct'])}",
        inline=True
    )

    if result.get("weight"):
        embed.add_field(name="Weight", value=f"{result['weight']} lbs", inline=True)

    if result.get("workout_minutes"):
        embed.add_field(name="Workout", value=f"{result['workout_minutes']} min", inline=True)

    if result.get("mood"):
        embed.add_field(name="Mood", value=result["mood"].title(), inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="week", description="Show this week's progress")
async def show_week(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)

    result = await call_api("/dashboard/week", params={"discord_id": discord_id})

    embed = discord.Embed(
        title="This Week's Progress",
        color=discord.Color.blue()
    )

    for day in result[:7]:
        day_date = day["date"]
        cal_emoji = "\u2705" if day["calorie_pct"] <= 100 else "\u26a0\ufe0f"
        summary = f"{cal_emoji} {day['calories']} cal | {day['protein_g']:.0f}g protein | {day['water_oz']:.0f}oz water"
        embed.add_field(name=day_date, value=summary, inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="undo", description="Delete your last log entry")
async def undo_last(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)

    logs = await call_api("/nutrition/today", params={"discord_id": discord_id})

    if not logs:
        await interaction.response.send_message("No logs to undo today.", ephemeral=True)
        return

    last_log = logs[-1]
    await call_api(f"/nutrition/{last_log['id']}", method="DELETE", params={"discord_id": discord_id})

    await interaction.response.send_message(
        f"Deleted: **{last_log['description']}** ({last_log.get('calories', 0)} cal)",
        ephemeral=True
    )


@bot.tree.command(name="goals", description="View or set your daily goals")
@app_commands.describe(
    calories="Daily calorie goal",
    protein="Daily protein goal (grams)",
    water="Daily water goal (oz)"
)
async def manage_goals(
    interaction: discord.Interaction,
    calories: int = None,
    protein: int = None,
    water: int = None
):
    discord_id = str(interaction.user.id)

    if calories or protein or water:
        current = await call_api("/dashboard/goals", params={"discord_id": discord_id})

        updated = {
            "target_weight": current.get("target_weight", 180),
            "daily_calorie_goal": calories or current.get("daily_calorie_goal", 2000),
            "daily_protein_goal": protein or current.get("daily_protein_goal", 150),
            "daily_carb_goal": current.get("daily_carb_goal", 200),
            "daily_fat_goal": current.get("daily_fat_goal", 65),
            "daily_water_goal": water or current.get("daily_water_goal", 64),
        }

        await call_api("/dashboard/goals", method="PUT", data=updated, params={"discord_id": discord_id})

        await interaction.response.send_message(
            f"Goals updated:\n- Calories: {updated['daily_calorie_goal']}\n- Protein: {updated['daily_protein_goal']}g\n- Water: {updated['daily_water_goal']}oz",
            ephemeral=True
        )
    else:
        goals = await call_api("/dashboard/goals", params={"discord_id": discord_id})

        embed = discord.Embed(title="Your Goals", color=discord.Color.gold())
        embed.add_field(name="Target Weight", value=f"{goals['target_weight']} lbs", inline=True)
        embed.add_field(name="Daily Calories", value=str(goals["daily_calorie_goal"]), inline=True)
        embed.add_field(name="Daily Protein", value=f"{goals['daily_protein_goal']}g", inline=True)
        embed.add_field(name="Daily Water", value=f"{goals['daily_water_goal']}oz", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# === New Conversational Commands ===

@bot.tree.command(name="recipe", description="Get a recipe suggestion")
@app_commands.describe(
    query="What kind of recipe do you want? (e.g., 'high protein chicken dinner')",
    preferences="Optional: dietary preferences (e.g., 'keto, no dairy')"
)
async def recipe_command(interaction: discord.Interaction, query: str, preferences: str = None):
    """Generate or search for a recipe"""
    discord_id = str(interaction.user.id)

    await interaction.response.defer(thinking=True)

    params = {"discord_id": discord_id, "query": query}
    if preferences:
        params["preferences"] = preferences

    result = await call_api("/recipes/generate", method="POST", params=params)

    if "error" in result:
        await interaction.followup.send(f"Couldn't generate recipe: {result.get('reason', 'Unknown error')}")
        return

    # Format recipe for Discord
    embed = discord.Embed(
        title=result.get("name", "Recipe"),
        color=discord.Color.orange()
    )

    # Macros
    macros = []
    if result.get("calories_per_serving"):
        macros.append(f"{result['calories_per_serving']} cal")
    if result.get("protein_g"):
        macros.append(f"{result['protein_g']}g protein")
    if result.get("carbs_g"):
        macros.append(f"{result['carbs_g']}g carbs")
    if result.get("fat_g"):
        macros.append(f"{result['fat_g']}g fat")

    if macros:
        servings = result.get("servings", 1)
        embed.description = f"*Per serving ({servings} servings): {', '.join(macros)}*"

    # Ingredients
    ingredients = result.get("ingredients", [])
    if ingredients:
        ing_text = "\n".join(f"- {ing}" for ing in ingredients[:15])
        if len(ingredients) > 15:
            ing_text += f"\n... and {len(ingredients) - 15} more"
        embed.add_field(name="Ingredients", value=ing_text, inline=False)

    # Instructions (truncate if too long)
    instructions = result.get("instructions", "")
    if len(instructions) > 1000:
        instructions = instructions[:997] + "..."
    if instructions:
        embed.add_field(name="Instructions", value=instructions, inline=False)

    # Tips
    if result.get("tips"):
        embed.set_footer(text=f"Tip: {result['tips']}")

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="mealplan", description="Generate a weekly meal plan")
@app_commands.describe(
    days="Number of days to plan (default: 7)",
    preferences="Optional: dietary preferences"
)
async def mealplan_command(interaction: discord.Interaction, days: int = 7, preferences: str = None):
    """Generate meal plan based on your goals"""
    discord_id = str(interaction.user.id)

    await interaction.response.defer(thinking=True)

    params = {"discord_id": discord_id, "days": min(days, 14)}
    if preferences:
        params["preferences"] = preferences

    result = await call_api("/meal-plans/generate", method="POST", params=params)

    if "error" in result:
        await interaction.followup.send(f"Couldn't generate meal plan: {result.get('reason', 'Unknown error')}")
        return

    plan_data = result.get("plan_data", {})

    embed = discord.Embed(
        title=f"Meal Plan (Week of {result.get('week_start', 'Today')})",
        color=discord.Color.purple()
    )

    day_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    for day in day_order[:days]:
        if day in plan_data:
            day_data = plan_data[day]
            meals = []
            if day_data.get("breakfast"):
                meals.append(f"**B:** {day_data['breakfast'][:60]}")
            if day_data.get("lunch"):
                meals.append(f"**L:** {day_data['lunch'][:60]}")
            if day_data.get("dinner"):
                meals.append(f"**D:** {day_data['dinner'][:60]}")

            embed.add_field(
                name=day.capitalize(),
                value="\n".join(meals) if meals else "Not planned",
                inline=False
            )

    embed.set_footer(text="Use /grocerylist to generate a shopping list from this plan")

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="grocerylist", description="Generate a grocery list from your meal plan")
async def grocerylist_command(interaction: discord.Interaction):
    """Generate grocery list from current meal plan"""
    discord_id = str(interaction.user.id)

    await interaction.response.defer(thinking=True)

    # Get current meal plan
    meal_plan = await call_api("/meal-plans/current", params={"discord_id": discord_id})

    if "error" in meal_plan or not meal_plan.get("id"):
        await interaction.followup.send(
            "No meal plan found for this week. Use `/mealplan` to create one first!"
        )
        return

    # Generate grocery list
    result = await call_api(
        "/grocery-lists/from-plan",
        method="POST",
        params={"discord_id": discord_id, "meal_plan_id": meal_plan["id"]}
    )

    if "error" in result:
        await interaction.followup.send(f"Couldn't generate grocery list: {result.get('reason', 'Unknown error')}")
        return

    embed = discord.Embed(
        title=result.get("name", "Grocery List"),
        color=discord.Color.green()
    )

    # Group by category
    categories = result.get("categories", {})
    for category, items in categories.items():
        if items:
            items_text = "\n".join(f"- {item}" for item in items[:10])
            if len(items) > 10:
                items_text += f"\n... and {len(items) - 10} more"
            embed.add_field(name=category, value=items_text, inline=True)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="reminders", description="Manage your reminders")
@app_commands.describe(action="list, enable, or disable")
async def reminders_command(interaction: discord.Interaction, action: str = "list"):
    """List, enable, or disable reminders"""
    discord_id = str(interaction.user.id)

    reminders = await call_api("/reminders", params={"discord_id": discord_id})

    if action.lower() == "list":
        embed = discord.Embed(
            title="Your Reminders",
            description="Use `/reminders enable` or `/reminders disable` to toggle",
            color=discord.Color.blue()
        )

        for r in reminders:
            status = "\u2705 Enabled" if r["enabled"] else "\u274c Disabled"
            embed.add_field(
                name=f"{r['reminder_type'].title()} ({status})",
                value=f"Schedule: `{r['schedule']}`\nMessage: {r['message_template'][:50]}...",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action.lower() == "enable":
        # Enable all reminders
        for r in reminders:
            if not r["enabled"]:
                await call_api(
                    f"/reminders/{r['id']}/toggle",
                    method="PUT",
                    params={"discord_id": discord_id, "enabled": "true"}
                )

        await interaction.response.send_message("All reminders enabled!", ephemeral=True)

    elif action.lower() == "disable":
        # Disable all reminders
        for r in reminders:
            if r["enabled"]:
                await call_api(
                    f"/reminders/{r['id']}/toggle",
                    method="PUT",
                    params={"discord_id": discord_id, "enabled": "false"}
                )

        await interaction.response.send_message("All reminders disabled!", ephemeral=True)

    else:
        await interaction.response.send_message(
            "Unknown action. Use: list, enable, or disable",
            ephemeral=True
        )


# === HTTP Server for Reminder Notifications ===

@notification_routes.post("/notify")
async def handle_notification(request):
    """Receive reminder notifications from the API"""
    try:
        data = await request.json()
        discord_id = data.get("discord_id")
        message = data.get("message")

        if not discord_id or not message:
            return web.json_response({"error": "Missing discord_id or message"}, status=400)

        # Send DM to user
        try:
            user = await bot.fetch_user(int(discord_id))
            await user.send(message)
            return web.json_response({"status": "sent"})
        except discord.NotFound:
            return web.json_response({"error": "User not found"}, status=404)
        except discord.Forbidden:
            return web.json_response({"error": "Cannot DM user"}, status=403)

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@notification_routes.get("/health")
async def health_check(request):
    """Health check endpoint"""
    return web.json_response({"status": "healthy", "bot_ready": bot.is_ready()})


async def start_http_server():
    """Start the HTTP server for notifications"""
    app = web.Application()
    app.add_routes(notification_routes)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", BOT_PORT)
    await site.start()

    print(f"Notification server running on port {BOT_PORT}")


async def main():
    """Main entry point"""
    # Start HTTP server
    await start_http_server()

    # Start Discord bot
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not set")
        exit(1)

    asyncio.run(main())
