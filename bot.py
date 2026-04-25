"""
Video-Analyse & Listen-Bot für OnlyFans Creator Management.

Workflow:
1. Mitarbeiter schickt: /liste ModelName + Instagram-Link + optionale Notizen
2. Bot lädt Video herunter (yt-dlp)
3. Gemini analysiert das Video nach 11 Kategorien (Traffic Light Framework)
4. Claude kombiniert Analyse + Patterns + Notizen → schreibt fertige Video-Vorgabe
5. Liste wird gespeichert und als Telegram-Nachricht zurückgeschickt
"""

import os
import asyncio
import tempfile
import logging
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import google.generativeai as genai
import anthropic
import yt_dlp

from prompts import GEMINI_ANALYSIS_PROMPT, build_claude_list_prompt

load_dotenv()

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY]):
    raise ValueError(
        "TELEGRAM_TOKEN, GEMINI_API_KEY und ANTHROPIC_API_KEY "
        "müssen in .env / Railway Variables gesetzt sein!"
    )

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
CLAUDE_MODEL = "claude-sonnet-4-6"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "bot_data.db")
TG_MAX_MESSAGE = 4096
MAX_TG_VIDEO_MB = 20


# ──────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            pattern TEXT NOT NULL,
            added_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (model_id) REFERENCES models(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            list_number INTEGER NOT NULL,
            instagram_url TEXT,
            gemini_analysis TEXT,
            final_list TEXT NOT NULL,
            notes TEXT,
            location TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (model_id) REFERENCES models(id)
        )
    """)

    conn.commit()
    conn.close()


def db_add_model(name):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO models (name, created_at) VALUES (?, ?)",
            (name.strip(), datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def db_get_model(name):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, name FROM models WHERE LOWER(name) = LOWER(?)",
        (name.strip(),)
    ).fetchone()
    conn.close()
    return row


def db_list_models():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT name FROM models ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def db_add_pattern(model_id, pattern, added_by=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO patterns (model_id, pattern, added_by, created_at) "
        "VALUES (?, ?, ?, ?)",
        (model_id, pattern.strip(), added_by, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def db_get_patterns(model_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT pattern FROM patterns WHERE model_id = ? ORDER BY created_at",
        (model_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def db_get_next_list_number(model_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MAX(list_number) FROM lists WHERE model_id = ?",
        (model_id,)
    ).fetchone()
    conn.close()
    return (row[0] or 0) + 1


def db_save_list(model_id, list_number, instagram_url, gemini_analysis,
                 final_list, notes, location, created_by):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO lists
           (model_id, list_number, instagram_url, gemini_analysis,
            final_list, notes, location, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (model_id, list_number, instagram_url, gemini_analysis,
         final_list, notes, location, created_by, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def db_get_lists(model_id, limit=5):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT list_number, final_list, instagram_url, notes,
                  created_by, created_at, location
           FROM lists WHERE model_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (model_id, limit)
    ).fetchall()
    conn.close()
    return rows


def db_count_lists(model_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*) FROM lists WHERE model_id = ?", (model_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


# ──────────────────────────────────────────────
# URL & DOWNLOAD HELPERS
# ──────────────────────────────────────────────

URL_PATTERNS = [
    r'instagram\.com/(reel|reels|p|tv)/',
    r'tiktok\.com/',
    r'youtube\.com/(shorts|watch)',
    r'youtu\.be/',
]


def is_supported_url(text):
    """Prüft ob Text einen unterstützten Video-Link enthält."""
    if not text:
        return False
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in URL_PATTERNS)


def extract_url(text):
    """Extrahiert die erste URL aus dem Text."""
    match = re.search(r'https?://\S+', text)
    return match.group(0) if match else None


def download_video(url, output_dir):
    """Lädt Video herunter mit yt-dlp. Gibt (path, error) zurück."""
    output_template = os.path.join(output_dir, "video.%(ext)s")

    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 100 * 1024 * 1024,  # 100 MB
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        for f in os.listdir(output_dir):
            if f.startswith("video."):
                return os.path.join(output_dir, f), None

        return None, "Datei nach Download nicht gefunden"
    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if "login" in msg or "private" in msg or "rate-limit" in msg:
            return None, ("Instagram blockiert den Download "
                          "(Rate-Limit oder privates Video). "
                          "Lade das Video bitte direkt als Datei hoch.")
        if "unsupported" in msg:
            return None, "Diese URL wird nicht unterstützt."
        return None, f"Download-Fehler: {str(e)[:200]}"
    except Exception as e:
        return None, f"Download-Fehler: {str(e)[:200]}"


# ──────────────────────────────────────────────
# GEMINI ANALYSE
# ──────────────────────────────────────────────

async def analyze_with_gemini(video_path):
    """Analysiert ein Video mit Gemini. Gibt (analysis, error) zurück."""
    uploaded_file = None
    try:
        uploaded_file = genai.upload_file(video_path)

        # Auf Verarbeitung warten
        max_wait_iterations = 60  # max 3 Minuten
        i = 0
        while uploaded_file.state.name == "PROCESSING" and i < max_wait_iterations:
            await asyncio.sleep(3)
            uploaded_file = genai.get_file(uploaded_file.name)
            i += 1

        if uploaded_file.state.name == "FAILED":
            return None, "Gemini konnte das Video nicht verarbeiten"
        if uploaded_file.state.name == "PROCESSING":
            return None, "Gemini braucht zu lange für die Verarbeitung"

        response = gemini_model.generate_content(
            [uploaded_file, GEMINI_ANALYSIS_PROMPT]
        )
        return response.text, None

    except Exception as e:
        logger.exception("Gemini-Fehler")
        return None, f"Gemini-Fehler: {str(e)[:200]}"
    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass


# ──────────────────────────────────────────────
# CLAUDE LIST GENERATION
# ──────────────────────────────────────────────

def generate_list_with_claude(model_name, list_number, instagram_url,
                               gemini_analysis, patterns, notes):
    """Erstellt finale Liste mit Claude. Gibt (list_text, error) zurück."""
    prompt = build_claude_list_prompt(
        model_name, list_number, instagram_url,
        gemini_analysis, patterns, notes
    )
    try:
        message = claude_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text, None
    except Exception as e:
        logger.exception("Claude-Fehler")
        return None, f"Claude-Fehler: {str(e)[:200]}"


def extract_location_from_list(list_text):
    """Extrahiert die Location aus dem Listen-Header."""
    match = re.search(r'Liste\s*-\s*\S+\s+\d+\s*-\s*(.+?)$', list_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Unbekannt"


# ──────────────────────────────────────────────
# TELEGRAM HELPERS
# ──────────────────────────────────────────────

async def send_long_message(target_msg_or_update, text):
    """Sendet eine lange Nachricht in chunks."""
    msg = target_msg_or_update
    if hasattr(target_msg_or_update, 'message'):
        msg = target_msg_or_update.message

    if len(text) <= TG_MAX_MESSAGE:
        await msg.reply_text(text)
        return

    chunks = [text[i:i+TG_MAX_MESSAGE] for i in range(0, len(text), TG_MAX_MESSAGE)]
    for chunk in chunks:
        await msg.reply_text(chunk)


# ──────────────────────────────────────────────
# COMMANDS
# ──────────────────────────────────────────────

HELP_TEXT = """🎬 *Video-Listen-Bot*

