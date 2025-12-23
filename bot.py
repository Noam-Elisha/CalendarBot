import os
import sys
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
        self.shared_events_file = 'userdata/shared_events.json'
        self.user_calendar_events_file = 'userdata/user_calendar_events.json'
        self.user_emails = self.load_user_data()
        self.shared_events = self.load_shared_events()
        self.user_calendar_events = self.load_user_calendar_events()
    
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
    
    def load_shared_events(self):
        """Load shared events data from JSON file"""
        if os.path.exists(self.shared_events_file):
            with open(self.shared_events_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_shared_events(self):
        """Save shared events data to JSON file"""
        with open(self.shared_events_file, 'w') as f:
            json.dump(self.shared_events, f, indent=2)
    
    def load_user_calendar_events(self):
        """Load user calendar events mapping from JSON file"""
        if os.path.exists(self.user_calendar_events_file):
            with open(self.user_calendar_events_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_user_calendar_events(self):
        """Save user calendar events mapping to JSON file"""
        with open(self.user_calendar_events_file, 'w') as f:
            json.dump(self.user_calendar_events, f, indent=2)

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
    def __init__(self, event_id: str, event_link: str = None, discord_event_id: str = None, guild_id: int = None, creator_id: str = None):
        super().__init__(timeout=None)  # Buttons persist
        self.event_id = event_id
        self.discord_event_id = discord_event_id
        self.guild_id = guild_id
        self.creator_id = creator_id
        
        # Only add "View in Calendar" link button if event_link is provided
        if event_link:
            view_button = discord.ui.Button(
                label="View in Calendar",
                style=discord.ButtonStyle.link,
                url=event_link,
                emoji="🔗"
            )
            self.add_item(view_button)
    
    @discord.ui.button(label="Add to My Calendar", style=discord.ButtonStyle.success, emoji="📅", custom_id="persistent:add_to_calendar")
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
            
            # Store the calendar event ID for this user
            if user_id not in client.user_calendar_events:
                client.user_calendar_events[user_id] = []
            client.user_calendar_events[user_id].append({
                'calendar_event_id': calendar_event_id,
                'event_name': event_data['name'],
                'shared_event_id': self.event_id
            })
            client.save_user_calendar_events()
            
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
    
    @discord.ui.button(label="Delete Event", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="persistent:delete_shared_event")
    async def delete_shared_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is the creator
        if str(interaction.user.id) != self.creator_id:
            await interaction.response.send_message("❌ Only the event creator can delete this event.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Delete Discord scheduled event if it exists
            if self.discord_event_id and self.guild_id:
                try:
                    guild = interaction.client.get_guild(self.guild_id)
                    if guild:
                        scheduled_event = await guild.fetch_scheduled_event(int(self.discord_event_id))
                        await scheduled_event.delete()
                except Exception as e:
                    print(f"Failed to delete Discord event: {e}")
            
            # Remove from shared events
            if self.event_id in client.shared_events:
                event_name = client.shared_events[self.event_id]['name']
                event_start = client.shared_events[self.event_id]['start']
                event_end = client.shared_events[self.event_id]['end']
                del client.shared_events[self.event_id]
                client.save_shared_events()
                
                # Create response embed with remove button
                delete_embed = discord.Embed(
                    title="✅ Event Deleted",
                    description=f"**{event_name}** has been deleted from the bot and Discord events.",
                    color=discord.Color.green()
                )
                delete_embed.add_field(
                    name="Remove from Your Calendar",
                    value="If you had added this event to your Google Calendar, click the button below to remove it.",
                    inline=False
                )
                
                # Create view with remove from calendar button
                remove_view = RemoveDeletedEventView(event_name, event_start, event_end)
                
                await interaction.followup.send(embed=delete_embed, view=remove_view, ephemeral=True)
                
                # Update the original message to show it's deleted
                try:
                    await interaction.message.edit(content="⚠️ This event has been deleted.", embed=None, view=None)
                except:
                    pass
            else:
                await interaction.followup.send("❌ Event not found.", ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ Error deleting event: {str(e)}", ephemeral=True)

# Custom View for removing a deleted event from user's calendar
class RemoveDeletedEventView(discord.ui.View):
    def __init__(self, event_name: str, event_start: str, event_end: str):
        super().__init__(timeout=300)  # 5 minute timeout since it's ephemeral
        self.event_name = event_name
        self.event_start = event_start
        self.event_end = event_end
    
    @discord.ui.button(label="Remove from My Calendar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_from_calendar(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        # Check if user is registered
        if user_id not in client.user_emails:
            await interaction.response.send_message(
                "❌ You're not registered or don't have this event in your calendar.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check if user has this event
            has_event = await check_if_user_has_event(
                user_id,
                self.event_name,
                self.event_start,
                self.event_end
            )
            
            if not has_event:
                await interaction.followup.send(
                    "❌ This event is not in your calendar.",
                    ephemeral=True
                )
                return
            
            # Load user's credentials
            user_data = client.user_emails[user_id]
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
            
            # Find and delete the event
            start_rfc = self.event_start
            end_rfc = self.event_end
            
            # Add timezone suffix if not present
            if not start_rfc.endswith('Z') and '+' not in start_rfc and start_rfc.count('-') == 2:
                start_rfc += '-08:00'
            if not end_rfc.endswith('Z') and '+' not in end_rfc and end_rfc.count('-') == 2:
                end_rfc += '-08:00'
            
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_rfc,
                timeMax=end_rfc,
                q=self.event_name,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            # Find matching event and delete it
            deleted = False
            for event in events:
                if event.get('summary') == self.event_name:
                    service.events().delete(calendarId='primary', eventId=event['id']).execute()
                    deleted = True
                    
                    # Remove from tracking
                    if user_id in client.user_calendar_events:
                        client.user_calendar_events[user_id] = [
                            e for e in client.user_calendar_events[user_id]
                            if e['calendar_event_id'] != event['id']
                        ]
                        client.save_user_calendar_events()
                    break
            
            if deleted:
                await interaction.followup.send(
                    f"✅ **{self.event_name}** has been removed from your calendar.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Could not find the event in your calendar.",
                    ephemeral=True
                )
        
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error removing event: {str(e)}",
                ephemeral=True
            )

# Custom View for delete button on success response
class DeleteEventView(discord.ui.View):
    def __init__(self, user_id: str, calendar_event_id: str, event_name: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.calendar_event_id = calendar_event_id
        self.event_name = event_name
    
    @discord.ui.button(label="Delete from Calendar", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="persistent:delete_from_calendar")
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
            
            # Remove from tracking
            if self.user_id in client.user_calendar_events:
                client.user_calendar_events[self.user_id] = [
                    e for e in client.user_calendar_events[self.user_id] 
                    if e['calendar_event_id'] != self.calendar_event_id
                ]
                client.save_user_calendar_events()
            
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
    
    # Register persistent views for all stored events
    for event_id, event_data in client.shared_events.items():
        client.add_view(AddToCalendarView(
            event_id, 
            None,
            discord_event_id=event_data.get('discord_event_id'),
            guild_id=event_data.get('guild_id'),
            creator_id=event_data.get('creator_id')
        ))
    
    # Register DeleteEventView for all user calendar events
    for user_id, events in client.user_calendar_events.items():
        for event_info in events:
            client.add_view(DeleteEventView(
                user_id, 
                event_info['calendar_event_id'], 
                event_info['event_name']
            ))
    
    print(f'Loaded {len(client.shared_events)} shared events')
    print(f'Loaded calendar events for {len(client.user_calendar_events)} users')



async def is_owner(interaction: discord.Interaction) -> bool:
    """Check if user is the owner"""
    OWNER_ID = int(os.getenv('OWNER_ID', '0'))
    return interaction.user.id == OWNER_ID

@client.tree.command(name="update", description="Update CalendarBot's code", guild=discord.Object(id=int(os.getenv('TEST_GUILD_ID', '0'))))
@app_commands.check(is_owner)
async def update(interaction: discord.Interaction):
    await interaction.response.send_message("Updating!", ephemeral=True)
    os.system("git pull")
    sys.exit(0)

@client.tree.command(name="stop", description="shut down CalendarBot", guild=discord.Object(id=int(os.getenv('TEST_GUILD_ID', '0'))))
@app_commands.check(is_owner)
async def stop(interaction: discord.Interaction):
    await interaction.response.send_message("Shutting down!", ephemeral=True)
    sys.exit(-1)

@client.tree.command(name="restart", description="reboot CalendarBot", guild=discord.Object(id=int(os.getenv('TEST_GUILD_ID', '0'))))
@app_commands.check(is_owner)
async def restart(interaction: discord.Interaction):
    await interaction.response.send_message("Restarting!", ephemeral=True)
    sys.exit(0)

@client.tree.command(name="code", description="View CalendarBot's source code on GitHub")
async def code(interaction: discord.Interaction):
    """Display link to GitHub repository"""
    embed = discord.Embed(
        title="📦 CalendarBot Source Code",
        description="View and contribute to CalendarBot on GitHub!",
        color=discord.Color.blurple(),
        url="https://github.com/Noam-Elisha/CalendarBot"
    )
    embed.add_field(
        name="Repository",
        value="[github.com/Noam-Elisha/CalendarBot](https://github.com/Noam-Elisha/CalendarBot)",
        inline=False
    )
    embed.set_footer(text="Feel free to star the repo ⭐")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
        client.shared_events[event_id] = {
            'name': name,
            'description': description or '',
            'start': event_dt.isoformat(),
            'end': end_dt.isoformat(),
            'creator_id': str(interaction.user.id),
            'location': location or ''
        }
        client.save_shared_events()
        
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
        
        # Create Discord scheduled event
        try:
            # Convert Pacific time to UTC-aware datetime for Discord
            from datetime import timezone
            
            # Create timezone-aware datetime (Pacific is UTC-8)
            pacific_tz = timezone(timedelta(hours=-8))
            event_dt_aware = event_dt.replace(tzinfo=pacific_tz)
            end_dt_aware = end_dt.replace(tzinfo=pacific_tz)
            
            scheduled_event = await interaction.guild.create_scheduled_event(
                name=name,
                description=description or "No description provided",
                start_time=event_dt_aware,
                end_time=end_dt_aware,
                entity_type=discord.EntityType.external,
                location=location or "No location specified",
                privacy_level=discord.PrivacyLevel.guild_only
            )
            
            discord_event_id = str(scheduled_event.id)
            
            # Store discord event ID in shared events
            client.shared_events[event_id]['discord_event_id'] = discord_event_id
            client.shared_events[event_id]['guild_id'] = interaction.guild_id
            client.save_shared_events()
            
            # Add event link to embed
            embed.add_field(
                name="🎫 Discord Event",
                value=f"[View Event](https://discord.com/events/{interaction.guild_id}/{scheduled_event.id})",
                inline=False
            )
        except Exception as e:
            print(f"Failed to create Discord scheduled event: {e}")
            discord_event_id = None
            # Continue even if Discord event creation fails
        
        # Create interactive view with buttons (no View link since event isn't created yet)
        view = AddToCalendarView(
            event_id, 
            None, 
            discord_event_id=discord_event_id if 'discord_event_id' in locals() else None,
            guild_id=interaction.guild_id,
            creator_id=str(interaction.user.id)
        )
        
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error creating event: {str(e)}",
            ephemeral=True
        )

@client.tree.command(name="sync", description="Sync slash commands (owner only)", guild=discord.Object(id=int(os.getenv('TEST_GUILD_ID', '0'))))
async def sync(interaction: discord.Interaction):
    """Manually sync slash commands"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Sync global commands
        synced_global = await client.tree.sync()
        
        # Sync test guild commands
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id:
            test_guild = discord.Object(id=test_guild_id)
            synced_guild = await client.tree.sync(guild=test_guild)
            total_synced = len(synced_global) + len(synced_guild)
        else:
            total_synced = len(synced_global)
        
        synced = total_synced
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
