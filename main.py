import os
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import datetime
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')

# Google Calendar API Scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_calendar_service():
    """Authenticates and returns the Google Calendar service."""
    creds = None
    # token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        with open('token.json', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("Error: credentials.json not found. Please add it to the project root.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)

def get_upcoming_events(service, calendar_id):
    """Fetches events for the current day."""
    now = datetime.datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    end_of_day = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    
    try:
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=start_of_day, timeMax=end_of_day,
            singleEvents=True, orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except Exception as e:
        print(f"Error fetching events: {e}")
        return []

import re

def extract_points(text):
    """Extracts points from text like 'Task [10]' or 'Task 10 pts'."""
    if not text:
        return 0
    # Look for [number], (number), or 'number points/pts'
    match = re.search(r'\[(\d+)\]|\((\d+)\)|(\d+)\s*(?:points|pts|pt|punten|pnt)', text, re.IGNORECASE)
    if match:
        # Return the first non-None group found
        for group in match.groups():
            if group:
                return int(group)
    return 0

class ChudBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Start the background task
        self.daily_calendar_check.start()

    async def on_ready(self):
        print(f'Logged on as {self.user}!')

    @tasks.loop(hours=24)
    async def daily_calendar_check(self):
        """Background task that runs every 24 hours."""
        await self.send_calendar_updates()

    async def send_calendar_updates(self, channel=None, days=1):
        """Fetches and sends calendar events for a specified number of days."""
        service = get_calendar_service()
        if not service:
            if channel:
                await channel.send("⚠️ Fout: `credentials.json` niet gevonden. Kan agenda niet laden.")
            return

        now = datetime.datetime.utcnow()
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        
        if days == 7:
            days_until_sunday = 6 - now.weekday()
            end_time = (now + datetime.timedelta(days=days_until_sunday + 1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            title = "📅 **Agenda voor deze week:**"
        else:
            end_time = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            title = "📅 **Agenda voor vandaag:**"

        try:
            events_result = service.events().list(
                calendarId=CALENDAR_ID, timeMin=start_time, timeMax=end_time,
                singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
        except Exception as e:
            print(f"Error fetching events: {e}")
            if channel:
                await channel.send(f"⚠️ Fout bij ophalen agenda: {e}")
            return
        
        message = f"{title}\n"
        total_points = 0
        
        if not events:
            message += "Geen afspraken gepland."
        else:
            current_date = None
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', '(Geen onderwerp)')
                description = event.get('description', '')
                
                # Combine summary and description to look for points
                points = extract_points(summary) or extract_points(description)
                total_points += points
                
                point_str = f" **[{points} pnt]**" if points > 0 else ""
                
                event_date = start.split('T')[0]
                if event_date != current_date and days > 1:
                    current_date = event_date
                    message += f"\n🗓️ **{event_date}:**\n"

                if 'T' in start:
                    time_str = start.split('T')[1][:5]
                    message += f"- **{time_str}**: {summary}{point_str}\n"
                else:
                    message += f"- **Hele dag**: {summary}{point_str}\n"

            if total_points > 0:
                message += f"\n🏆 **Totaal aantal punten: {total_points}**"

        if channel:
            await channel.send(message)
        else:
            for guild in self.guilds:
                target_channel = discord.utils.get(guild.text_channels, name='chud-bot')
                if target_channel:
                    await target_channel.send(message)

# Initialize Bot
bot = ChudBot()

@bot.command(name='today')
async def events_command(ctx):
    """Manual command to check today's events."""
    await bot.send_calendar_updates(ctx.channel, days=1)

@bot.command(name='week')
async def week_command(ctx):
    """Manual command to check this week's events."""
    await bot.send_calendar_updates(ctx.channel, days=7)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Basic response from original code
    if message.content.lower() == 'yo':
        await message.channel.send('yo')
    
    # Ensure commands still work
    await bot.process_commands(message)

if __name__ == '__main__':
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env file.")
    else:
        bot.run(TOKEN)