Ich verwandle Competitor-Videos in fertige Video-Vorgaben für eure Models.

━━━━━━━━━━━━━━━━━━━━
🎯 *HAUPTFUNKTION: LISTE ERSTELLEN*
━━━━━━━━━━━━━━━━━━━━

Schick mir eine Nachricht in *3 Zeilen*:

```
/liste Vivi
https://www.instagram.com/reel/xyz
Vivi sagt "Hey..." Kameramann sagt "..." Sie soll ein Handtuch tragen.
```

▫️ Zeile 1: Befehl + Model-Name
▫️ Zeile 2: Instagram-Link
▫️ Zeile 3+: deine Wünsche/Notizen (kannst du auch mit Wispr Flow einsprechen)

Ich lade das Video, analysiere es und schreibe die fertige Liste — du kopierst sie und schickst sie direkt an dein Model.

━━━━━━━━━━━━━━━━━━━━
🆘 *FALLS INSTAGRAM-DOWNLOAD NICHT KLAPPT*
━━━━━━━━━━━━━━━━━━━━

Lad das Video direkt als Datei hoch — mit Caption:

```
Vivi
Deine Notizen hier...
```

━━━━━━━━━━━━━━━━━━━━
👤 *MODEL-VERWALTUNG*
━━━━━━━━━━━━━━━━━━━━

