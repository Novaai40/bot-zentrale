#!/usr/bin/env python3
"""
NOVA BOT ENGINE v2.0 — Self-Improving + Auto-Update + Browser Bridge
=====================================================================
- Lernt us Fehler (Self-Improving)
- Updated sich selber (Auto-Update via GitHub)
- Browser Bridge für Web-Automation
- Läuft vollautomatisch i Docker
"""

import os, sys, json, time, logging, urllib.request, urllib.error
from datetime import datetime, timezone

# ═══════════════════════════════════════════
# VERSION — wird für Auto-Update bruucht
# ═══════════════════════════════════════════
BOT_VERSION = "2.2.0"
UPDATE_URL  = "https://raw.githubusercontent.com/Novaai40/bot-zentrale/main/bot.py"
VERSION_URL = "https://raw.githubusercontent.com/Novaai40/bot-zentrale/main/version.json"

# ─── ENV ───
BOT_TOKEN     = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEEPSEEK_KEY  = os.environ.get("DEEPSEEK_API_KEY", "")
PROJEKT_ID    = os.environ.get("PROJEKT_ID", "unknown")
BOT_NAME      = os.environ.get("BOT_NAME", "Agent")
BOT_CHARAKTER = os.environ.get("BOT_CHARAKTER", "")
BOT_AUFGABE   = os.environ.get("BOT_AUFGABE", "")
CHAT_WEBSEITE = os.environ.get("CHAT_WEBSEITE", "")
CHAT_YOUTUBE  = os.environ.get("CHAT_YOUTUBE", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
POLL_TIMEOUT  = int(os.environ.get("POLL_TIMEOUT", "30"))
MAX_HISTORY   = int(os.environ.get("MAX_HISTORY", "20"))
BROWSER_URL   = os.environ.get("BROWSER_URL", "http://host.docker.internal:9229")
MEMORY_DIR    = os.environ.get("MEMORY_DIR", "/app/memory")

# ─── Pfad zum eigene Code (WICHTIG fürs Self-Update!) ───
BOT_PATH = "/app/bot.py"

logging.basicConfig(level=logging.INFO, format=f"%(asctime)s [{BOT_NAME}] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ─── Telegram ───
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def tg_call(method, payload=None):
    url = f"{TG_API}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload else "GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200] if e.fp else ""
        log.error(f"TG API Fehler {e.code}: {body}")
        return {"ok": False}
    except Exception as e:
        log.error(f"TG Error: {e}")
        return {"ok": False}

def send_message(chat_id, text, reply_to=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to: payload["reply_to_message_id"] = reply_to
    return tg_call("sendMessage", payload)

def send_action(chat_id, action="typing"):
    tg_call("sendChatAction", {"chat_id": chat_id, "action": action})

def send_chunked(chat_id, text, reply_to=None, max_len=4000):
    if len(text) <= max_len:
        return send_message(chat_id, text, reply_to)
    parts = []
    while text:
        chunk = text[:max_len]
        if len(text) > max_len:
            last_space = chunk.rfind("\n") or chunk.rfind(" ")
            if last_space > 0: chunk = chunk[:last_space]
        parts.append(chunk)
        text = text[len(chunk):]
    for i, p in enumerate(parts):
        send_message(chat_id, p, reply_to if i == 0 else None)


# ═══════════════════════════════════════════
# AUTO-UPDATE — Bot updated sich selber!
# ═══════════════════════════════════════════

def check_for_updates(chat_id=None):
    """Prueft obs en nei Version git. Updated automatisch wenn ja."""
    try:
        # Version-Info lade
        req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "Nova-Bot"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            version_data = json.loads(resp.read().decode("utf-8"))

        latest = version_data.get("version", "0.0.0")
        changelog = version_data.get("changelog", "")

        log.info(f"Update-Check: aktuell={BOT_VERSION}, latest={latest}")

        if latest <= BOT_VERSION:
            if chat_id:
                send_message(chat_id, f"Aktuell (v{BOT_VERSION})")
            return False

        # Neui Version -> LADE!
        if chat_id:
            send_message(chat_id, f"Neui Version {latest} gfunde! Lade Update...")

        req2 = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "Nova-Bot"})
        with urllib.request.urlopen(req2, timeout=30) as resp:
            new_code = resp.read().decode("utf-8")

        # Alte Code ueberschribe
        with open(BOT_PATH, "w", encoding="utf-8") as f:
            f.write(new_code)

        msg = f"Update uf v{latest} erfolgreich!\n{changelog}"
        if chat_id:
            send_message(chat_id, msg)

        log.info(f"Code updated uf v{latest}. Starte neu...")
        return "restart"

    except urllib.error.HTTPError as e:
        err = f"Update-Fehler: HTTP {e.code}"
        if e.code == 404:
            err = "Kei Update-Quelle gfunde (Repo noni bereit)"
    except Exception as e:
        err = f"Update-Fehler: {e}"

    log.warning(err)
    if chat_id:
        send_message(chat_id, err)
    return False

