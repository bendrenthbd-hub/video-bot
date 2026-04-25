import os
import json
import asyncio
import tempfile
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

load_dotenv()

# --- Config ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_TOKEN und GEMINI_API_KEY müssen in .env gesetzt sein!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "bot_data.db")


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
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            analysis TEXT NOT NULL,
            team_notes TEXT,
            suggested_patterns TEXT,
            analyzed_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (model_id) REFERENCES models(id)
        )
    """)
    conn.commit()
    conn.close()


def db_add_model(name: str) -> bool:
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


def db_get_model(name: str):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, name FROM models WHERE LOWER(name) = LOWER(?)", (name.strip(),)
    ).fetchone()
    conn.close()
    return row


def db_list_models():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT name FROM models ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def db_add_pattern(model_id: int, pattern: str, added_by: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO patterns (model_id, pattern, added_by, created_at) VALUES (?, ?, ?, ?)",
        (model_id, pattern.strip(), added_by, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def db_get_patterns(model_id: int):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT pattern FROM patterns WHERE model_id = ? ORDER BY created_at", (model_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def db_save_analysis(model_id: int, analysis: str, team_notes: str,
                     suggested_patterns: str, analyzed_by: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO analyses
           (model_id, analysis, team_notes, suggested_patterns, analyzed_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (model_id, analysis, team_notes, suggested_patterns, analyzed_by,
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def db_get_analyses(model_id: int, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT analysis, team_notes, suggested_patterns, analyzed_by, created_at
           FROM analyses WHERE model_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (model_id, limit)
    ).fetchall()
    conn.close()
    return rows


# ──────────────────────────────────────────────
# ANALYSIS PROMPT BUILDER
# ──────────────────────────────────────────────

def build_prompt(model_name: str, patterns: list, team_notes: str = None) -> str:
    base = f"""Du bist ein professioneller Social-Media- und Content-Analyst.
Analysiere dieses Video fuer das Model "{model_name}".

"""
    if patterns:
        base += "BEKANNTE PATTERNS DIE BEI DIESEM MODEL FUNKTIONIEREN:\n"
        for i, p in enumerate(patterns, 1):
            base += f"  {i}. {p}\n"
        base += "\nBeruecksichtige diese Patterns in deiner Analyse! Pruefe ob das Video diese Patterns nutzt und schlage vor, wie sie besser eingesetzt werden koennten.\n\n"

    if team_notes:
        base += f"NOTIZEN VOM MARKETING-TEAM:\n{team_notes}\n"
        base += "Geh in deiner Analyse auch auf diese Punkte ein!\n\n"

    base += """Gib eine strukturierte Analyse:

1. HOOK-ANALYSE (erste 3 Sekunden)
- Art des Hooks (Pattern Interrupt, Frage, Statement, visuell, etc.)
- Staerke des Hooks (1-10)
- Was genau macht den Hook stark/schwach?

2. PACING & STRUKTUR
- Schnittfrequenz (schnell/mittel/langsam)
- Spannungsbogen vorhanden? (Ja/Nein + Beschreibung)
- Retention-Killer identifiziert? (Stellen wo Zuschauer abspringen wuerden)

3. VISUELLER STIL
- Farbgebung & Grading
- Kamerafuehrung (statisch, Bewegung, POV, etc.)
- Text-Overlays & Grafiken
- Gesamtaesthetik (1-10)

4. AUDIO & VOICEOVER
- Musikeinsatz
- Voiceover-Qualitaet & Tonalitaet
- Sound-Design / Sound-Effekte

5. CONTENT-QUALITAET
- Kernbotschaft klar? (Ja/Nein)
- Mehrwert fuer Zuschauer (1-10)
- Call-to-Action vorhanden? (Ja/Nein + Art)
- Authentizitaet (1-10)

"""
    if patterns:
        base += """6. PATTERN-CHECK
- Welche der bekannten Patterns wurden genutzt?
- Welche Patterns fehlen und sollten eingebaut werden?
- Neue Pattern-Vorschlaege basierend auf diesem Video?

"""

    base += """GESAMT-BEWERTUNG
- Gesamtscore (1-10)
- Top 3 Staerken
- Top 3 Verbesserungsvorschlaege
- Geschaetzte Performance-Prognose (viral potential: niedrig/mittel/hoch)

