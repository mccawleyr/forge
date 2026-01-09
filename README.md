# Forge - Fitness Tracking System

A fitness tracking system with Discord bot integration and web dashboard.

## Components

- **forge-api**: FastAPI backend with Claude-powered natural language parsing
- **forge-bot**: Discord bot for logging via chat
- **forge-web**: Flask web dashboard for viewing trends

## Setup

### 1. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application → Name it "Forge"
3. Go to Bot → Reset Token → Copy the token
4. Enable these Privileged Gateway Intents:
   - MESSAGE CONTENT INTENT
5. Go to OAuth2 → URL Generator:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Add Reactions`
6. Use the generated URL to invite the bot to your server

### 2. Get API Keys

- **Anthropic API Key**: https://console.anthropic.com/
- **USDA FoodData Central**: https://fdc.nal.usda.gov/api-key-signup.html (free)

### 3. Configure Environment

Edit `~/Homelab/.env` and fill in:

```bash
FORGE_DISCORD_TOKEN=your_discord_bot_token
FORGE_DEFAULT_DISCORD_ID=your_discord_user_id
ANTHROPIC_API_KEY=sk-ant-...
USDA_API_KEY=your_usda_key
```

To find your Discord User ID: Enable Developer Mode in Discord settings, right-click your name → Copy User ID.

### 4. Initialize Database

```bash
docker exec -it postgres psql -U admin -c "CREATE DATABASE forge;"
```

### 5. Build and Start

```bash
cd ~/Homelab
docker compose build forge-api forge-bot forge-web
docker compose up -d forge-api forge-bot forge-web
```

## Usage

### Discord Commands

**Natural Language (just type in your logging channel):**
- "I just had 24oz water and an apple"
- "just ate a chicken breast with rice"
- "logged 2 eggs and coffee"

**Slash Commands:**
- `/weight 272.5` - Log your weight
- `/today` - Show today's summary with progress bars
- `/week` - Show this week's overview
- `/undo` - Delete your last log entry
- `/goals` - View or set your daily goals
- `/goals calories:1800 protein:180 water:80` - Update goals

### Web Dashboard

Access at: https://forge.mccawley.me

- **Dashboard**: Today's progress with goals
- **Log**: Manual entry forms
- **Trends**: Weight and nutrition charts

## Architecture

```
Discord User
     │
     ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  forge-bot  │───▶│  forge-api  │───▶│  postgres   │
└─────────────┘    └──────┬──────┘    └─────────────┘
                         │
                    ┌────┴────┐
                    ▼         ▼
              ┌─────────┐ ┌──────┐
              │ Claude  │ │ USDA │
              │   API   │ │ API  │
              └─────────┘ └──────┘

Web Browser
     │
     ▼
┌─────────────┐
│  forge-web  │───▶ forge-api
└─────────────┘
```

## Troubleshooting

**Bot not responding:**
- Check logs: `docker logs forge-bot`
- Verify MESSAGE CONTENT INTENT is enabled
- Ensure bot has permissions in the channel

**API errors:**
- Check logs: `docker logs forge-api`
- Verify database connection: `docker exec forge-api python -c "from app.database import engine; print(engine.url)"`

**Dashboard not loading:**
- Check logs: `docker logs forge-web`
- Verify API_URL is correct