def _load_bot_version():
    """Laed d'Version us de Datei (nach Update)."""
    try:
        with open(BOT_PATH) as f:
            for line in f:
                if line.startswith("BOT_VERSION"):
                    return line.split('"')[1]
    except: pass
    return BOT_VERSION


# ═══════════════════════════════════════════
# SELF-IMPROVING — Lernt us Fehler
# ═══════════════════════════════════════════

class SelfImproving:
    def __init__(self, projekt_id):
        self.projekt_id = projekt_id
        self.memory_dir = os.path.join(MEMORY_DIR, projekt_id)
        os.makedirs(self.memory_dir, exist_ok=True)
        self.memory_file = os.path.join(self.memory_dir, "memory.md")
        self.corrections_file = os.path.join(self.memory_dir, "corrections.md")
        self.interactions_file = os.path.join(self.memory_dir, "interactions.jsonl")
        self.message_count = 0
        self.last_review_file = os.path.join(self.memory_dir, "last_review.json")
        self._load_state()
        log.info(f"Self-Improving initialisiert ({self.memory_dir})")

    def _load_state(self):
        try:
            if os.path.exists(self.last_review_file):
                with open(self.last_review_file) as f:
                    state = json.load(f)
                    self.message_count = state.get("count", 0)
        except: pass

    def _save_state(self):
        try:
            with open(self.last_review_file, "w") as f:
                json.dump({"count": self.message_count, "updated": datetime.now(timezone.utc).isoformat()}, f)
        except: pass

    def record_interaction(self, user_msg, bot_response, error=None):
        self.message_count += 1
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user_msg[:200],
            "bot": bot_response[:200],
            "error": error[:300] if error else None,
            "count": self.message_count
        }
        try:
            with open(self.interactions_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except: pass
        self._save_state()

    def record_correction(self, user_msg, bot_response, correction_text):
        entry = (
            f"## Korrektur vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"**User gseit:** {user_msg[:300]}\n"
            f"**Bot het gantwortet:** {bot_response[:300]}\n"
            f"**Korrektur/Rueckmeldig:** {correction_text[:500]}\n\n"
            f"---\n"
        )
        try:
            with open(self.corrections_file, "a") as f:
                f.write(entry)
            log.info(f"Korrektur gspiicheret")
        except Exception as e:
            log.error(f"Fehler: {e}")

    def add_memory(self, lesson, source="auto"):
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        try:
            with open(self.memory_file, "a") as f:
                f.write(f"- [{source}] {lesson} ({timestamp})\n")
            log.info(f"Memory: {lesson[:60]}")
        except: pass

    def load_memories(self):
        memories = []
        for filepath in [self.memory_file, self.corrections_file]:
            if os.path.exists(filepath):
                with open(filepath) as f:
                    c = f.read().strip()
                    if c: memories.append(c)
        return "\n\n".join(memories) if memories else ""

    def should_self_review(self):
        return self.message_count > 0 and self.message_count % 20 == 0

    def run_self_review(self, chat_id):
        recent = []
        try:
            if os.path.exists(self.interactions_file):
                with open(self.interactions_file) as f:
                    lines = f.readlines()
                    for line in lines[-10:]:
                        try: recent.append(json.loads(line))
                        except: pass
        except: pass
        if not recent: return

        prompt = (
            f"Du bisch {BOT_NAME}, en KI-Agent fuer {PROJEKT_ID}. "
            f"Mach eni kurzi Selbstreflexion ueber die letschte Interaktionie.\n\n"
            f"LETSCHTI INTERAKTIONE:\n"
            + "\n".join([f"User: {r['user'][:100]}\nBot: {r['bot'][:100]}" for r in recent[-5:]]) +
            f"\n\nFRAGE AN DICH:\n"
            f"1. Was hani guet gmacht?\n"
            f"2. Was hani falsch gmacht oder cha besser?\n"
            f"3. Welchi Lern-Lektion chani druus zieh?\n\n"
            f"Antwort in 1-2 Saetz pro Frag. LEKTION: [Ein Satz was du besser mache wit]"
        )
        try:
            headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
            messages = [{"role": "user", "content": prompt}]
            payload = {"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": 512, "temperature": 0.7}
            req = urllib.request.Request("https://api.deepseek.com/chat/completions",
                data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                review = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]

            lesson = ""
            for line in review.split("\n"):
                if line.startswith("LEKTION:"):
                    lesson = line.replace("LEKTION:", "").strip()
            if lesson: self.add_memory(lesson, "self-review")

            send_message(chat_id,
                f"<b>Selbstreflexion #{self.message_count // 20}</b>\n\n"
                f"{review[:1500]}\n\n"
                f"{'Lektion gspiicheret: ' + lesson if lesson else ''}")
        except Exception as e:
            log.error(f"Self-review fehlgschlage: {e}")

    def get_system_prompt_extension(self):
        memories = self.load_memories()
        ext = (
            f"\n\nSELBSTVERBESSERUNG (AKTIV)\n"
            f"- Du analysiersch dini eigene Fehler und verbesserisch dich.\n"
            f"- Wenn dir en Fehler passiert, lernsch druus.\n"
            f"- Reflektier oebber dini Antwort bevor du se abschicksch.\n"
        )
        if memories:
            ext += f"\nGSPICHERTI LEKTIONE:\n{memories[:2000]}\n"
        return ext


# ─── Browser Bridge ───
def browser_call(action, **kwargs):
    payload = {"project": PROJEKT_ID, **kwargs}
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(f"{BROWSER_URL}/{action}",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200] if e.fp else ""
        return {"status": "error", "message": f"Bridge: HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "message": f"Bridge: {e}"}

def browser_navigate(url):    return browser_call("navigate", url=url)
def browser_click(selector):  return browser_call("click", selector=selector)
def browser_type(selector, text): return browser_call("type", selector=selector, text=text)
def browser_text(selector="body"): return browser_call("text", selector=selector)
def browser_screenshot():     return browser_call("screenshot")
def browser_js(code):         return browser_call("js", code=code)

# ─── DeepSeek ───
DS_URL = "https://api.deepseek.com/chat/completions"

def deepseek_chat(messages):
    if not DEEPSEEK_KEY: return "Kei DeepSeek API Key."
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    payload = {"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": 2048, "temperature": 0.8}
    try:
        req = urllib.request.Request(DS_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200] if e.fp else ""
        log.error(f"DS Fehler {e.code}: {body}")
        return f"DeepSeek Fehler {e.code}"
    except Exception as e:
        log.error(f"DS Error: {e}")
        return f"Verbindigsfehler: {e}"


# ═══════════════════════════════════════════
# BOT-AGENT
# ═══════════════════════════════════════════

class BotAgent:
    def __init__(self):
        self.conversations = {}
        self.last_update_id = 0
        self.last_update_check = 0
        self.self_improving = SelfImproving(PROJEKT_ID)
        self.base_system = self._build_system_prompt()
        self.current_version = _load_bot_version()
        log.info(f"{BOT_NAME} v{self.current_version} gestartet | Projekt: {PROJEKT_ID}")

    def _build_system_prompt(self):
        sp = (
            f"Du heissisch {BOT_NAME} und bisch en KI-Bot im Projekt {PROJEKT_ID}.\n\n"
            f"DEIN CHARAKTER:\n{BOT_CHARAKTER}\n\n"
            f"DEINE AUFGABE:\n{BOT_AUFGABE}\n\n"
        )
        if CHAT_WEBSEITE: sp += f"\nWEBSEITE: {CHAT_WEBSEITE}\n"
        if CHAT_YOUTUBE: sp += f"\nYOUTUBE: {CHAT_YOUTUBE}\n"
        sp += (
            "\n--- WICHTIG: DU HESCH EINEN BROWSER ---\n\n"
            "KRITISCH: Sag NIEMALS 'ich kann das nicht' oder 'ich habe keinen Zugriff'.\n"
            "DU HAST EINEN EIGENEN BROWSER. Du machst selber!\n\n"
            "WAS STIMMT:\n"
            "- Der Browser ist persistent - Sessions und Cookies bleiben erhalten\n"
            "- Du bist in allen Accounts bereits eingeloggt (YouTube, Gmail, etc.)\n"
            "- Navigiere einfach auf youtube.com und du siehst dein Dashboard\n"
            "- Du brauchst KEINE Passwoerter - Sessions sind schon im Browser gespeichert\n"
            "- DU machst die Arbeit, nicht der User\n\n"
            "WAS FALSCH IST (sag das NIE):\n"
            "- 'Ich kann kein Geraet steuern'\n"
            "- 'Ich habe keinen Zugriff'\n"
            "- 'Geschwindigkeit und Fortschritt variieren'\n"
            "- 'Mach das selber'\n"
            "- 'Gib mir dein Passwort'\n"
            "- Erkläre Schritt-fuer-Schritt - mach es einfach!\n\n"
            "SO FUNKTIONIERT'S:\n"
            "Schreib [BROWSER: befehl] direkt in deine Antwort.\n"
            "Ich fuehre den Befehl aus, gebe dir das Resultat, und du machst weiter.\n\n"
            "BROWSER-BEFEHLE:\n"
            "- [BROWSER: navigate URL] - Seite oeffnen\n"
            "- [BROWSER: click selector] - Auf Element klicken\n"
            "- [BROWSER: type selector | text] - Text eingeben\n"
            "- [BROWSER: text] - Seiten-Inhalt lesen\n"
            "- [BROWSER: text selector] - Text von bestimmtem Element\n"
            "- [BROWSER: js code] - JavaScript ausfuehren\n\n"
            "BEISPIEL (richtig):\n"
            "User: 'oeffne YouTube und zeig meine Videos'\n"
            "Du: Klar, ich schau! [BROWSER: navigate https://youtube.com]\n"
            "-> Du bekommst die Seiten-Daten (Title, URL, Content)\n"
            "-> Siehst du den Avatar/channel-link? Schon eingeloggt! [BROWSER: click #avatar-btn]\n"
            "-> [BROWSER: click a[href*=/channel/]]\n"
            "-> [BROWSER: text] lesen was da steht\n"
            "-> Antworte: 'Ich habe deine Videos angesehen. Dein Channel heisst Klickspende, letztes Video: ...'\n\n"
            "WICHTIGE REGELN:\n"
            "1. Nach [BROWSER: navigate] immer [BROWSER: text] zum Pruefen obs funktioniert hat\n"
            "2. Wenn die Login-Seite kommt -> Kein Problem! Session-Cookies sind schon da -> einfach auf richtige Seite navigieren\n"
            "3. Keine Schritte erklaeren - mach sie!\n"
            "4. Mehrere Befehle in einem Satz -> alle nacheinander ausgefuehrt\n"
            "5. Im Zweifel: navigieren und machen - nicht fragen!\n"
        )
        return sp

    def _get_system_prompt(self):
        return self.base_system + self.self_improving.get_system_prompt_extension()

    def get_history(self, chat_id):
        if chat_id not in self.conversations:
            self.conversations[chat_id] = [{"role": "system", "content": self._get_system_prompt()}]
        return self.conversations[chat_id]

    def add_message(self, chat_id, role, content):
        history = self.get_history(chat_id)
        history.append({"role": role, "content": content})
        user_msgs = [m for m in history if m["role"] != "system"]
        if len(user_msgs) > MAX_HISTORY:
            history[1:] = user_msgs[-MAX_HISTORY:]

    def handle_browse(self, chat_id, text, reply_to=None):
        t = text.strip()
        if t.startswith("!browse "):
            url = t[8:].strip()
            send_action(chat_id)
            send_message(chat_id, f"Oeffne {url}...", reply_to)
            r = browser_navigate(url)
            if r.get("status") == "ok":
                send_chunked(chat_id,
                    f"<b>{r.get('title','')}</b>\n<code>{r.get('url','')}</code>\n\n{r.get('text','')[:2500]}")
            else: send_message(chat_id, f"Fehler: {r.get('message','Error')}")
            return True
        if t.startswith("!click "):
            r = browser_click(t[7:].strip())
            send_message(chat_id, "Geklickt" if r.get("status")=="ok" else f"Fehler: {r.get('message','Error')}")
            return True
        if t.startswith("!type "):
            rest = t[6:].strip()
            sel, txt = ("body", rest) if "|" not in rest else rest.split("|", 1)
            r = browser_type(sel.strip(), txt.strip())
            send_message(chat_id, "Getippt" if r.get("status")=="ok" else f"Fehler: {r.get('message','Error')}")
            return True
        if t.startswith("!text"):
            r = browser_text(t[5:].strip() or "body")
            if r.get("status")=="ok": send_chunked(chat_id, r.get('text','')[:4000])
            else: send_message(chat_id, f"Fehler: {r.get('message','Error')}")
            return True
        if t == "!screenshot":
            send_action(chat_id, "upload_photo")
            r = browser_screenshot()
            send_message(chat_id, "Screenshot gemacht" if r.get("status")=="ok" else f"Fehler: {r.get('message','Error')}")
            return True
        if t.startswith("!js "):
            r = browser_js(t[4:].strip())
            if r.get("status")=="ok": send_chunked(chat_id, f"<b>JS:</b>\n<code>{r.get('result','')[:3000]}</code>")
            else: send_message(chat_id, f"Fehler: {r.get('message','Error')}")
            return True
        return False

    def handle_update(self, chat_id):
        send_message(chat_id, f"<b>Auto-Update</b>\nAktuell: v{self.current_version}\nPruefe...")
        result = check_for_updates(chat_id)
        if result == "restart":
            send_message(chat_id, "Bot startet neu mit neuer Version...")
            log.info("Self-restart fuer Update...")
            os._exit(0)  # Docker restart: always -> startet neu!
        return True

    def _execute_browser_tool(self, cmd):
        """Fuehrt en [BROWSER: ...] Befehl us und git es Resultat zrugg."""
        cmd = cmd.strip()
        log.info(f"Browser-Tool: {cmd[:80]}")

        if cmd.startswith("navigate "):
            url = cmd[9:].strip()
            r = browser_navigate(url)
            if r.get("status") == "ok":
                return f"[BROWSER RESULTAT] Site gelade: {r.get('title','')} | URL: {r.get('url','')}\nInhalt (Aafang): {r.get('text','')[:1500]}"
            return f"[BROWSER FEHLER] Navigate: {r.get('message','')}"

        if cmd.startswith("click "):
            sel = cmd[6:].strip()
            r = browser_click(sel)
            if r.get("status") == "ok":
                return f"[BROWSER RESULTAT] Klick uf '{sel}'"
            return f"[BROWSER FEHLER] Click: {r.get('message','')}"

        if cmd.startswith("type "):
            rest = cmd[5:].strip()
            if "|" in rest:
                sel, txt = rest.split("|", 1)
                r = browser_type(sel.strip(), txt.strip())
            else:
                r = browser_type("body", rest)
            if r.get("status") == "ok":
                return f"[BROWSER RESULTAT] Text igaeh"
            return f"[BROWSER FEHLER] Type: {r.get('message','')}"

        if cmd == "text" or cmd.startswith("text "):
            sel = cmd[5:].strip() if len(cmd) > 4 else "body"
            r = browser_text(sel)
            if r.get("status") == "ok":
                return f"[BROWSER RESULTAT] Text vo de Site:\n{r.get('text','')[:2000]}"
            return f"[BROWSER FEHLER] Text: {r.get('message','')}"

        if cmd.startswith("js "):
            code = cmd[3:].strip()
            r = browser_js(code)
            if r.get("status") == "ok":
                return f"[BROWSER RESULTAT] JS: {r.get('result','')[:1500]}"
            return f"[BROWSER FEHLER] JS: {r.get('message','')}"

        return f"[BROWSER FEHLER] Unbekannte Befehl: {cmd[:60]}"

    def _process_browser_tools(self, response_text, chat_id, reply_to):
        """Findet [BROWSER: ...] im Text, fuehrt si us, git de restliche Text zrugg + s'Resultat."""
        import re
        pattern = r'\[BROWSER:\s*(.*?)\]'
        matches = re.findall(pattern, response_text, re.IGNORECASE)

        if not matches:
            return response_text, None  # Kei Browser-Befaehl

        # Text ohni Browser-Befaehl
        clean_text = re.sub(pattern, '', response_text, flags=re.IGNORECASE).strip()

        results = []
        for cmd in matches:
            result = self._execute_browser_tool(cmd.strip())
            results.append(result)

        result_text = "\n\n---\n".join(results)
        return clean_text, result_text

    def handle_message(self, chat_id, text, reply_to=None):
        # Expliziti Browser-Befaehl (!browse, etc.) behandlet handle_browse
        if self.handle_browse(chat_id, text, reply_to):
            self.self_improving.record_interaction(text, f"[Browser: {text[:50]}]")
            return

        send_action(chat_id)
        self.add_message(chat_id, "user", text)

        # Korrektur erkannt?
        history = self.get_history(chat_id)
        historical_response = None
        if len(history) >= 3:
            for m in reversed(history):
                if m["role"] == "assistant":
                    if any(w in text.lower() for w in ["falsch","nei","noed so","stimmt noed","korrektur"]):
                        historical_response = m["content"][:300]
                    break

        # Tool-Use Loop: max 10 Iteratione zum endloss Schleife verhindere
        max_tool_loops = 10
        final_response = None

        for loop in range(max_tool_loops):
            try:
                response = deepseek_chat(self.get_history(chat_id))
            except Exception as e:
                response = f"Fehler: {e}"
                self.self_improving.record_interaction(text, "", error=str(e))
                send_message(chat_id, response, reply_to)
                return

            # Browser-Befaehl im Response finde und usfuehre
            clean_response, tool_results = self._process_browser_tools(response, chat_id, reply_to)

            if tool_results is None:
                # Kei Browser-Befaehl -> fertig
                final_response = response
                self.add_message(chat_id, "assistant", response)
                break

            # Browser-Resultat als System-Nachricht a DeepSeek zrugggeh
            log.info(f"Tool-Loop {loop+1}: Browser-Befaehl usgfuehrt")
            self.add_message(chat_id, "assistant", clean_response if clean_response else "[Browser]")

            # Resultat als system message (damit DeepSeek drauf reagiert)
            tool_msg = {"role": "system", "content": f"BROWSER-RESULTAT:\n{tool_results}\n\nMach witter. Wenn alles erledigt isch, antwort dein Benutzer auf Deutsch."}
            history = self.get_history(chat_id)
            history.append(tool_msg)

        else:
            # Max Loop erreicht
            final_response = response if final_response is None else final_response
            log.warning(f"Tool-Loop Limit erreicht ({max_tool_loops})")

        # Letzti Antwort
        if final_response:
            self.add_message(chat_id, "assistant", final_response)
            error = "Bot Fehler" if "Fehler" in final_response else None
            self.self_improving.record_interaction(text, final_response, error)
            if historical_response:
                self.self_improving.record_correction(text, historical_response, "Korrektur autom. erkannt")
            if self.self_improving.should_self_review():
                self.self_improving.run_self_review(chat_id)
            send_message(chat_id, final_response, reply_to)

    def handle_start(self, chat_id, first_name=""):
        version = self.current_version
        memories = self.self_improving.load_memories()
        mem_info = f"{len(memories)} Lektionen gspiicheret" if memories else "Noch kei gspiicherti Erfahrige"
        send_message(chat_id,
            f"Hoi {first_name}!\n\n"
            f"Ich bin <b>{BOT_NAME}</b> | v{version}\n"
            f"{PROJEKT_ID}\n"
            f"{mem_info}\n\n"
            f"<b>Befaehl:</b>\n"
            f"<code>!browse https://...</code> - Site oeffne\n"
            f"<code>!click button</code> - Element klicke\n"
            f"<code>!type input | Text</code> - Text igaeh\n"
            f"<code>!screenshot</code> - Screenshot mache\n"
            f"<code>!update</code> - Bot automatisch update\n"
            f"<code>!reflect</code> - Selbstreflexion\n"
            f"<code>!memory</code> - Gspiicherti Lektion\n\n"
            f"Schrib mir!")

    def handle_help(self, chat_id):
        send_message(chat_id,
            f"<b>Hilfe</b>\n\n"
            f"Befaehl:\n"
            f"/start - Neustart\n"
            f"/help - Hilfe\n"
            f"/info - Ueber mich\n\n"
            f"Browser:\n"
            f"<code>!browse URL</code> - Site oeffne\n"
            f"<code>!click SELECTOR</code> - Klicke\n"
            f"<code>!type SELECTOR | TEXT</code> - Tippe\n"
            f"<code>!screenshot</code> - Screenshot\n"
            f"<code>!js CODE</code> - JS usfuehre\n\n"
            f"Auto-Update:\n"
            f"<code>!update</code> - Code vo GitHub lade & neu starte\n"
            f"Der Bot prueft automatisch alli 60 Minute obs es Update git!\n\n"
            f"Self-Improving:\n"
            f"<code>!reflect</code> - Jetzt reflektiere\n"
            f"<code>!memory</code> - Lektion ahluege\n"
            f"<code>!forget</code> - Gedaechtnis leere")

    def handle_info(self, chat_id):
        n_mem = len(self.self_improving.load_memories())
        send_message(chat_id,
            f"<b>{BOT_NAME}</b>\n"
            f"Projekt: {PROJEKT_ID}\n"
            f"Modell: {DEEPSEEK_MODEL}\n"
            f"Version: v{self.current_version}\n"
            f"Self-Improving: ({n_mem} Lektionen)\n"
            f"Auto-Update: (GitHub, alli 60min)\n"
            f"Browser: ({BROWSER_URL})")

    def handle_reflect(self, chat_id):
        send_message(chat_id, "Starte Selbstreflexion...")
        self.self_improving.run_self_review(chat_id)

    def handle_memory(self, chat_id):
        memories = self.self_improving.load_memories()
        if memories:
            send_chunked(chat_id, f"<b>Gspiicherti Lektion:</b>\n\n{memories[:4000]}")
        else:
            send_message(chat_id, "Kei Lektion gspiicheret. Bruuch <code>!reflect</code> zum starte!")

    def handle_forget(self, chat_id):
        for f in [self.self_improving.memory_file, self.self_improving.corrections_file, self.self_improving.interactions_file]:
            try: os.remove(f)
            except: pass
        self.self_improving.message_count = 0
        self.self_improving._save_state()
        send_message(chat_id, "Gedaechtnis glerrt! Frischer Start")

    def _auto_update_check(self):
        """Prueft automatisch alli 60 Minute obs es Update git."""
        now = time.time()
        if now - self.last_update_check < 3600:  # 60 min
            return
        self.last_update_check = now
        log.info("Auto-Update-Check...")
        try:
            result = check_for_updates()
            if result == "restart":
                log.info("Auto-Update: Restart...")
                os._exit(0)
        except Exception as e:
            log.warning(f"Auto-Update check failed: {e}")

    def poll(self):
        result = tg_call("getUpdates", {"timeout": POLL_TIMEOUT, "offset": self.last_update_id + 1, "allowed_updates": ["message"]})
        if not result.get("ok"): return
        for update in result.get("result", []):
            self.last_update_id = update["update_id"]
            msg = update.get("message")
            if not msg: continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()
            first_name = msg.get("from", {}).get("first_name", "")
            reply_to = msg.get("message_id")
            if not text: continue
            log.info(f"{first_name}: {text[:60]}")

            if text.startswith("/start"): self.handle_start(chat_id, first_name)
            elif text.startswith("/help"): self.handle_help(chat_id)
            elif text.startswith("/info"): self.handle_info(chat_id)
            elif text == "!update": self.handle_update(chat_id)
            elif text == "!reflect": self.handle_reflect(chat_id)
            elif text == "!memory": self.handle_memory(chat_id)
            elif text == "!forget": self.handle_forget(chat_id)
            else: self.handle_message(chat_id, text, reply_to)

            # Nach jeder Nohricht: Update-Check
            self._auto_update_check()

    def run(self):
        log.info("Polling aktiv...")
        while True:
            try: self.poll()
            except KeyboardInterrupt: log.info("Gestoppt"); break
            except Exception as e:
                log.error(f"Fehler: {e}")
                time.sleep(5)

if __name__ == "__main__":
    if not BOT_TOKEN:
        log.error("Kei TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    BotAgent().run()
