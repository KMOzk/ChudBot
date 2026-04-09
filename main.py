import os
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import datetime
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import re
import logging
from collections import defaultdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants for magic numbers
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_DESCRIPTION_LIMIT = 1000
MAX_EVENTS_PER_SYNC = 50
DAYS_FOR_POINTS_VIEW = 35

# Load environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')
CLASS_CALENDAR_ID = os.getenv('CLASS_CALENDAR_ID', 'dvg94ag773s3e5upapis8g89c8tgebim@import.calendar.google.com')
GUILD_ID = os.getenv('GUILD_ID')


def validate_environment():
    missing_vars = []
    if not TOKEN:
        missing_vars.append('DISCORD_TOKEN')
    if not CALENDAR_ID:
        missing_vars.append('GOOGLE_CALENDAR_ID')
    if missing_vars:
        logger.error(f"Error: Missing environment variables: {', '.join(missing_vars)}")
        exit(1)


SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

COLORS = {
    'red': '\033[2;31m',
    'green': '\033[2;32m',
    'yellow': '\033[2;33m',
    'blue': '\033[2;34m',
    'magenta': '\033[2;35m',
    'cyan': '\033[2;36m',
    'white': '\033[2;37m',
    'reset': '\033[0m',
    'bold_white': '\033[1;37m',
}

COLOR_PALETTE = [
    '\033[2;36m',
    '\033[2;32m',
    '\033[2;33m',
    '\033[2;35m',
    '\033[2;34m',
]


def clean_event_title(title):
    if not title or not isinstance(title, str):
        return "(Geen onderwerp)"

    clean_name = title
    prefixes_to_strip = [
        "TICT-V1SE1-24_2025 - Introduction to ICT_Leerlijn",
        "TICT-V1SE1-24_2025 - Introduction to ICT_Project",
        "TICT-V1SE1-24_2025 - Introduction to ICT_",
        "TICT-V1SE1-24_2025 - Introduction to ICT",
        "TICT-V1SE1-24_2025 - ",
    ]
    for prefix in prefixes_to_strip:
        if clean_name.startswith(prefix):
            clean_name = clean_name.replace(prefix, "").strip()
            if clean_name and clean_name.startswith("_"):
                clean_name = clean_name[1:].strip()
            break

    if clean_name and clean_name.startswith("Introduction to ICT_"):
        clean_name = clean_name.replace("Introduction to ICT_", "").strip()

    return clean_name or "(Geen onderwerp)"


def get_color_for_subject(subject, color_map):
    if not subject:
        return COLORS['white']
    s = subject.upper()

    if s == "PROG":
        return COLORS['red']

    if s == "OVERIG":
        return COLORS['white']

    if s not in color_map:
        color_idx = len(color_map) % len(COLOR_PALETTE)
        color_map[s] = COLOR_PALETTE[color_idx]

    return color_map[s]


def extract_subject(text):
    if not text or not isinstance(text, str):
        return "Overig", "(Geen onderwerp)"

    clean_title = clean_event_title(text)
    raw_subj = "Overig"

    match = re.match(r'\[(.*?)\]', clean_title)
    if match:
        raw_subj = match.group(1).strip()
        clean_title = clean_title.replace(match.group(0), "").strip()
    elif ":" in clean_title:
        parts = clean_title.split(":", 1)
        raw_subj = parts[0].strip()
        clean_title = parts[1].strip()
    else:
        words = clean_title.split()
        if words and words[0].isupper() and len(words[0]) <= 5:
            raw_subj = words[0]
            clean_title = " ".join(words[1:]).strip()

    clean_title = clean_title or text or '(Geen onderwerp)'
    text_upper = text.upper()
    if "PROG" in text_upper or "PROGRAM" in text_upper:
        return "PROG", clean_title
    if "CSC" in text_upper:
        return "CSC", clean_title
    if "MOD" in text_upper:
        return "MOD", clean_title
    if "BIM" in text_upper:
        return "BIM", clean_title

    return raw_subj, clean_title