Antworte auf Deutsch. Sei direkt und ehrlich. Nutze Emojis fuer Uebersichtlichkeit."""

    return base


# ──────────────────────────────────────────────
# TELEGRAM HANDLERS
# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! Ich bin der Video-Analyse-Bot.\n\n"
        "So funktioniert's:\n\n"
        "1. Model anlegen:\n"
        "   /model_neu Lisa\n\n"
        "2. Patterns speichern:\n"
        "   /pattern Lisa | POV-Hooks funktionieren am besten\n"
        "   /pattern Lisa | Schnelle Schnitte performen bei ihr\n\n"
        "3. Video analysieren:\n"
        "   Schick ein Video mit Caption:\n"
        "   Lisa: bitte Beleuchtung checken\n"
        "   (oder nur: Lisa)\n\n"
        "4. Liste abrufen:\n"
        "   /liste Lisa\n\n"
        "Weitere Befehle:\n"
        "   /models - alle Models anzeigen\n"
        "   /patterns Lisa - Patterns anzeigen\n"
        "   /hilfe - diese Nachricht"
    )


async def cmd_hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def cmd_model_neu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bitte gib einen Namen an:\n/model_neu Lisa")
        return

    name = " ".join(context.args)
    if db_add_model(name):
        await update.message.reply_text(f"Model \"{name}\" angelegt!")
    else:
        await update.message.reply_text(f"Model \"{name}\" existiert bereits.")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    models = db_list_models()
    if not models:
        await update.message.reply_text("Noch keine Models angelegt.\nNutze /model_neu Name")
        return
    text = "Deine Models:\n\n"
    for m in models:
        row = db_get_model(m)
        patterns = db_get_patterns(row[0])
        analyses = db_get_analyses(row[0], limit=1000)
        text += f"- {m} ({len(patterns)} Patterns, {len(analyses)} Analysen)\n"
    await update.message.reply_text(text)


async def cmd_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.replace("/pattern", "").strip()
    if "|" not in raw:
        await update.message.reply_text(
            "Format:\n/pattern ModelName | Das Pattern hier\n\n"
            "Beispiel:\n/pattern Lisa | POV-Hooks funktionieren bei ihr am besten"
        )
        return

    parts = raw.split("|", 1)
    model_name = parts[0].strip()
    pattern_text = parts[1].strip()

    model_row = db_get_model(model_name)
    if not model_row:
        await update.message.reply_text(
            f"Model \"{model_name}\" nicht gefunden.\n"
            f"Erst anlegen mit /model_neu {model_name}"
        )
        return

    db_add_pattern(model_row[0], pattern_text, update.message.from_user.first_name)
    count = len(db_get_patterns(model_row[0]))
    await update.message.reply_text(
        f"Pattern fuer {model_row[1]} gespeichert! ({count} Patterns total)\n\n"
        f"\"{pattern_text}\""
    )


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bitte gib einen Namen an:\n/patterns Lisa")
        return

    name = " ".join(context.args)
    model_row = db_get_model(name)
    if not model_row:
        await update.message.reply_text(f"Model \"{name}\" nicht gefunden.")
        return

    patterns = db_get_patterns(model_row[0])
    if not patterns:
        await update.message.reply_text(
            f"Noch keine Patterns fuer {model_row[1]}.\n"
            f"Hinzufuegen mit:\n/pattern {model_row[1]} | Dein Pattern hier"
        )
        return

    text = f"Patterns fuer {model_row[1]}:\n\n"
    for i, p in enumerate(patterns, 1):
        text += f"{i}. {p}\n"
    await update.message.reply_text(text)


async def cmd_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bitte gib einen Namen an:\n/liste Lisa")
        return

    name = " ".join(context.args)
    model_row = db_get_model(name)
    if not model_row:
        await update.message.reply_text(f"Model \"{name}\" nicht gefunden.")
        return

    analyses = db_get_analyses(model_row[0], limit=5)
    if not analyses:
        await update.message.reply_text(
            f"Noch keine Analysen fuer {model_row[1]}.\n"
            "Schick ein Video mit Caption:\n"
            f"{model_row[1]}: optional deine Notizen"
        )
        return

    await update.message.reply_text(
        f"Letzte {len(analyses)} Analysen fuer {model_row[1]}:\n"
        "─" * 20
    )

    for i, (analysis, notes, patterns, by, date) in enumerate(analyses):
        dt = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
        header = f"Analyse #{len(analyses)-i} - {dt}"
        if by:
            header += f" (von {by})"
        header += "\n"
        if notes:
            header += f"Team-Notizen: {notes}\n"
        header += "─" * 20 + "\n"

        full_text = header + analysis

        if len(full_text) <= 4096:
            await update.message.reply_text(full_text)
        else:
            chunks = [full_text[j:j+4096] for j in range(0, len(full_text), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk)


def parse_caption(caption: str):
    """Parst 'ModelName: optionale notizen' oder nur 'ModelName'."""
    if not caption:
        return None, None

    caption = caption.strip()
    if ":" in caption:
        parts = caption.split(":", 1)
        return parts[0].strip(), parts[1].strip() or None
    return caption.strip(), None


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video empfangen, Model zuordnen, Gemini analysieren, speichern."""
    msg = update.message
    video = msg.video or msg.video_note or msg.document

    if msg.document and not (msg.document.mime_type or "").startswith("video/"):
        return

    if not video:
        return

    # Caption parsen
    model_name, team_notes = parse_caption(msg.caption)

    if not model_name:
        await msg.reply_text(
            "Bitte schick das Video mit einer Caption:\n\n"
            "ModelName: optionale Notizen\n\n"
            "Beispiel:\n"
            "Lisa: bitte Hook und Beleuchtung checken\n\n"
            "Oder einfach nur:\n"
            "Lisa"
        )
        return

    model_row = db_get_model(model_name)
    if not model_row:
        models = db_list_models()
        hint = ""
        if models:
            hint = "\n\nVorhandene Models:\n" + "\n".join(f"- {m}" for m in models)
        await msg.reply_text(
            f"Model \"{model_name}\" nicht gefunden.\n"
            f"Erst anlegen mit /model_neu {model_name}{hint}"
        )
        return

    # Groessen-Check
    file_size_mb = (video.file_size or 0) / (1024 * 1024)
    if file_size_mb > 20:
        await msg.reply_text(
            f"Video ist {file_size_mb:.0f} MB - Telegram erlaubt max. 20 MB fuer Bots.\n"
            "Bitte komprimiere das Video oder schick eine kuerzere Version."
        )
        return

    status_msg = await msg.reply_text(f"Video fuer {model_row[1]} wird heruntergeladen...")

    try:
        # 1) Download von Telegram
        tg_file = await video.get_file()
        file_name = getattr(video, "file_name", None)
        suffix = Path(file_name).suffix if file_name else ".mp4"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            await tg_file.download_to_drive(tmp_path)

        # 2) Upload zu Gemini
        await status_msg.edit_text("Video wird an Gemini gesendet...")
        uploaded_file = genai.upload_file(tmp_path, mime_type=video.mime_type or "video/mp4")

        # 3) Warten auf Verarbeitung
        await status_msg.edit_text("Gemini verarbeitet das Video...")
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(3)
            uploaded_file = genai.get_file(uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            await status_msg.edit_text("Gemini konnte das Video nicht verarbeiten.")
            return

        # 4) Patterns laden & Prompt bauen
        patterns = db_get_patterns(model_row[0])
        prompt = build_prompt(model_row[1], patterns, team_notes)

        await status_msg.edit_text(
            f"Video fuer {model_row[1]} wird analysiert...\n"
            f"{len(patterns)} Patterns werden beruecksichtigt"
        )

        response = model.generate_content([uploaded_file, prompt])
        analysis = response.text

        # 5) In DB speichern
        pattern_info = None
        if patterns:
            pattern_info = json.dumps(patterns, ensure_ascii=False)

        db_save_analysis(
            model_id=model_row[0],
            analysis=analysis,
            team_notes=team_notes,
            suggested_patterns=pattern_info,
            analyzed_by=msg.from_user.first_name
        )

        # 6) Ergebnis senden
        await status_msg.delete()

        header = f"Analyse fuer {model_row[1]}\n"
        if team_notes:
            header += f"Team-Notizen: {team_notes}\n"
        header += "─" * 20 + "\n\n"

        full_text = header + analysis
        total_analyses = len(db_get_analyses(model_row[0], limit=1000))
        footer = f"\n\n─────\nGespeichert als Analyse #{total_analyses} fuer {model_row[1]}"

        full_text += footer

        if len(full_text) <= 4096:
            await msg.reply_text(full_text)
        else:
            chunks = [full_text[j:j+4096] for j in range(0, len(full_text), 4096)]
            for chunk in chunks:
                await msg.reply_text(chunk)

        # Cleanup bei Gemini
        genai.delete_file(uploaded_file.name)
        logger.info(f"Analyse #{total_analyses} fuer {model_row[1]} von {msg.from_user.first_name}")

    except Exception as e:
        logger.error(f"Fehler: {e}")
        await status_msg.edit_text(f"Fehler:\n{str(e)[:500]}")

    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Schick mir ein Video mit Caption um es zu analysieren:\n"
        "ModelName: optionale Notizen\n\n"
        "/hilfe zeigt alle Befehle"
    )


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hilfe", cmd_hilfe))
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    logger.info("Bot gestartet!")
    app.run_polling()


if __name__ == "__main__":
    main()