`/model_neu Vivi` — neues Model anlegen
`/models` — alle Models anzeigen
`/pattern Vivi | Pattern-Text` — Pattern speichern
`/patterns Vivi` — Patterns eines Models anzeigen
`/liste Vivi` (ohne URL) — letzte Listen anzeigen
`/hilfe` — diese Nachricht
"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_model_neu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte einen Namen angeben:\n/model_neu Vivi"
        )
        return

    name = " ".join(context.args)
    if db_add_model(name):
        await update.message.reply_text(
            f"✅ Model \"{name}\" angelegt!\n\n"
            f"Jetzt Patterns hinzufügen mit:\n"
            f"/pattern {name} | Pattern-Beschreibung"
        )
    else:
        await update.message.reply_text(f"ℹ️ Model \"{name}\" existiert bereits.")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    models = db_list_models()
    if not models:
        await update.message.reply_text(
            "Noch keine Models angelegt.\n\n"
            "Anlegen mit: /model_neu Name"
        )
        return

    text = "📋 *Models*\n\n"
    for m in models:
        row = db_get_model(m)
        patterns = db_get_patterns(row[0])
        list_count = db_count_lists(row[0])
        text += f"• *{m}* — {len(patterns)} Patterns, {list_count} Listen\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.replace("/pattern", "", 1).strip()
    if "|" not in raw:
        await update.message.reply_text(
            "Format:\n/pattern ModelName | Pattern-Beschreibung\n\n"
            "Beispiel:\n"
            "/pattern Vivi | POV-Hooks funktionieren bei ihr am besten"
        )
        return

    parts = raw.split("|", 1)
    model_name = parts[0].strip()
    pattern_text = parts[1].strip()

    if not model_name or not pattern_text:
        await update.message.reply_text(
            "Format:\n/pattern ModelName | Pattern-Beschreibung"
        )
        return

    model_row = db_get_model(model_name)
    if not model_row:
        await update.message.reply_text(
            f"⚠️ Model \"{model_name}\" nicht gefunden.\n"
            f"Erst anlegen mit: /model_neu {model_name}"
        )
        return

    db_add_pattern(model_row[0], pattern_text, update.message.from_user.first_name)
    count = len(db_get_patterns(model_row[0]))
    await update.message.reply_text(
        f"✅ Pattern für {model_row[1]} gespeichert ({count} total)"
    )


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte Model angeben:\n/patterns Vivi"
        )
        return

    name = " ".join(context.args)
    model_row = db_get_model(name)
    if not model_row:
        await update.message.reply_text(f"Model \"{name}\" nicht gefunden.")
        return

    patterns = db_get_patterns(model_row[0])
    if not patterns:
        await update.message.reply_text(
            f"Keine Patterns für {model_row[1]}.\n\n"
            f"Hinzufügen mit:\n/pattern {model_row[1]} | Pattern-Text"
        )
        return

    text = f"📌 Patterns für {model_row[1]} ({len(patterns)}):\n\n"
    for i, p in enumerate(patterns, 1):
        text += f"{i}. {p}\n\n"

    await send_long_message(update.message, text)