def fetch_calendar_events(calendar_configs, start_time=None, end_time=None, max_results=MAX_EVENTS_PER_SYNC):
    """
    Fetches events from multiple Google Calendars and returns a list of unified event dictionaries.
    calendar_configs: list of dicts like {"id": "cal_id", "type": "class" or "personal"}
    """
    service = get_calendar_service()
    if not service:
        return []

    all_unified_events = []
    
    # Use current time if start_time is not provided
    if not start_time:
        start_time = datetime.datetime.now().astimezone().isoformat()

    for config in calendar_configs:
        cal_id = config["id"]
        cal_type = config.get("type", "personal")
        
        try:
            list_kwargs = {
                "calendarId": cal_id,
                "timeMin": start_time,
                "singleEvents": True,
                "orderBy": 'startTime'
            }
            if end_time:
                list_kwargs["timeMax"] = end_time
            if max_results:
                list_kwargs["maxResults"] = max_results
                
            events_result = service.events().list(**list_kwargs).execute()
            events = events_result.get('items', [])
        except Exception as e:
            logger.error(f"Error fetching calendar {cal_id}: {e}")
            continue

        for event in events:
            summary = str(event.get('summary') or '(Geen onderwerp)')
            description = str(event.get('description') or '')
            location = str(event.get('location') or 'Nader te bepalen')
            
            # Extract metadata using existing helpers
            points = extract_points(summary) or extract_points(description)
            subj, clean_name = extract_subject(summary)
            
            # Date parsing helper
            def parse_dt(dt_str):
                if not dt_str: return None
                if 'T' not in dt_str:
                    return datetime.datetime.fromisoformat(dt_str).replace(tzinfo=datetime.timezone.utc)
                return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))

            start_dt = parse_dt(event['start'].get('dateTime', event['start'].get('date')))
            end_dt = parse_dt(event['end'].get('dateTime', event['end'].get('date')))
            
            if not start_dt:
                continue

            all_unified_events.append({
                'id': event.get('id'),
                'summary': summary,
                'description': description,
                'location': location,
                'start_dt': start_dt,
                'end_dt': end_dt,
                'points': points,
                'subject': subj,
                'clean_title': clean_name,
                'calendar_id': cal_id,
                'calendar_type': cal_type,
                'html_link': event.get('htmlLink')
            })
            
    # Sort by start time
    all_unified_events.sort(key=lambda x: x['start_dt'])
    return all_unified_events


