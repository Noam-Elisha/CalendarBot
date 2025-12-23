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
        self.user_data_file = 'userdata/user_data.json'
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

async def check_if_user_has_event(user_id: str, event_name: str, start_time: str, end_time: str) -> bool:
    """
    Check if a user has a specific event in their calendar
    
    Args:
        user_id: Discord user ID
        event_name: Name of the event to search for
        start_time: ISO format start time of the event
        end_time: ISO format end time of the event
    
    Returns:
        True if event exists in user's calendar, False otherwise
    """
    try:
        # Check if user is registered
        if user_id not in client.user_emails:
            return False
        
        # Load user's credentials
        user_data = client.user_emails[user_id]
        creds_file = user_data.get('creds_file')
        
        if not creds_file or not os.path.exists(creds_file):
            return False
        
        with open(creds_file, 'rb') as token:
            creds = pickle.load(token)
        
        # Refresh credentials if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(creds_file, 'wb') as token:
                pickle.dump(creds, token)
        
        # Verify credentials are valid
        if not creds or not creds.valid:
            return False
        
        # Create calendar service
        service = build('calendar', 'v3', credentials=creds)
        
        # Search for events in the time range
        # Convert ISO format to RFC3339 with timezone
        start_rfc = start_time
        end_rfc = end_time
        
        # Add timezone suffix if not present
        if not start_rfc.endswith('Z') and '+' not in start_rfc and start_rfc.count('-') == 2:
            start_rfc += '-08:00'  # Pacific timezone
        if not end_rfc.endswith('Z') and '+' not in end_rfc and end_rfc.count('-') == 2:
            end_rfc += '-08:00'  # Pacific timezone
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_rfc,
            timeMax=end_rfc,
            q=event_name,  # Search by event name
            singleEvents=True
        ).execute()
        
        events = events_result.get('items', [])
        
        # Check if any event matches the name exactly
        for event in events:
            if event.get('summary') == event_name:
                return True
        
        return False
        
    except Exception as e:
        print(f"Error checking calendar: {e}")
        return False

