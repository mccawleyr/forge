import os
import discord
from discord.ext import commands
from discord import app_commands
import httpx
from datetime import date

API_URL = os.getenv("API_URL", "http://forge-api:8000")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def call_api(endpoint: str, method: str = "GET", data: dict = None, params: dict = None):
    """Helper to call the Forge API"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{API_URL}/api{endpoint}"
        try:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=data, params=params)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code != 200:
                return {"success": False, "message": f"API error: {response.status_code}"}

            if not response.content:
                return {"success": False, "message": "Empty response from API"}

            return response.json()
        except httpx.TimeoutException:
            return {"success": False, "message": "API timeout"}
        except Exception as e:
            return {"success": False, "message": str(e)}


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
    """Handle natural language logging in designated channels"""
    if message.author.bot:
        return

    # Process commands first
    await bot.process_commands(message)

    # Check if this looks like a food logging message
    content = message.content.lower().strip()

    # Natural language triggers - check if any appear anywhere in the message
    triggers = [
        "i had", "i ate", "i drank", "just had", "just ate",
        "i've had", "i've eaten", "ive had", "ive eaten",
        "for breakfast", "for lunch", "for dinner", "for a snack",
        "logged", "log:"
    ]
    if any(t in content for t in triggers):
        discord_id = str(message.author.id)

        result = await call_api(
            "/nutrition/parse",
            method="POST",
            data={"text": message.content, "discord_id": discord_id}
        )

        if result.get("success"):
            parsed = result.get("parsed", {})
            response = f"Logged: **{parsed.get('description', 'item')}**"

            details = []
            if parsed.get("calories"):
                details.append(f"{parsed['calories']} cal")
            if parsed.get("protein_g"):
                details.append(f"{parsed['protein_g']}g protein")
            if parsed.get("water_oz"):
                details.append(f"{parsed['water_oz']}oz water")

            if details:
                response += f" ({', '.join(details)})"

            await message.add_reaction("\u2705")
            await message.reply(response, mention_author=False)
        else:
            await message.add_reaction("\u274c")
            await message.reply(
                f"Couldn't parse that: {result.get('message', 'Unknown error')}",
                mention_author=False
            )


# Slash Commands
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

    # Progress bars
    def progress_bar(pct: float, width: int = 10) -> str:
        filled = int(pct / 100 * width)
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

    # Get today's nutrition logs
    logs = await call_api("/nutrition/today", params={"discord_id": discord_id})

    if not logs:
        await interaction.response.send_message("No logs to undo today.", ephemeral=True)
        return

    # Delete the most recent one
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
        # Update goals
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
        # Show current goals
        goals = await call_api("/dashboard/goals", params={"discord_id": discord_id})

        embed = discord.Embed(title="Your Goals", color=discord.Color.gold())
        embed.add_field(name="Target Weight", value=f"{goals['target_weight']} lbs", inline=True)
        embed.add_field(name="Daily Calories", value=str(goals["daily_calorie_goal"]), inline=True)
        embed.add_field(name="Daily Protein", value=f"{goals['daily_protein_goal']}g", inline=True)
        embed.add_field(name="Daily Water", value=f"{goals['daily_water_goal']}oz", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not set")
        exit(1)
    bot.run(DISCORD_TOKEN)