def format_events_for_discord(events, title, days=1, now=None):
    """Formats unified events into a list of Discord-ready messages (ANSI)."""
    if not now:
        now = datetime.datetime.now().astimezone()
        
    if not events:
        return [f"{title}\nGeen afspraken gepland."]

    subject_groups = defaultdict(list)
    total_points = 0
    color_map = {}

    for ev in events:
        if "ZELFSTANDIG WERKEN" in ev['summary'].upper():
            continue
        
        total_points += ev['points']
        subject_groups[ev['subject']].append(ev)

    lines = []
    sorted_subjects = sorted(subject_groups.keys(), key=lambda s: (0 if s.upper() == 'PROG' else 1, s.lower()))

    for i, subj in enumerate(sorted_subjects):
        color = get_color_for_subject(subj, color_map)
        subj_points = sum(ev['points'] for ev in subject_groups[subj])
        subj_point_str = f" {COLORS['yellow']}[Points: {subj_points}]{COLORS['reset']}" if subj_points > 0 else ""

        if i > 0:
            lines.append(f"{COLORS['white']}------------------------------------{COLORS['reset']}")
        lines.append(f"{COLORS['bold_white']}# {subj.upper()}{subj_point_str}{COLORS['reset']}")

        for ev in subject_groups[subj]:
            start_dt = ev['start_dt']
            clean_title = ev['clean_title']
            points = ev['points']

            days_left_str = ""
            if points > 0:
                delta_days = (start_dt - now.replace(tzinfo=datetime.timezone.utc)).days
                days_left_str = f" (Nog {delta_days}d)" if delta_days >= 0 else " (Verlopen)"

            point_str = f" {COLORS['yellow']}[Points: {points}]{COLORS['reset']}{days_left_str}" if points > 0 else ""
            date_prefix = ""
            if days > 1:
                days_nl = ["MA", "DI", "WO", "DO", "VR", "ZA", "ZO"]
                day_str = days_nl[start_dt.weekday()]
                date_prefix = f"({start_dt.strftime('%d-%m')} {day_str}) "

            time_str = start_dt.strftime('%H:%M') if ev['start_dt'].hour or ev['start_dt'].minute else "Hele dag"
            lines.append(f"{color}- {date_prefix}{time_str}: {clean_title}{point_str}{COLORS['reset']}")

    messages = []
    current_chunk = f"{title}\n```ansi\n"

    for line in lines:
        if len(current_chunk) + len(line) + 10 > DISCORD_MESSAGE_LIMIT:
            current_chunk += "```"
            messages.append(current_chunk)
            current_chunk = "```ansi\n" + line + "\n"
        else:
            current_chunk += line + "\n"

    current_chunk += "```"
    if total_points > 0:
        footer = f"\n🏆 **Totaal aantal punten: {total_points}**"
        if len(current_chunk) + len(footer) > DISCORD_MESSAGE_LIMIT:
            messages.append(current_chunk)
            current_chunk = footer
        else:
            current_chunk += footer
    messages.append(current_chunk)
    
    return messages


from micropython_formatter import format_events_for_micropython


