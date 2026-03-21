# CHUD (Calendar Hogeschool Utrecht Discord) 🎓

**CHUD** is de slimme assistent voor studenten aan de **Hogeschool Utrecht**. De bot is ontworpen om de kloof tussen je Google Calendar en Discord te overbruggen door automatisch lesroosters en belangrijke opdrachten te synchroniseren naar Discord Scheduled Events.

## ✨ Functies

-   📅 **HU Rooster Sync**: Synchroniseert automatisch je lessen van de klassenagenda naar overzichtelijke Discord-evenementen.
-   🏆 **Punten-Gedreven Opdrachten**: Herkent opdrachten met punten in je persoonlijke agenda en maakt hier deadlines van op Discord.
-   🎨 **Visuele Agenda**: Gebruikt ANSI-kleuren om vakken zoals PROG, CSC, MOD en BIM direct herkenbaar te maken in Discord berichten.
-   📋 **Deadlines opvragen**: Met `/points` krijg je een direct overzicht van alle aankomende taken en hun waarde voor de komende 5 weken.
-   🛠️ **Slimme Filtering**: Verwijdert overbodige tekst zoals "Zelfstandig werken" en lange vak-codes voor een schoon en leesbaar resultaat.

## 💡 Hoe het werkt

Om het maximale uit **CHUD** te halen, raden we de volgende workflow aan:

1.  **BetterCanvas Plugin**: Installeer de [BetterCanvas](https://chrome.google.com/webstore/detail/better-canvas/idndmbiaphladnnepfghngbeacgeackba) browser extensie.
2.  **Agenda Sync**: Gebruik BetterCanvas om je Canvas-taken en deadlines automatisch te synchroniseren met je **Google Calendar**.
3.  **Discord Sync**: Gebruik het `/sync` commando van CHUD om deze opdrachten (inclusief punten!) direct als evenementen in je Discord-server te zetten.

## 🚀 Commando's (Hybrid)

-   `/sync`: De krachtpatser van de bot. Synchroniseert zowel je lessen als je opdrachten met punten naar Discord.
-   `/today`: Je dagoverzicht in een oogopslag.
-   `/week`: Alles wat je deze week nog moet doen.
-   `/nextweek`: Een vooruitblik naar de volgende lesweek.
-   `/points`: Een lijst van alle beschikbare punten die je nog kunt binnenslepen.

## 🛠️ Installatie

1.  Clone de repository.
2.  Vul je `.env` bestand aan:
    ```env
    DISCORD_TOKEN=jouw_discord_token
    GOOGLE_CALENDAR_ID=jouw_persoonlijke_agenda_id
    GUILD_ID=jouw_server_id
    ```
3.  Zet je Google Calendar `credentials.json` in de hoofdmap.
4.  Installeer dependencies: `pip install -r requirements.txt`
5.  Start de bot: `python main.py`

---
*CHUD: De ultieme assistent voor elke HU student.*
