import os
import discord
from discord import app_commands
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import json
from datetime import datetime, timedelta
import re

# Load environment variables
load_dotenv()

# Discord bot setup
intents = discord.Intents.default()

class CalendarBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.user_data_file = 'user_data.json'
        self.user_emails = self.load_user_data()
    
    def load_user_data(self):
        """Load user email data from JSON file"""
        if os.path.exists(self.user_data_file):
            with open(self.user_data_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_user_data(self):
        """Save user email data to JSON file"""
        with open(self.user_data_file, 'w') as f:
            json.dump(self.user_emails, f, indent=2)

client = CalendarBot()

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Authenticate and return Google Calendar service"""
    creds = None
    
    # Token file stores user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    service = build('calendar', 'v3', credentials=creds)
    return service

@client.event
async def on_ready():
    """Event handler for when the bot is ready"""
    print(f'{client.user} has connected to Discord!')
    print(f'Bot is in {len(client.guilds)} guilds')


@client.tree.command(name="register", description="Register your email for calendar invites")
@app_commands.describe(email="Your email address for receiving calendar invites")
async def register(interaction: discord.Interaction, email: str):
    """Register user's email for calendar invites"""
    # Email validation using regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        await interaction.response.send_message(
            "❌ Please provide a valid email address.",
            ephemeral=True
        )
        return
    
    user_id = str(interaction.user.id)
    client.user_emails[user_id] = {
        'email': email,
        'username': interaction.user.name
    }
    client.save_user_data()
    
    embed = discord.Embed(
        title="✅ Registration Successful",
        description=f"Your email has been registered for calendar invites.",
        color=discord.Color.green()
    )
    embed.add_field(name="Email", value=email, inline=False)
    embed.add_field(
        name="Note",
        value="You will receive calendar invites at this email address.",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="create_event", description="Create a calendar event")
@app_commands.describe(
    name="Event name/title",
    date="Date in MM/DD/YYYY format (e.g., 12/25/2025)",
    time="Time in Pacific time (e.g., 2:30 PM or 14:30)",
    description="Optional event description"
)
async def create_event(
    interaction: discord.Interaction, 
    name: str, 
    date: str, 
    time: str,
    description: str = None
):
    """Create a calendar event"""
    try:
        # Parse the date and time
        datetime_str = f"{date} {time}"
        
        # Try multiple time formats
        event_dt = None
        for fmt in ["%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%m/%d/%Y %I%p", "%m/%d/%Y %H"]:
            try:
                event_dt = datetime.strptime(datetime_str, fmt)
                break
            except ValueError:
                continue
        
        if event_dt is None:
            await interaction.response.send_message(
                "❌ Invalid date/time format. Use MM/DD/YYYY for date and time like '2:30 PM' or '14:30'",
                ephemeral=True
            )
            return
        
        # Get Discord timestamp (Unix timestamp)
        unix_timestamp = int(event_dt.timestamp())
        
        embed = discord.Embed(
            title="Event Created",
            description=f"",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Event Name",
            value=name,
            inline=False
        )
        
        if description:
            embed.add_field(
                name="Description",
                value=description,
                inline=False
            )
        
        # Discord timestamp formats:
        # <t:timestamp:R> = relative time (e.g., "in 2 hours")
        # <t:timestamp:F> = full date/time (e.g., "Monday, December 25, 2025 2:30 PM")
        embed.add_field(
            name="Date/Time",
            value=f"<t:{unix_timestamp}:F>\n(<t:{unix_timestamp}:R>)",
            inline=False
        )
        
        # Create a button with success (green) style
        view = discord.ui.View()
        button = discord.ui.Button(
            label="Add to Calendar"
        )
        view.add_item(button)
        
        await interaction.response.send_message(embed=embed, view=view)
        
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error: {str(e)}",
            ephemeral=True
        )

@client.tree.command(name="sync", description="Sync slash commands (owner only)")
async def sync(interaction: discord.Interaction):
    """Manually sync slash commands"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        synced = await client.tree.sync()
        await interaction.followup.send(
            f"✅ Synced {len(synced)} command(s)",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Failed to sync: {str(e)}",
            ephemeral=True
        )

# Run the bot
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ Error: DISCORD_TOKEN not found in .env file")
    else:
        client.run(token)
