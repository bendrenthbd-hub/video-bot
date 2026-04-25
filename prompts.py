"""
Prompts für Gemini (Video-Analyse) und Claude (Listenerstellung).
Hier können die Prompts angepasst werden ohne den Hauptcode zu ändern.
"""


GEMINI_ANALYSIS_PROMPT = """Du bist ein Expert Content Analyst für OnlyFans Creator Social Media Growth.

Analysiere dieses Video EXAKT und DETAILLIERT nach dem Traffic Light Framework. Sei präzise und konkret — vage Aussagen sind nutzlos. Antworte auf Deutsch.

RATING SCALE:
🟢 GRÜN (9-10/10) | 🟡 GELB (6-8/10) | 🔴 ROT (0-5/10)

═══════════════════════════════════════
KATEGORIE 1: HOOK & ERSTE 2 SEKUNDEN
═══════════════════════════════════════
- Was passiert exakt 0:00-0:02?
- Text-Overlay vorhanden? Welcher exakter Text?
- Energy-Level: Niedrig / Mittel / Hoch
- Scroll-Stopper: Ja/Nein + warum?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 2: WATCHTIME & PACING
═══════════════════════════════════════
- Deadtime vorhanden? Bei welcher Sekunde?
- Pacing: Konstant / Beschleunigend / Langsam
- Wann würde der Zuschauer abspringen?
- Grund weiterzuschauen nach Sek 3? Ja/Nein + warum
- Video-Länge angemessen?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 3: BELEUCHTUNG
═══════════════════════════════════════
- Lichttyp: Natürlich / Künstlich / Gemischt
- Qualität: Professionell / Amateur / Schlecht
- Gesicht klar sichtbar?
- Konsistent durchs Video?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 4: HINTERGRUND & SETTING
═══════════════════════════════════════
- Location (genau beschreiben):
- Hintergrundtiefe: Flach / Hat Tiefe / Unscharf
- Visuelle Unordnung: Sauber / Beschäftigt / Unaufgeräumt
- Trägt zum Video bei?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 5: OUTFIT & KÖRPERPRÄSENTATION
═══════════════════════════════════════
- Outfit-Stil (genau beschreiben):
- Sichtbare Haut: Wenig / Mittel / Viel
- Brust-Präsentation: Dekolleté? Push-up? Winkel optimiert?
- Schmeichelhaft für Körpertyp?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 6: KAMERA & WINKEL
═══════════════════════════════════════
- Hauptwinkel: Augenhöhe / Von unten / Von oben / Seitlich
- Bewegung: Statisch / Handheld / Pan / Zoom
- Bildausschnitt: Ganzkörper / Oberkörper / Close-up / Unterkörper
- Schmeichelhaft?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 7: BEWEGUNG & ENERGIE
═══════════════════════════════════════
- Bewegungstyp:
- Energy-Level: 1-10
- Wirkt: Natürlich / Forciert / Steif / Übersexualisiert / Genau richtig
- Gesichtsausdruck: Engagiert / Neutral / Lächelnd / Ernst / Verspielt
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 8: SEXUAL SWEET SPOT (8FAA Rule)
═══════════════════════════════════════
Zähle vorhandene Faktoren:
1. Suggestives Outfit
2. Suggestive Bewegung
3. Suggestiver Text
4. Suggestives Setting
5. Suggestiver Kamerawinkel
6. Suggestiver Gesichtsausdruck

Anzahl Faktoren: [X]
Welche: [...]
Sweet Spot: Zu safe (0-1) / Optimal (2-3) / Spicy (4-5) / Zu viel (6+)
Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 9: TEXT-OVERLAY & HOOK COPY
═══════════════════════════════════════
- Text vorhanden? Exakter Text:
- Stil: Bold / Frage / Relatable / POV / Story
- Position:
- Lesbar?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 10: VISUELLE QUALITÄT
═══════════════════════════════════════
- Auflösung: Hoch / Mittel / Niedrig
- Schärfe:
- Color Grading: Warm / Kühl / Neutral / Übersättigt
- Professionell?
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
KATEGORIE 11: PATTERN MATCH
═══════════════════════════════════════
- Core Pattern: POV / Relatable / Thirst Trap / Trend / Dance / Andere
- Was macht es viral? Der eine Trigger:
- Rating: 🟢/🟡/🔴

═══════════════════════════════════════
GESAMT-VERDICT
═══════════════════════════════════════
🟢 GRÜN: [X] | 🟡 GELB: [X] | 🔴 ROT: [X]

TOP 3 STÄRKEN DES VIDEOS (was es viral macht):
1. [...]
2. [...]
3. [...]

ZUSAMMENFASSUNG IN EINEM SATZ:
Was dieses Video erfolgreich macht: [...]

═══════════════════════════════════════
ÜBERTRAGBARKEIT (sehr wichtig!)
═══════════════════════════════════════
Was muss EXAKT übernommen werden, damit das Video bei einem anderen Model genauso funktioniert?

- Konkrete Hook-Bewegung (was macht sie in den ersten 2 Sek):
- Outfit-Beschreibung (was trägt sie):
- Hintergrund/Location (wo wird gefilmt):
- Kamerawinkel (wie wird gefilmt):
- Text-Overlay (welcher Text steht im Video, falls vorhanden):
- Pacing (Schnittfrequenz, Tempo):
- Tonalität/Stimmung (Vibe des Videos):
- Was sie genau sagt/macht (Schritt für Schritt):
"""


