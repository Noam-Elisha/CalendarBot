# Discord Calendar Bot

A Discord bot that creates and manages Google Calendar events directly from Discord commands.

## Setup

### 1. Install Dependencies

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token
5. Enable "Message Content Intent" in the Bot settings
6. Go to OAuth2 > URL Generator:
   - Select scope: `bot`
   - Select permissions: `Send Messages`, `Use Slash Commands`, `Embed Links`
7. Use the generated URL to invite the bot to your server

### 3. Configure Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google Calendar API
4. Go to "Credentials" > "Create Credentials" > "OAuth client ID"
5. Select "Desktop app" as application type
6. Download the credentials JSON file and save it as `credentials.json` in the project root

### 4. Set Environment Variables

Edit the `.env` file and add your Discord bot token:

```
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

### 5. Run the Bot

```powershell
.venv\Scripts\python.exe bot.py
```

On first run, you'll be prompted to authorize the Google Calendar API access in your browser.

## Commands

- `!create_event` - Create a calendar event
  - Format: `!create_event Title | YYYY-MM-DD HH:MM | YYYY-MM-DD HH:MM | Description`
  - Example: `!create_event Team Meeting | 2025-12-25 10:00 | 2025-12-25 11:00 | Discuss project updates`

- `!list_events` - List upcoming calendar events
  - Usage: `!list_events [days]`
  - Example: `!list_events 7`

- `!help_calendar` - Show help for calendar commands

## Notes

- The bot uses OAuth2 for Google Calendar authentication
- Your credentials are stored locally in `token.pickle` (gitignored)
- Change the timezone in `bot.py` to match your location (currently set to America/New_York)