def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        with open('token.json', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                logger.error("Token expired or revoked. Re-authenticating...")
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists('credentials.json'):
                logger.error("Error: credentials.json not found. Please add it to the project root.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)


def extract_points(text):
    if not text:
        return 0

    prefix_match = re.search(r'\b(?:points?|pts?|punten|pnt)[:\s]+(\d+)\b', text, re.IGNORECASE)
    if prefix_match:
        return int(prefix_match.group(1))

    suffix_match = re.search(r'\b(\d+)[ \t]*(?:points?|pts?|punten|pnt)\b', text, re.IGNORECASE)
    if suffix_match:
        return int(suffix_match.group(1))

    return 0


class CalendarNavigationView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="Vandaag", style=discord.ButtonStyle.primary)
    async def today_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.send_calendar_updates(interaction, days=1)

    @discord.ui.button(label="Morgen", style=discord.ButtonStyle.secondary)
    async def tomorrow_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.send_calendar_updates(interaction, days=1, for_tomorrow=True)

    @discord.ui.button(label="Deze Week", style=discord.ButtonStyle.success)
    async def week_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.send_calendar_updates(interaction, days=7)

    @discord.ui.button(label="Volgende Week", style=discord.ButtonStyle.danger)
    async def next_week_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.send_calendar_updates(interaction, days=7, for_next_week=True)


class SubjectFilterSelect(discord.ui.Select):
    def __init__(self, subjects, original_events, bot):
        options = [discord.SelectOption(label="Alle Vakken", value="all", description="Toon alle opdrachten")]
        for subj in sorted(subjects):
            options.append(discord.SelectOption(label=subj, value=subj))

        super().__init__(placeholder="Filter op vak...", min_values=1, max_values=1, options=options)
        self.original_events = original_events
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_subj = self.values[0]

        filtered_events = self.original_events
        if selected_subj != "all":
            filtered_events = [e for e in self.original_events if extract_subject(e.get('summary') or '')[0] == selected_subj]

        await self.bot.display_points(interaction, filtered_events, view=self.view)


class PointsView(discord.ui.View):
    def __init__(self, subjects, original_events, bot):
        super().__init__(timeout=180)
        self.add_item(SubjectFilterSelect(subjects, original_events, bot))


class ChudBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.startup_message_sent = False

    async def setup_hook(self):
        self.daily_calendar_check.start()

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"✅ Slash commands direct gesynct naar server ID: {GUILD_ID}")
        else:
            await self.tree.sync()
            logger.warning("⚠️ Slash commands globaal gesynct (dit kan tot een uur duren om in Discord te verschijnen).")

    async def on_ready(self):
        logger.info(f'Logged on as {self.user}!')
        if not self.startup_message_sent:
            await self.send_startup_assignment()

            for guild in self.guilds:
                logger.info(f"Starting startup sync for guild: {guild.name}")
                await self.sync_guild_events(guild)

            self.startup_message_sent = True

    async def sync_guild_events(self, guild, ctx=None, only_lessons=False):
        try:
            existing_events = await guild.fetch_scheduled_events()
        except Exception as e:
            logger.error(f"Could not fetch events for {guild.name}: {e}")
            return 0, 0

        created_count = 0
        skipped_count = 0
        reasons = defaultdict(int)

        configs = [{"id": CLASS_CALENDAR_ID, "type": "class"}]
        if not only_lessons:
            configs.append({"id": CALENDAR_ID, "type": "personal"})

        events = fetch_calendar_events(configs)

        for ev in events:
            summary_upper = ev['summary'].upper()
            display_name = '(Geen onderwerp)'
            
            if ev['calendar_type'] == "class":
                if "ZELFSTANDIG WERKEN" in summary_upper:
                    reasons["Zelfstandig werken"] += 1
                    skipped_count += 1
                    continue
                display_name = ev['clean_title']
            else:
                if ev['points'] <= 0:
                    reasons["Geen punten (persoonlijk)"] += 1
                    skipped_count += 1
                    continue
                location = "Deadline / Opdracht"
                display_name = f"[{ev['points']} pts] {ev['clean_title']}" if f"{ev['points']}" not in ev['clean_title'] else ev['clean_title']

            display_name = display_name or ev['summary'] or '(Geen onderwerp)'

            exists = any(e.name == display_name and abs((e.start_time - ev['start_dt']).total_seconds()) < 60 for e in existing_events)
            if exists:
                reasons["Bestaat al in Discord"] += 1
                skipped_count += 1
                continue

            event_image = None
            if ev['points'] > 0:
                try:
                    if os.path.exists('d.jpg'):
                        with open('d.jpg', 'rb') as f:
                            event_image = f.read()
                except Exception:
                    pass

            try:
                cal_link = f"https://calendar.google.com/calendar/embed?src={ev['calendar_id']}"
                full_description = f"{ev['description']}\n\n📍 Lokaal: {ev['location']}\n🔗 Agenda: {cal_link}"

                event_kwargs = {
                    "name": display_name[:100],
                    "description": full_description[:DISCORD_DESCRIPTION_LIMIT],
                    "start_time": ev['start_dt'],
                    "end_time": ev['end_dt'],
                    "location": ev['location'][:100],
                    "entity_type": discord.EntityType.external,
                    "privacy_level": discord.PrivacyLevel.guild_only
                }
                if event_image is not None:
                    event_kwargs["image"] = event_image

                await guild.create_scheduled_event(**event_kwargs)
                created_count += 1
            except Exception as e:
                logger.error(f"Failed to create Discord event '{display_name}': {e}")
                reasons[f"Fout: {type(e).__name__}"] += 1

        if ctx and created_count == 0 and skipped_count > 0:
            reason_str = ", ".join([f"{k}: {v}" for k, v in reasons.items()])
            msg = f"ℹ️ Geen nieuwe lessen aangemaakt. Redenen: {reason_str}"
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)

        return created_count, skipped_count

    async def send_startup_assignment(self):
        now_dt = datetime.datetime.now().astimezone()
        start_time = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_time = (now_dt + datetime.timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        configs = [{"id": CALENDAR_ID, "type": "personal"}]
        events = fetch_calendar_events(configs, start_time=start_time, end_time=end_time)

        for ev in events:
            if ev['points'] > 0:
                delta = (ev['start_dt'] - now_dt).days
                days_str = f"Nog {delta} dagen over" if delta >= 0 else "Deadline verstreken"

                days_nl = ["MA", "DI", "WO", "DO", "VR", "ZA", "ZO"]
                day_name = days_nl[ev['start_dt'].weekday()]
                date_str = f"{ev['start_dt'].strftime('%d-%m')} {day_name}"

                box_width = 50
                clean_summary = ev['summary'][:box_width - 15]

                message = (
                    "```ansi\n"
                    f"\033[1;37m╔{'═' * box_width}╗\033[0m\n"
                    f"\033[1;37m║\033[2;33m  🏆 VOLGENDE OPDRACHT MET PUNTEN{' ' * (box_width - 31)}\033[1;37m║\033[0m\n"
                    f"\033[1;37m╠{'═' * box_width}╣\033[0m\n"
                    f"\033[1;37m║\033[2;36m  Onderwerp:  \033[0m{clean_summary:<{box_width - 13}} \033[1;37m║\033[0m\n"
                    f"\033[1;37m║\033[2;36m  Datum:      \033[0m{date_str:<{box_width - 13}} \033[1;37m║\033[0m\n"
                    f"\033[1;37m║\033[2;33m  Waarde:     \033[0m{str(ev['points']) + ' pts':<{box_width - 13}} \033[1;37m║\033[0m\n"
                    f"\033[1;37m║\033[2;32m  Status:     \033[0m{days_str:<{box_width - 13}} \033[1;37m║\033[0m\n"
                    f"\033[1;37m╚{'═' * box_width}╝\033[0m\n"
                    "```\n"
                    "🌐 **Web Dashboard:** http://localhost:5000"
                )
                for guild in self.guilds:
                    channel = discord.utils.get(guild.text_channels, name='chud-bot')
                    if channel:
                        await channel.send(message)
                return

    @tasks.loop(hours=24)
    async def daily_calendar_check(self):
        await self.wait_until_ready()
        await self.send_calendar_updates(None, for_tomorrow=True)

    async def send_calendar_updates(self, ctx_or_int, days=1, for_tomorrow=False, for_next_week=False):
        now = datetime.datetime.now().astimezone()

        if for_tomorrow:
            start_date = now + datetime.timedelta(days=1)
            start_time = start_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            end_time = (start_date + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            title = "📅 **Agenda voor morgen:**"
        elif for_next_week:
            days_until_monday = (7 - now.weekday()) % 7 or 7
            start_date = now + datetime.timedelta(days=days_until_monday)
            start_time = start_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            end_time = (start_date + datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            title = "📅 **Agenda voor volgende week:**"
        else:
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            if days == 7:
                days_until_sunday = 6 - now.weekday()
                end_time = (now + datetime.timedelta(days=days_until_sunday + 1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                title = "📅 **Agenda voor deze week:**"
            else:
                end_time = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                title = "📅 **Agenda voor vandaag:**"

        configs = [
            {"id": CLASS_CALENDAR_ID, "type": "class"},
            {"id": CALENDAR_ID, "type": "personal"}
        ]
        
        events = fetch_calendar_events(configs, start_time=start_time, end_time=end_time)
        
        if not events:
            message = f"{title}\nGeen afspraken gepland."
            view = CalendarNavigationView(self)
            if ctx_or_int:
                if isinstance(ctx_or_int, discord.Interaction):
                    await ctx_or_int.edit_original_response(content=message, view=view)
                else:
                    await ctx_or_int.send(message, view=view)
            else:
                for guild in self.guilds:
                    target_channel = discord.utils.get(guild.text_channels, name='chud-bot')
                    if target_channel:
                        await target_channel.send(message, view=view)
            return

        messages_to_send = format_events_for_discord(events, title, days=days, now=now)
        view = CalendarNavigationView(self)

        if ctx_or_int:
            if isinstance(ctx_or_int, discord.Interaction):
                await ctx_or_int.edit_original_response(content=messages_to_send[0], view=view)
                for i in range(1, len(messages_to_send)):
                    await ctx_or_int.followup.send(messages_to_send[i])
            else:
                for i, msg in enumerate(messages_to_send):
                    if i == len(messages_to_send) - 1:
                        await ctx_or_int.send(msg, view=view)
                    else:
                        await ctx_or_int.send(msg)
        else:
            for guild in self.guilds:
                target_channel = discord.utils.get(guild.text_channels, name='chud-bot')
                if target_channel:
                    for i, msg in enumerate(messages_to_send):
                        if i == len(messages_to_send) - 1:
                            await target_channel.send(msg, view=view)
                        else:
                            await target_channel.send(msg)

    async def display_points(self, ctx_or_int, events, view=None):
        now_dt = datetime.datetime.now().astimezone()
        now_date = now_dt.date()
        start_of_this_week = now_date - datetime.timedelta(days=now_date.weekday())

        weekly_tasks = defaultdict(list)
        total_points = 0
        color_map = {}
        subjects = set()

        for ev in events:
            if ev['points'] > 0:
                task_date = ev['start_dt'].date()
                delta_days = (task_date - start_of_this_week).days
                week_index = delta_days // 7

                if 0 <= week_index <= 4:
                    subjects.add(ev['subject'])
                    total_points += ev['points']
                    weekly_tasks[week_index].append({
                        'date': task_date,
                        'subj': ev['subject'],
                        'clean_title': ev['clean_title'],
                        'points': ev['points']
                    })

        if not weekly_tasks:
            msg = "📅 Geen taken met punten gevonden."
            if isinstance(ctx_or_int, discord.Interaction):
                await ctx_or_int.edit_original_response(content=msg, view=view)
            else:
                await ctx_or_int.send(msg, view=view)
            return

        lines = []
        week_labels = {0: "DEZE WEEK", 1: "VOLGENDE WEEK", 2: "OVER 2 WEKEN", 3: "OVER 3 WEKEN", 4: "OVER 4 WEKEN"}

        for i in range(5):
            if i in weekly_tasks:
                if lines: lines.append(f"{COLORS['white']}------------------------------------{COLORS['reset']}")
                lines.append(f"{COLORS['bold_white']}# {week_labels[i]}{COLORS['reset']}")
                sorted_tasks = sorted(weekly_tasks[i], key=lambda x: x['date'])
                for task in sorted_tasks:
                    color = get_color_for_subject(task['subj'], color_map)

                    days_nl = ["MA", "DI", "WO", "DO", "VR", "ZA", "ZO"]
                    day_str = days_nl[task['date'].weekday()]
                    date_str = f"{task['date'].strftime('%d-%m')} {day_str}"

                    delta_days = (task['date'] - now_date).days
                    days_left_str = f" (Nog {delta_days}d)" if delta_days >= 0 else " (Verlopen)"
                    point_str = f" {COLORS['yellow']}[Points: {task['points']}]{COLORS['reset']}{days_left_str}"
                    lines.append(f"{color}• {date_str}: [{task['subj']}] {task['clean_title']}{point_str}{COLORS['reset']}")

        title = "📋 **Taken met punten:**"
        messages = []
        current_chunk = f"{title}\n```ansi\n"
        for line in lines:
            if len(current_chunk) + len(line) + 10 > DISCORD_MESSAGE_LIMIT:
                current_chunk += "```"
                messages.append(current_chunk)
                current_chunk = "```ansi\n" + line + "\n"
            else:
                current_chunk += line + "\n"

        current_chunk += "```\n🏆 **Totaal: {0} pts**".format(total_points)
        messages.append(current_chunk)

        if isinstance(ctx_or_int, discord.Interaction):
            await ctx_or_int.edit_original_response(content=messages[0], view=view)
            for i in range(1, len(messages)):
                await ctx_or_int.followup.send(messages[i])
        else:
            for i, msg in enumerate(messages):
                if i == len(messages) - 1:
                    await ctx_or_int.send(msg, view=view)
                else:
                    await ctx_or_int.send(msg)


bot = ChudBot()


@bot.hybrid_command(name='clear', description="Verwijder alle toekomstige evenementen die door de bot zijn aangemaakt.")
async def clear_command(ctx):
    await ctx.defer()

    try:
        existing_events = await ctx.guild.fetch_scheduled_events()
    except Exception as e:
        await ctx.send(f"⚠️ Fout bij ophalen evenementen: {e}")
        return

    deleted_count = 0
    now = datetime.datetime.now().astimezone()

    for event in existing_events:
        if event.start_time > now and (event.creator_id == bot.user.id or event.creator == bot.user):
            try:
                await event.delete()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Fout bij verwijderen event '{event.name}': {e}")

    await ctx.send(f"🗑️ Opgeruimd! {deleted_count} toekomstige evenementen verwijderd.")


@bot.hybrid_command(name='today', description="Bekijk de agenda van vandaag.")
async def events_command(ctx):
    await bot.send_calendar_updates(ctx, days=1)


@bot.hybrid_command(name='week', description="Bekijk de agenda van deze week.")
async def week_command(ctx):
    await bot.send_calendar_updates(ctx, days=7)


@bot.hybrid_command(name='nextweek', description="Bekijk de agenda van volgende week.")
async def next_week_command(ctx):
    await bot.send_calendar_updates(ctx, days=7, for_next_week=True)


@bot.hybrid_command(name='sync_lessons', description="Sync alleen lessen naar Discord evenementen.")
async def sync_lessons_command(ctx):
    await ctx.defer()
    created, skipped = await bot.sync_guild_events(ctx.guild, ctx, only_lessons=True)
    await ctx.send(f"✅ Lessen sync voltooid! {created} lessen aangemaakt, {skipped} overgeslagen.")


@bot.hybrid_command(name='sync', description="Sync lessen en opdrachten met punten naar Discord evenementen.")
async def sync_command(ctx):
    await ctx.defer()
    created, skipped = await bot.sync_guild_events(ctx.guild, ctx)
    await ctx.send(f"✅ Sync voltooid! {created} evenementen aangemaakt (lessen + opdrachten met punten), {skipped} overgeslagen.")


@bot.hybrid_command(name='sync_tasks', description="Sync opdrachten met punten naar Discord evenementen.")
async def sync_tasks_command(ctx):
    await ctx.defer()

    configs = [{"id": CALENDAR_ID, "type": "personal"}]
    events = fetch_calendar_events(configs)

    if not events:
        await ctx.send("📅 Geen aankomende opdrachten gevonden.")
        return

    existing_events = await ctx.guild.fetch_scheduled_events()

    created_count = 0
    skipped_count = 0

    for ev in events:
        if ev['points'] <= 0:
            continue

        exists = any(e.name == ev['summary'] and e.start_time == ev['start_dt'] for e in existing_events)

        if exists:
            skipped_count += 1
            continue

        try:
            await ctx.guild.create_scheduled_event(
                name=ev['summary'][:100],
                description=f"Punten: {ev['points']}\n\n{ev['description']}"[:DISCORD_DESCRIPTION_LIMIT],
                start_time=ev['start_dt'],
                end_time=ev['end_dt'],
                location="Deadline / Opdracht",
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only
            )
            created_count += 1
        except Exception as e:
            logger.error(f"Fout bij aanmaken evenement '{ev['summary']}': {e}")

    await ctx.send(f"✅ Sync voltooid! {created_count} opdrachten met punten aangemaakt als evenement, {skipped_count} overgeslagen.")


@bot.hybrid_command(name='points', description="Bekijk alle taken met punten.")
async def tasks_command(ctx):
    await ctx.defer()
    
    now_dt = datetime.datetime.now().astimezone()
    start_time = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_time = (now_dt + datetime.timedelta(days=DAYS_FOR_POINTS_VIEW)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    configs = [{"id": CALENDAR_ID, "type": "personal"}]
    events = fetch_calendar_events(configs, start_time=start_time, end_time=end_time)

    subjects = set(ev['subject'] for ev in events if ev['points'] > 0)

    view = PointsView(subjects, events, bot)
    await bot.display_points(ctx, events, view=view)


@bot.hybrid_command(name='debug_hu', description="Debug hulp voor de HU agenda.")
async def debug_hu_command(ctx):
    await ctx.defer()

    service = get_calendar_service()
    if not service:
        await ctx.send("❌ Google API niet geconfigureerd.")
        return

    cal_id = CLASS_CALENDAR_ID
    now = datetime.datetime.now().astimezone().isoformat()

    try:
        cal_meta = service.calendarList().get(calendarId=cal_id).execute()
        meta_msg = f"✅ Kalender gevonden: **{cal_meta.get('summary')}**\n"

        events_result = service.events().list(
            calendarId=cal_id, timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            msg = meta_msg + "❌ Geen evenementen gevonden in de komende tijd."
        else:
            event_list = "\n".join([f"- {e.get('summary')}" for e in events])
            msg = meta_msg + f"✅ {len(events)} evenementen gevonden:\n{event_list}"

        await ctx.send(msg[:2000])
    except Exception as e:
        await ctx.send(f"❌ Fout bij debuggen: {e}\nKalender ID: `{cal_id}`")


from flask import Flask, render_template
import threading

app = Flask(__name__)


@app.route('/')
def dashboard():
    now_dt = datetime.datetime.now().astimezone()
    start_time = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_time = (now_dt + datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    try:
        configs = [
            {"id": CLASS_CALENDAR_ID, "type": "class"},
            {"id": CALENDAR_ID, "type": "personal"}
        ]
        
        unified_events = fetch_calendar_events(configs, start_time=start_time, end_time=end_time)
        
        if not unified_events:
            return render_template('index.html', 
                                   events=[], 
                                   assignments=[], 
                                   today_count=0, 
                                   total_points=0, 
                                   subjects=[])

        all_events = []
        total_points = 0
        days_nl = ["MA", "DI", "WO", "DO", "VR", "ZA", "ZO"]

        for ev in unified_events:
            time_str = ev['start_dt'].strftime('%H:%M') if ev['start_dt'].hour or ev['start_dt'].minute else "Hele dag"
            day_name = days_nl[ev['start_dt'].weekday()]

            event_data = {
                'summary': ev['summary'],
                'clean_title': ev['clean_title'],
                'subject': ev['subject'],
                'time': time_str,
                'date': f"{ev['start_dt'].strftime('%d-%m')} {day_name}",
                'location': ev['location'],
                'points': ev['points'],
                'dt': ev['start_dt']
            }
            all_events.append(event_data)
            total_points += ev['points']

        today_date = now_dt.date()
        today_events = [e for e in all_events if e['dt'].date() == today_date]
        assignments = [e for e in all_events if e['points'] > 0]

        for a in assignments:
            delta = (a['dt'].date() - today_date).days
            a['days_left'] = f"Nog {delta}d" if delta >= 0 else "Verlopen"

        available_subjects = sorted(list(set(e['subject'] for e in all_events)))

        return render_template('index.html',
                               events=all_events,
                               assignments=assignments,
                               today_count=len(today_events),
                               total_points=total_points,
                               subjects=available_subjects)
    except Exception as e:
        logger.error(f"Web Dashboard Error: {e}")
        return f"⚠️ Fout bij ophalen data: {e}"


def run_webserver():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


if __name__ == '__main__':
    validate_environment()
    logger.info("Starting Web Dashboard...")
    threading.Thread(target=run_webserver, daemon=True).start()
    logger.info("Starting ChudBot...")
    bot.run(TOKEN)