# Custom View for Add to Calendar button
class AddToCalendarView(discord.ui.View):
    def __init__(self, event_id: str, event_link: str = None):
        super().__init__(timeout=None)  # Buttons persist
        self.event_id = event_id
        
        # Only add "View in Calendar" link button if event_link is provided
        if event_link:
            view_button = discord.ui.Button(
                label="View in Calendar",
                style=discord.ButtonStyle.link,
                url=event_link,
                emoji="🔗"
            )
            self.add_item(view_button)
    
    @discord.ui.button(label="Add to My Calendar", style=discord.ButtonStyle.success, emoji="📅")
    async def add_to_calendar(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        # Check if user is registered
        if user_id not in client.user_emails:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register` to connect your Google Calendar.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get event details
            if not hasattr(client, 'shared_events') or self.event_id not in client.shared_events:
                await interaction.followup.send(
                    "❌ Event information not found.",
                    ephemeral=True
                )
                return
            
            event_data = client.shared_events[self.event_id]
            
            # Check if user already has this event (including if they're the creator)
            has_event = await check_if_user_has_event(
                user_id,
                event_data['name'],
                event_data['start'],
                event_data['end']
            )
            
            if has_event:
                await interaction.followup.send(
                    "✅ This event is already in your calendar!",
                    ephemeral=True
                )
                return
            
            # Load user's credentials
            user_data = client.user_emails[user_id]
            creds_file = user_data.get('creds_file')
            
            if not creds_file or not os.path.exists(creds_file):
                await interaction.followup.send(
                    "❌ Your credentials are missing. Please `/unregister` and `/register` again.",
                    ephemeral=True
                )
                return
            
            with open(creds_file, 'rb') as token:
                creds = pickle.load(token)
            
            # Refresh credentials if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(creds_file, 'wb') as token:
                    pickle.dump(creds, token)
            
            # Verify credentials are valid
            if not creds or not creds.valid:
                await interaction.followup.send(
                    "❌ Your credentials are invalid. Please `/unregister` and `/register` again.",
                    ephemeral=True
                )
                return
            
            # Create calendar service with user's credentials
            service = build('calendar', 'v3', credentials=creds)
            
            # Create the event on user's calendar
            event = {
                'summary': event_data['name'],
                'description': event_data['description'],
                'start': {
                    'dateTime': event_data['start'],
                    'timeZone': 'America/Los_Angeles',
                },
                'end': {
                    'dateTime': event_data['end'],
                    'timeZone': 'America/Los_Angeles',
                },
            }
            
            # Add location if it exists
            if event_data.get('location'):
                event['location'] = event_data['location']
            
            # Add the event
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            event_link = created_event.get('htmlLink')
            calendar_event_id = created_event.get('id')
            
            # Create success embed
            success_embed = discord.Embed(
                title="✅ Event Added",
                description=f"**{event_data['name']}** has been added to your calendar!",
                color=discord.Color.green()
            )
            
            # Parse the datetime for display
            event_start = datetime.fromisoformat(event_data['start'])
            unix_timestamp = int(event_start.timestamp())
            
            success_embed.add_field(
                name="📅 Event Time",
                value=f"<t:{unix_timestamp}:F>",
                inline=False
            )
            
            if event_data['description']:
                success_embed.add_field(
                    name="Description",
                    value=event_data['description'],
                    inline=False
                )
            
            # Create view with calendar link and delete buttons
            response_view = DeleteEventView(user_id, calendar_event_id, event_data['name'])
            calendar_button = discord.ui.Button(
                label="View in Calendar",
                style=discord.ButtonStyle.link,
                url=event_link,
                emoji="🔗"
            )
            response_view.add_item(calendar_button)
            
            await interaction.followup.send(
                embed=success_embed,
                view=response_view,
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error adding event: {str(e)}",
                ephemeral=True
            )

# Custom View for delete button on success response
class DeleteEventView(discord.ui.View):
    def __init__(self, user_id: str, calendar_event_id: str, event_name: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.calendar_event_id = calendar_event_id
        self.event_name = event_name
    
    @discord.ui.button(label="Delete from Calendar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verify it's the same user
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ This is not your event to delete.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Load user's credentials
            user_data = client.user_emails[self.user_id]
            creds_file = user_data.get('creds_file')
            
            if not creds_file or not os.path.exists(creds_file):
                await interaction.followup.send(
                    "❌ Your credentials are missing.",
                    ephemeral=True
                )
                return
            
            with open(creds_file, 'rb') as token:
                creds = pickle.load(token)
            
            # Refresh credentials if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(creds_file, 'wb') as token:
                    pickle.dump(creds, token)
            
            # Create calendar service
            service = build('calendar', 'v3', credentials=creds)
            
            # Delete the event
            service.events().delete(calendarId='primary', eventId=self.calendar_event_id).execute()
            
            # Update the original message
            delete_embed = discord.Embed(
                title="🗑️ Event Deleted",
                description=f"**{self.event_name}** has been removed from your calendar.",
                color=discord.Color.red()
            )
            
            await interaction.edit_original_response(embed=delete_embed, view=None)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error deleting event: {str(e)}",
                ephemeral=True
            )

@client.event
async def on_ready():
    """Event handler for when the bot is ready"""
    print(f'{client.user} has connected to Discord!')
    print(f'Bot is in {len(client.guilds)} guilds')


@client.tree.command(name="register", description="Connect your Google Calendar")
async def register(interaction: discord.Interaction):
    """Register user's Google Calendar through OAuth"""
    user_id = str(interaction.user.id)
    
    # Check if user is already registered
    if user_id in client.user_emails:
        await interaction.response.send_message(
            "✅ You're already registered! Use `/unregister` to disconnect your account.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Create OAuth flow with manual redirect URI
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', 
            SCOPES,
            redirect_uri='https://localhost'
        )
        
        # Generate authorization URL
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline'
        )
        
        embed = discord.Embed(
            title="🔐 Google Calendar Authentication",
            description="Click the link below to authorize access to your Google Calendar:",
            color=discord.Color.blue()
        )
        
        view = discord.ui.View()
        button = discord.ui.Button(
            label="Authorize Google Calendar",
            style=discord.ButtonStyle.link,
            url=auth_url,
            emoji="🔗"
        )
        view.add_item(button)
        
        embed.add_field(
            name="Steps:",
            value=(
                "1. Click the button above\n"
                "2. Sign in with your Google account\n"
                "3. Grant calendar access\n"
                "4. Copy the ENTIRE URL from your browser after authorization\n"
                "   (It will look like: http://localhost/?code=...&scope=...)\n"
                "5. Use `/verify <full_url>` to complete setup"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"User ID: {user_id}")
        
        # Store the flow temporarily (in a real app, use a database)
        if not hasattr(client, 'pending_auths'):
            client.pending_auths = {}
        client.pending_auths[user_id] = flow
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error starting authentication: {str(e)}",
            ephemeral=True
        )

@client.tree.command(name="verify", description="Complete Google Calendar registration")
@app_commands.describe(url="The full redirect URL from Google (starting with http://localhost/?code=...)")
async def verify(interaction: discord.Interaction, url: str):
    """Complete OAuth flow with authorization code"""
    code = url
    user_id = str(interaction.user.id)
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Check if user has a pending auth
        if not hasattr(client, 'pending_auths') or user_id not in client.pending_auths:
            await interaction.followup.send(
                "❌ No pending registration found. Use `/register` first.",
                ephemeral=True
            )
            return
        
        flow = client.pending_auths[user_id]
        
        # Extract code from URL if full URL was provided
        auth_response = code.strip()
        
        # Add http:// if it's missing
        if auth_response.startswith('localhost') or auth_response.startswith('127.0.0.1'):
            auth_response = 'http://' + auth_response
        
        # Check if it's a URL (http or https)
        if (auth_response.startswith('http://localhost') or 
            auth_response.startswith('http://127.0.0.1') or
            auth_response.startswith('https://localhost') or
            auth_response.startswith('https://127.0.0.1')):
            # Extract just the code from the URL
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(auth_response)
            params = parse_qs(parsed.query)
            
            if 'code' in params:
                auth_code = params['code'][0]
                flow.fetch_token(code=auth_code)
            else:
                raise ValueError("No code found in URL")
        else:
            # Assume it's just the code
            flow.fetch_token(code=auth_response)
        
        creds = flow.credentials
        
        # Get user's calendar info
        service = build('calendar', 'v3', credentials=creds)
        calendar = service.calendarList().get(calendarId='primary').execute()
        email = calendar.get('id', 'unknown')
        
        # Save credentials
        user_creds_file = f'userdata/user_creds_{user_id}.pickle'
        with open(user_creds_file, 'wb') as token:
            pickle.dump(creds, token)
        
        # Store user info
        client.user_emails[user_id] = {
            'email': email,
            'username': interaction.user.name,
            'creds_file': user_creds_file
        }
        client.save_user_data()
        
        # Clean up pending auth
        del client.pending_auths[user_id]
        
        embed = discord.Embed(
            title="✅ Registration Complete",
            description="Your Google Calendar is now connected!",
            color=discord.Color.green()
        )
        embed.add_field(name="Calendar", value=email, inline=False)
        embed.add_field(
            name="Next Steps",
            value="You can now create calendar events using `/create_event`",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error completing registration: {str(e)}\nMake sure you copied the entire authorization code.",
            ephemeral=True
        )

@client.tree.command(name="unregister", description="Disconnect your Google Calendar")
async def unregister(interaction: discord.Interaction):
    """Remove user's Google Calendar connection"""
    user_id = str(interaction.user.id)
    
    if user_id not in client.user_emails:
        await interaction.response.send_message(
            "❌ You're not registered.",
            ephemeral=True
        )
        return
    
    # Delete credentials file
    user_data = client.user_emails[user_id]
    creds_file = user_data.get('creds_file')
    if creds_file and os.path.exists(creds_file):
        os.remove(creds_file)
    
    # Remove from user data
    del client.user_emails[user_id]
    client.save_user_data()
    
    await interaction.response.send_message(
        "✅ Your Google Calendar has been disconnected.",
        ephemeral=True
    )

@client.tree.command(name="create_event", description="Create a calendar event")
@app_commands.describe(
    name="Event name/title",
    date="Date in MM/DD/YYYY format (e.g., 12/25/2025)",
    time="Time in Pacific time (e.g., 2:30 PM or 14:30)",
    description="Optional event description",
    duration="Duration in hours (default: 1)",
    location="Optional event location"
)
async def create_event(
    interaction: discord.Interaction, 
    name: str, 
    date: str, 
    time: str,
    description: str = None,
    duration: float = 1.0,
    location: str = None
):
    """Create a calendar event announcement"""
    await interaction.response.defer()
    
    try:
        # Validate duration
        if duration <= 0:
            await interaction.followup.send(
                "❌ Duration must be greater than 0 hours.",
                ephemeral=True
            )
            return
        
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
            await interaction.followup.send(
                "❌ Invalid date/time format. Use MM/DD/YYYY for date and time like '2:30 PM' or '14:30'",
                ephemeral=True
            )
            return
        
        # Set duration (default 1 hour, or user-specified)
        end_dt = event_dt + timedelta(hours=duration)
        
        # Generate a unique event ID
        import uuid
        event_id = str(uuid.uuid4())
        
        # Store event info for "Add to Calendar" functionality
        if not hasattr(client, 'shared_events'):
            client.shared_events = {}
        
        client.shared_events[event_id] = {
            'name': name,
            'description': description or '',
            'start': event_dt.isoformat(),
            'end': end_dt.isoformat(),
            'creator_id': str(interaction.user.id),
            'location': location or ''
        }
        
        # Get Discord timestamp (Unix timestamp)
        unix_timestamp = int(event_dt.timestamp())
        
        embed = discord.Embed(
            title="📅 Event Created:",
            description=f"",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Name:",
            value=name,
            inline=True
        )
        embed.add_field(
            name="Created by",
            value=interaction.user.mention,
            inline=True
        )
        
        if location:
            embed.add_field(
                name="Location:",
                value=location,
                inline=False
            )
        
        if description:
            embed.add_field(
                name="Description:",
                value=description,
                inline=False
            )
        
        # Discord timestamp formats:
        # <t:timestamp:R> = relative time (e.g., "in 2 hours")
        # <t:timestamp:F> = full date/time (e.g., "Monday, December 25, 2025 2:30 PM")
        embed.add_field(
            name="Event Time:",
            value=f"<t:{unix_timestamp}:F> - (<t:{unix_timestamp}:R>)",
            inline=False
        )
        
        # Only show duration if it wasn't specified (using default)
        embed.add_field(
            name="Duration",
            value=f"{duration} hour{'s' if duration != 1 else ''}",
            inline=True
        )
        
        embed.set_footer(text="Click 'Add to My Calendar' to add this event to your Google Calendar")
        
        # Create interactive view with buttons (no View link since event isn't created yet)
        view = AddToCalendarView(event_id, None)
        
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error creating event: {str(e)}",
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
