# Video-Analyse Telegram Bot

Deine Mitarbeiter schicken ein Video an den Telegram-Bot, Gemini analysiert es automatisch und speichert die Ergebnisse in einer Liste pro Model. Der Bot kennt die Patterns die bei jedem Model funktionieren und schlaegt sie bei jeder Analyse vor.

---

## Features

- Video-Analyse per Gemini (Hook, Pacing, Stil, Audio, Content-Qualitaet)
- Eigene Liste pro Model — alle Analysen werden gespeichert
- Pattern-System: Speichere was bei jedem Model funktioniert, der Bot prueft automatisch ob es im Video genutzt wird
- Team-Notizen: Marketing kann beim Video eigene Punkte mitschicken
- Alles ueber Telegram — kein Login, keine App, einfach Video schicken

---

## Setup in 5 Minuten

### 1. Telegram Bot erstellen

1. Oeffne Telegram und suche @BotFather
2. Schreib /newbot
3. Gib dem Bot einen Namen (z.B. "Content Analyzer")
4. Gib ihm einen Username (z.B. content_analyzer_xyz_bot)
5. Kopiere den Token

### 2. Gemini API Key holen

1. Geh auf https://aistudio.google.com/apikey
2. Meld dich mit deinem Google-Konto an
3. Klick auf "Create API Key"
4. Kopiere den Key

### 3. Bot einrichten

    cd video-analyzer-bot
    cp .env.example .env

Oeffne .env und trag deine Keys ein:

    TELEGRAM_TOKEN=123456789:ABCdefGHI...
    GEMINI_API_KEY=AIzaSy...

### 4. Abhaengigkeiten installieren

    pip install -r requirements.txt

### 5. Bot starten

    python bot.py

---

## Befehle

    /model_neu Lisa        Model anlegen
    /models                Alle Models anzeigen
    /pattern Lisa | Text   Pattern fuer ein Model speichern
    /patterns Lisa         Alle Patterns eines Models anzeigen
    /liste Lisa            Letzte 5 Analysen eines Models anzeigen
    /hilfe                 Alle Befehle

## Video analysieren

Schick dem Bot ein Video mit Caption:

    Lisa: bitte Hook und Beleuchtung checken

Oder einfach nur den Model-Namen:

    Lisa

Der Bot:
1. Laedt das Video herunter
2. Schickt es an Gemini
3. Laed die bekannten Patterns fuer das Model
4. Analysiert Hook, Pacing, Stil, Audio, Content
5. Prueft welche Patterns genutzt wurden
6. Schlaegt fehlende Patterns vor
7. Speichert alles automatisch zur Model-Liste
8. Schickt die Analyse als Telegram-Nachricht zurueck

---

## Beispiel-Workflow

Einmalig:

    /model_neu Lisa
    /pattern Lisa | POV-Hooks funktionieren bei ihr am besten
    /pattern Lisa | Schnelle Schnitte bringen mehr Views
    /pattern Lisa | Direkte Kamera-Ansprache performt gut

Dann taeglich:

    [Video senden mit Caption: Lisa: neue Hook-Idee testen]

Der Bot analysiert und sagt z.B.:
- Hook-Staerke: 7/10
- Pattern "POV-Hook" wurde NICHT genutzt — Vorschlag: ...
- Pattern "Schnelle Schnitte" wurde genutzt
- Neuer Pattern-Vorschlag basierend auf dem Video: ...
- Gespeichert als Analyse #14 fuer Lisa

---

## Hosting (24/7 Betrieb)

### Option A: Railway (am einfachsten)
1. Geh auf railway.app
2. Neues Projekt, Dateien hochladen
3. Variables setzen: TELEGRAM_TOKEN + GEMINI_API_KEY
4. Laeuft automatisch
5. Kosten: ca. 5$/Monat

### Option B: Eigener VPS (Hetzner, DigitalOcean)

    sudo apt update && sudo apt install python3 python3-pip -y
    cd video-analyzer-bot
    pip install -r requirements.txt
    cp .env.example .env
    nano .env
    nohup python3 bot.py &

### Option C: Docker

    docker build -t video-bot .
    docker run -d --env-file .env video-bot

Wichtig: Die SQLite-Datenbank (bot_data.db) liegt im gleichen Ordner. Bei Docker ein Volume mounten damit die Daten nicht verloren gehen:

    docker run -d --env-file .env -v ./data:/app/data -e DB_PATH=/app/data/bot_data.db video-bot

---

## Limits

- Telegram: Bots koennen max. 20 MB Videos downloaden
- Gemini Free Tier: 15 Anfragen/Minute, 1500/Tag
- Gemini Pay-as-you-go: ca. 0.01-0.05$ pro Video