async def cmd_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hauptfunktion: Liste erstellen ODER Historie anzeigen."""
    text = update.message.text.replace("/liste", "", 1).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if not lines:
        await update.message.reply_text(
            "📋 *LISTE ERSTELLEN:*\n\n"
            "```\n"
            "/liste Vivi\n"
            "https://www.instagram.com/reel/xyz\n"
            "Deine Notizen hier...\n"
            "```\n\n"
            "📋 *HISTORIE ANZEIGEN:*\n"
            "`/liste Vivi` (ohne URL/Notizen)",
            parse_mode="Markdown"
        )
        return

    model_name = lines[0]
    model_row = db_get_model(model_name)
    if not model_row:
        models = db_list_models()
        hint = ""
        if models:
            hint = "\n\nVorhandene Models:\n" + "\n".join(f"• {m}" for m in models)
        await update.message.reply_text(
            f"⚠️ Model \"{model_name}\" nicht gefunden.\n"
            f"Erst anlegen mit: /model_neu {model_name}{hint}"
        )
        return

    # URL und Notizen aus den restlichen Zeilen extrahieren
    url = None
    notes_lines = []
    for line in lines[1:]:
        if not url and is_supported_url(line):
            url = extract_url(line) or line
        else:
            notes_lines.append(line)

    notes = "\n".join(notes_lines).strip() or None

    if url:
        await create_list_from_url(update, context, model_row, url, notes)
    else:
        await show_list_history(update, context, model_row)


# ──────────────────────────────────────────────
# LISTE ERSTELLEN
# ──────────────────────────────────────────────

async def show_list_history(update, context, model_row):
    """Zeigt die letzten 5 Listen für ein Model."""
    lists = db_get_lists(model_row[0], limit=5)
    if not lists:
        await update.message.reply_text(
            f"Noch keine Listen für {model_row[1]}.\n\n"
            f"Erste Liste erstellen:\n"
            f"/liste {model_row[1]}\n"
            f"https://instagram.com/reel/...\n"
            f"Deine Notizen..."
        )
        return

    await update.message.reply_text(
        f"📋 Letzte {len(lists)} Listen für {model_row[1]}:"
    )
    for list_num, final_list, url, notes, by, created, location in lists:
        try:
            dt = datetime.fromisoformat(created).strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt = created
        header = f"━━━━━━━━━━\n📋 Liste #{list_num} — {dt}"
        if by:
            header += f" (von {by})"
        text = header + "\n\n" + final_list
        await send_long_message(update.message, text)


async def create_list_from_url(update, context, model_row, url, notes):
    """Lädt Video von URL herunter und erstellt die Liste."""
    msg = update.message
    status_msg = await msg.reply_text(
        f"⏳ Lade Video für {model_row[1]} herunter..."
    )

    tmp_dir = tempfile.mkdtemp()
    video_path = None
    try:
        video_path, error = download_video(url, tmp_dir)
        if error:
            await status_msg.edit_text(
                f"❌ {error}\n\n"
                f"💡 *Tipp:* Lade das Video direkt als Datei hoch — mit Caption:\n\n"
                f"`{model_row[1]}\n"
                f"Deine Notizen...`",
                parse_mode="Markdown"
            )
            return

        await process_video_for_list(
            status_msg, msg, model_row, video_path, url, notes
        )
    finally:
        try:
            for f in os.listdir(tmp_dir):
                os.unlink(os.path.join(tmp_dir, f))
            os.rmdir(tmp_dir)
        except Exception:
            pass


async def process_video_for_list(status_msg, original_msg, model_row,
                                   video_path, instagram_url, notes):
    """Gemeinsamer Code für Liste erstellen — egal ob URL oder Direkt-Upload."""
    # 1. Gemini Analyse
    await status_msg.edit_text(
        f"🧠 Gemini analysiert das Video für {model_row[1]}...\n"
        f"(das dauert 30-60 Sekunden)"
    )
    gemini_analysis, error = await analyze_with_gemini(video_path)
    if error:
        await status_msg.edit_text(f"❌ {error}")
        return

    # 2. Patterns laden
    patterns = db_get_patterns(model_row[0])
    list_number = db_get_next_list_number(model_row[0])

    # 3. Claude Liste schreiben
    await status_msg.edit_text(
        f"✍️ Claude schreibt Liste #{list_number} für {model_row[1]}...\n"
        f"(berücksichtigt {len(patterns)} Patterns)"
    )
    final_list, error = generate_list_with_claude(
        model_row[1], list_number, instagram_url,
        gemini_analysis, patterns, notes
    )
    if error:
        await status_msg.edit_text(f"❌ {error}")
        return

    # 4. Speichern
    location = extract_location_from_list(final_list)
    db_save_list(
        model_id=model_row[0],
        list_number=list_number,
        instagram_url=instagram_url,
        gemini_analysis=gemini_analysis,
        final_list=final_list,
        notes=notes,
        location=location,
        created_by=original_msg.from_user.first_name
    )

    # 5. Senden
    await status_msg.delete()
    await send_long_message(original_msg, final_list)
    await original_msg.reply_text(
        f"✅ Gespeichert als Liste #{list_number} für {model_row[1]}\n"
        f"📍 Location: {location}"
    )

    logger.info(
        f"Liste #{list_number} für {model_row[1]} erstellt "
        f"(von {original_msg.from_user.first_name})"
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback: Video direkt als Datei hochgeladen."""
    msg = update.message
    video = msg.video or msg.video_note or msg.document

    if msg.document and not (msg.document.mime_type or "").startswith("video/"):
        return
    if not video:
        return

    caption = (msg.caption or "").strip()
    if not caption:
        await msg.reply_text(
            "Bitte schick das Video mit Caption:\n\n"
            "ModelName\n"
            "Deine Notizen...\n\n"
            "(Erste Zeile = Model, Rest = Notizen)"
        )
        return

    lines = [l.strip() for l in caption.split("\n") if l.strip()]
    model_name = lines[0]
    notes = "\n".join(lines[1:]).strip() or None

    model_row = db_get_model(model_name)
    if not model_row:
        models = db_list_models()
        hint = ""
        if models:
            hint = "\n\nVorhandene Models:\n" + "\n".join(f"• {m}" for m in models)
        await msg.reply_text(
            f"⚠️ Model \"{model_name}\" nicht gefunden.\n"
            f"Erst anlegen mit: /model_neu {model_name}{hint}"
        )
        return

    file_size_mb = (video.file_size or 0) / (1024 * 1024)
    if file_size_mb > MAX_TG_VIDEO_MB:
        await msg.reply_text(
            f"⚠️ Video ist {file_size_mb:.0f} MB — Telegram erlaubt "
            f"max {MAX_TG_VIDEO_MB} MB. Bitte komprimieren."
        )
        return

    status_msg = await msg.reply_text(
        f"⏳ Lade Video für {model_row[1]} herunter..."
    )

    tmp_path = None
    try:
        tg_file = await video.get_file()
        suffix = ".mp4"
        if hasattr(video, "file_name") and video.file_name:
            suffix = Path(video.file_name).suffix or ".mp4"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            await tg_file.download_to_drive(tmp_path)

        await process_video_for_list(
            status_msg, msg, model_row, tmp_path, None, notes
        )
    except Exception as e:
        logger.exception("Fehler beim Video-Upload")
        await status_msg.edit_text(f"❌ Fehler: {str(e)[:200]}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wenn nur Text geschickt wird ohne Command."""
    text = update.message.text.strip()

    if is_supported_url(text):
        await update.message.reply_text(
            "Hast du das Video für eine Liste geschickt? Dann nutze:\n\n"
            "/liste ModelName\n"
            "URL\n"
            "Notizen...\n\n"
            "/hilfe für mehr Infos"
        )
    else:
        await update.message.reply_text(
            "Schreib /hilfe für alle Befehle."
        )


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("hilfe", cmd_hilfe))
    app.add_handler(CommandHandler("help", cmd_hilfe))
    app.add_handler(CommandHandler("model_neu", cmd_model_neu))
    app.add_handler(CommandHandler("models", cmd_models))
    app.add_handler(CommandHandler("pattern", cmd_pattern))
    app.add_handler(CommandHandler("patterns", cmd_patterns))
    app.add_handler(CommandHandler("liste", cmd_liste))

    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(
        filters.Document.MimeType("video/mp4") |
        filters.Document.MimeType("video/quicktime") |
        filters.Document.MimeType("video/x-msvideo") |
        filters.Document.MimeType("video/webm"),
        handle_video
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot gestartet!")
    app.run_polling()


if __name__ == "__main__":
    main()