def build_claude_list_prompt(model_name, list_number, instagram_url, gemini_analysis, patterns, notes):
    """Baut den Prompt für Claude um die finale Liste zu erstellen."""

    pattern_section = ""
    if patterns:
        pattern_text = "\n".join(f"- {p}" for p in patterns)
        pattern_section = f"""
═══════════════════════════════════════
PATTERNS DIE BEI {model_name.upper()} FUNKTIONIEREN
═══════════════════════════════════════
Diese Patterns MUSST du beim Schreiben der Liste berücksichtigen — sie sind die Erfolgsformel von {model_name}. Wenn das Original-Video etwas zeigt was zu {model_name}s Patterns NICHT passt, passe es an die Patterns an. Wenn etwas zu den Patterns passt, übernimm es:

{pattern_text}
"""

    notes_section = ""
    if notes:
        notes_section = f"""
═══════════════════════════════════════
NOTIZEN VOM MARKETING-MITARBEITER (höchste Priorität!)
═══════════════════════════════════════
Der Mitarbeiter hat folgende konkrete Wünsche eingesprochen. Das ist die WICHTIGSTE Eingabe — befolge das exakt, auch wenn es vom Original abweicht. Wenn er einen Dialog vorgibt, nutze EXAKT diesen Dialog. Wenn er Outfit/Location/Kamera vorgibt, nutze EXAKT seine Vorgaben:

{notes}
"""

    url_line = instagram_url if instagram_url else "[Video als Datei hochgeladen]"

    return f"""Du bist ein professioneller Content-Stratege für OnlyFans Creator Marketing. Du erhältst die Analyse eines viralen Competitor-Videos und schreibst daraus eine konkrete, sofort umsetzbare Video-Vorgabe für unsere eigene Creatorin {model_name}.

═══════════════════════════════════════
ORIGINAL-VIDEO ANALYSE (vom Competitor)
═══════════════════════════════════════

{gemini_analysis}
{pattern_section}{notes_section}
═══════════════════════════════════════
DEINE AUFGABE
═══════════════════════════════════════

Schreibe eine fertige Video-Vorgabe für {model_name} im EXAKT folgenden Format. Halte dich GENAU an dieses Format — keine Abweichungen, keine zusätzlichen Sektionen, keine fehlenden Sektionen, keine Einleitung oder Schlusstext. Diese Liste wird DIREKT an die Creatorin weitergeleitet:

Liste - {model_name} {list_number} - [LOCATION HIER EINFÜGEN — z.B. "Zuhause", "Küche", "Schlafzimmer", "Outdoor"]
🎥Beispiel
{url_line}
🎵Sound
-
👚Outfit
[Konkrete Outfit-Beschreibung in 1-2 Sätzen. Was genau soll sie tragen? Beziehe dich auf das was im Original-Video gut funktioniert hat, aber passe es an {model_name}s Patterns an. Falls die Notizen ein spezifisches Outfit nennen, nutze EXAKT das.]
🏡Hintergrund
[Konkrete Location/Hintergrund-Beschreibung in 1-2 Sätzen. Wo soll sie filmen?]
🎬Video
[Konkrete Schritt-für-Schritt Anweisungen wie sie das Video drehen soll. Beschreibe Kamerawinkel, Bewegungen, Timing, Hook in der ersten Sekunde. Sei so konkret dass die Creatorin das Video exakt so drehen kann ohne weitere Fragen. Nutze die Übertragbarkeits-Sektion aus der Analyse als Basis. Berücksichtige unbedingt die Patterns von {model_name}. 4-8 Sätze.]
📝 Text zum Sprechen
[Der genaue Dialog. Wenn der Mitarbeiter in den Notizen Text vorgegeben hat, nutze EXAKT diesen. Falls nicht, schreibe einen passenden Dialog basierend auf dem Original und den Patterns. Markiere klar wer wann spricht (z.B. "(Kamera noch im Stativ)" oder durch Zeilenumbrüche). Bau Regie-Anweisungen in Klammern ein wo sinnvoll, z.B. "(nach unten zeigen und kurz Wortpause machen)". Nutze deutsche Anführungszeichen „…".]
✏️ Caption
[Eine konkrete Caption-Vorschlag für den Instagram-Post. Maximal 1-2 Sätze. Sollte zu {model_name}s Patterns passen und Engagement triggern (Frage stellen, kontroverse Aussage etc).]

═══════════════════════════════════════
WICHTIGE REGELN (zwingend befolgen!)
═══════════════════════════════════════
1. Beginne deine Antwort DIREKT mit "Liste - {model_name} {list_number} - ..." — keine Einleitung.
2. Beende deine Antwort mit der Caption — kein Schlusstext, keine Erklärung danach.
3. Die Sektionen müssen GENAU diese Emojis und Reihenfolge haben: 🎥 → 🎵 → 👚 → 🏡 → 🎬 → 📝 → ✏️
4. Jede Sektion muss konkret und umsetzbar sein. Vage Aussagen wie "etwas Sexy tragen" sind verboten — schreib konkret was sie tragen soll.
5. Wenn die Mitarbeiter-Notizen einem Pattern widersprechen, folge IMMER den Notizen — der Mitarbeiter weiß was er will.
6. Schreibe in der Du-Form, sprich {model_name} direkt an.
7. Sound-Sektion ist IMMER nur "-". Niemals einen Sound vorschlagen — den fügt der Mitarbeiter im Editing hinzu.
8. Listen-Header MUSS exakt sein: "Liste - {model_name} {list_number} - [Location]" mit Bindestrichen und Leerzeichen wie hier gezeigt.
9. Wenn Original-Video einen Dialog hatte und der Mitarbeiter keinen vorgegeben hat: schreibe einen passenden Dialog, denk dabei an {model_name}s Vibe und Patterns."""
