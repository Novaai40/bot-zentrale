#!/usr/bin/env python3
import os, sys, json, time, logging, urllib.request, urllib.error, glob, re
from datetime import datetime, timezone

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
    """Sendet langi Text i Teil."""
    if len(text) <= max_len:
        return send_message(chat_id, text, reply_to)
    parts = []
    while text:
        chunk = text[:max_len]
        # Bruch anere natürlichi Grenze
        if len(text) > max_len:
            last_space = chunk.rfind("\n")
            if last_space > 0:
                chunk = chunk[:last_space]
        parts.append(chunk)
        text = text[len(chunk):]
    for i, p in enumerate(parts):
        reply = reply_to if i == 0 else None
        send_message(chat_id, p, reply)

# ─── Self-Improving ───
class SelfImproving:
    """Eigeni Lernfähigkeit — analysiert Feedback, korrigiert Verhalte, wird besser."""
    
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
        log.info(f"🧠 Self-Improving initialisiert ({self.memory_dir})")

    def _load_state(self):
        """Ladet de Zählerstand vo de letzte Session."""
        try:
            if os.path.exists(self.last_review_file):
                with open(self.last_review_file) as f:
                    state = json.load(f)
                    self.message_count = state.get("count", 0)
                    log.info(f"📊 Geladnige Zählerstand: {self.message_count}")
        except:
            self.message_count = 0

    def _save_state(self):
        """Speicheret de Zählerstand."""
        try:
            with open(self.last_review_file, "w") as f:
                json.dump({"count": self.message_count, "updated": datetime.now(timezone.utc).isoformat()}, f)
        except:
            pass

    def record_interaction(self, user_msg, bot_response, error=None):
        """Loggt die Lektion für spöteri Reflexion."""
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
        except:
            pass
        self._save_state()

    def record_correction(self, user_msg, bot_response, correction_text):
        """Speicheret expliziti Korrekture vom Benutzer."""
        entry = (
            f"## Korrektur vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"**User gseit:** {user_msg[:300]}\n"
            f"**Bot het gantwortet:** {bot_response[:300]}\n"
            f"**Korrektur/Rückmeldig:** {correction_text[:500]}\n\n"
            f"**Was i druus lerne sött:**\n"
            f"- {self._infer_lesson(user_msg, bot_response, correction_text)}\n\n"
            f"---\n"
        )
        try:
            with open(self.corrections_file, "a") as f:
                f.write(entry)
            log.info(f"📝 Korrektur gspiicheret")
            return entry
        except Exception as e:
            log.error(f"Fehler bim Korrektur-Speichere: {e}")
            return None

    def _infer_lesson(self, user_msg, bot_response, correction):
        """Extrahiert e Lern-Lektion us ere Korrektur (wird vom DeepSeek gmacht)."""
        # Einfachi Muster-Erkennig für häufigi Fäll
        if "falsch" in correction.lower() or "falsche" in correction.lower():
            return "Uf Korrektur achte und genau priefe bevor antworte."
        if "kürzer" in correction.lower() or "chürzer" in correction.lower():
            return "Antwortene chürzer und prägnanter halte."
        if "nicht" in correction.lower() and "wollen" in correction.lower():
            return "Meh nachem Kontext froge, statt Ahnige mache."
        return f"Mues us dere Korrektur lehre: {correction[:200]}"

    def add_memory(self, lesson, source="auto"):
        """Füegt en Lern-Eintrag i s Langzitgedächtnis."""
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        entry = f"- [{source}] {lesson} ({timestamp})\n"
        try:
            with open(self.memory_file, "a") as f:
                f.write(entry)
            log.info(f"💾 Memory gspiicheret: {lesson[:60]}")
        except Exception as e:
            log.error(f"Memory save failed: {e}")

    def load_memories(self):
        """Ladet alli gspiicherte Lektion für de System Prompt."""
        memories = []
        for filepath in [self.memory_file, self.corrections_file]:
            if os.path.exists(filepath):
                with open(filepath) as f:
                    content = f.read().strip()
                    if content:
                        memories.append(content)
        return "\n\n".join(memories) if memories else ""

    def should_self_review(self):
        """Söll eine selbst-Reflexion mache (alli 20 Nohrichte)?"""
        return self.message_count > 0 and self.message_count % 20 == 0

    def run_self_review(self, chat_id):
        """Führt e Selbstreflexion über die letschte Interaktionie dure."""
        # Letzti Interaktionie us em Log läse
        recent = []
        try:
            if os.path.exists(self.interactions_file):
                with open(self.interactions_file) as f:
                    lines = f.readlines()
                    for line in lines[-10:]:
                        try: recent.append(json.loads(line))
                        except: pass
        except:
            pass

        if not recent:
            return

        prompt = (
            f"Du bisch {BOT_NAME}, en KI-Agent för {PROJEKT_ID}. "
            f"Mach eni kurzi Selbstreflexion über die letschte Interaktionie.\n\n"
            f"LETSCHTI INTERAKTIONE:\n"
            + "\n".join([
                f"User:   {r['user'][:100]}\nBot:    {r['bot'][:100]}\nFehler: {r.get('error','keine')[:100]}"
                for r in recent[-5:]
            ]) +
            f"\n\nFRAGE AN DICH:\n"
            f"1. Was hani guet gmacht?\n"
            f"2. Was hani falsch gmacht oder cha besser?\n"
            f"3. Welchi Lern-Lektion chani us dere Erkenntnis zieh?\n\n"
            f"Antwort in 1-2 Sätz pro Frag. Säg am Schluss: LEKTION: [ein Satz was du besser mache wit]"
        )

        # Mini eige Reflexion — thread-safe
        try:
            headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
            messages = [{"role": "user", "content": prompt}]
            payload = {"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": 512, "temperature": 0.7}
            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                review = data["choices"][0]["message"]["content"]

            # Lektion extrahiere
            lesson = ""
            for line in review.split("\n"):
                if line.startswith("LEKTION:"):
                    lesson = line.replace("LEKTION:", "").strip()

            if lesson:
                self.add_memory(lesson, "self-review")

            # Meldig a Marco
            send_message(chat_id,
                f"<b>🔄 Selbstreflexion #{self.message_count // 20}</b>\n\n"
                f"{review[:1500]}\n\n"
                f"{'📝 Lektion gspiicheret: ' + lesson if lesson else ''}")

        except Exception as e:
            log.error(f"Self-review fehlgschlage: {e}")


    def get_system_prompt_extension(self):
        """Git d'Selbstverbesserigs-Instruktion für de System Prompt."""
        memories = self.load_memories()
        ext = (
            f"\n\n═══════════════════════════════════\n"
            f"🧠 SELBSTVERBESSERUNGS-MODUS (AKTIV)\n"
            f"═══════════════════════════════════\n\n"
            f"- Du analysiersch dini eigene Fehler und verbesserisch dich.\n"
            f"- Wenn dir en Fehler passiert, lernsch druus für s'nöchste Mol.\n"
            f"- Du hesch en gschribene Gedächtnis-Speicher — nütz ihn!\n"
            f"- Reflektier öber dini Antwortene bevor du se abschicksch.\n"
            f"- Wemmer explizit gseit wird was falsch isch -> MERK DIR DAS!\n"
        )
        if memories:
            ext += f"\n📚 GSPICHERTI LEKTIONE:\n{memories[:2000]}\n"
        return ext

# ─── Browser Bridge ───
def browser_call(action, **kwargs):
    payload = {"project": PROJEKT_ID, **kwargs}
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{BROWSER_URL}/{action}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200] if e.fp else ""
        return {"status": "error", "message": f"Bridge HTTP {e.code}: {body}"}
    except Exception as e:
        return {"status": "error", "message": f"Bridge: {e}"}

def browser_navigate(url):
    return browser_call("navigate", url=url)

def browser_click(selector):
    return browser_call("click", selector=selector)

def browser_type(selector, text):
    return browser_call("type", selector=selector, text=text)

def browser_text(selector="body"):
    return browser_call("text", selector=selector)

def browser_screenshot():
    return browser_call("screenshot")

def browser_js(code):
    return browser_call("js", code=code)

def browser_state():
    return browser_call("state")

# ─── DeepSeek ───
DS_URL = "https://api.deepseek.com/chat/completions"

def deepseek_chat(messages):
    if not DEEPSEEK_KEY:
        return "❌ Kei DeepSeek API Key."
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    payload = {"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": 2048, "temperature": 0.8}
    try:
        req = urllib.request.Request(DS_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200] if e.fp else ""
        log.error(f"DS Fehler {e.code}: {body}")
        return f"❌ DeepSeek Fehler {e.code}"
    except Exception as e:
        log.error(f"DS Error: {e}")
        return f"❌ Verbindigsfehler: {e}"

# ─── Bot ───
class BotAgent:
    def __init__(self):
        self.conversations = {}
        self.last_update_id = 0
        self.self_improving = SelfImproving(PROJEKT_ID)
        self.base_system = self._build_system_prompt()
        log.info(f"{BOT_NAME} gestartet | Projekt: {PROJEKT_ID}")

    def _build_system_prompt(self):
        sp = (
            f"Du heissisch {BOT_NAME} und bisch en KI-Bot im Projekt {PROJEKT_ID}.\n\n"
            f"DEIN CHARAKTER:\n{BOT_CHARAKTER}\n\n"
            f"DEINE AUFGABE:\n{BOT_AUFGABE}\n\n"
        )
        if CHAT_WEBSEITE:
            sp += f"\nWEBSEITE: {CHAT_WEBSEITE}\n"
        if CHAT_YOUTUBE:
            sp += f"\nYOUTUBE: {CHAT_YOUTUBE}\n"
        sp += (
            "\nWichtigi Regle:\n"
            "- Du antwortisch immer uf Dütsch.\n"
            "- Bisch freundlich, kompetent und professionell.\n"
            "- Hesch en eigeni Persönlichkeit.\n"
            "- Bi Unsicherheit frogsch nah.\n"
            "- Verwend HTML-Formatierig für Telegram (Bold, Kursiv).\n"
        )
        return sp

    def _get_system_prompt(self):
        """Baut de System Prompt mit aktuelle Lektion zämme."""
        memories = self.self_improving.load_memories()
        ext = self.self_improving.get_system_prompt_extension()
        return self.base_system + ext

    def get_history(self, chat_id):
        if chat_id not in self.conversations:
            self.conversations[chat_id] = [{"role": "system", "content": self._get_system_prompt()}]
        return self.conversations[chat_id]

    def add_message(self, chat_id, role, content):
        history = self.get_history(chat_id)
        history.append({"role": role, "content": content})
        user_msgs = [m for m in history if m["role"] != "system"]
        if len(user_msgs) > MAX_HISTORY:
            # Behault erste und letschti N
            history[1:] = user_msgs[-MAX_HISTORY:]

    def _refresh_system_prompt(self, chat_id):
        """Erneuert de System Prompt mit aktuellschte Lektion (ohni Verlust vo History)."""
        if chat_id in self.conversations:
            history = self.conversations[chat_id]
            if history and history[0]["role"] == "system":
                history[0]["content"] = self._get_system_prompt()

    def fmt_result(self, r):
        if r.get("status") == "ok":
            return r
        return {"status": "error", "message": r.get("message", "Unbekannt")}

    def handle_browse(self, chat_id, text, reply_to=None):
        text_clean = text.strip()

        if text_clean.startswith("!browse "):
            url = text_clean[8:].strip()
            send_action(chat_id)
            send_message(chat_id, f"🌐 Öffne {url}...", reply_to)
            r = browser_navigate(url)
            if r.get("status") == "ok":
                t = r.get("title", "")
                u = r.get("url", "")
                body = r.get("text", "")[:3000]
                send_chunked(chat_id,
                    f"<b>🌐 {t}</b>\n"
                    f"<code>{u}</code>\n\n"
                    f"{body[:2500]}")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean.startswith("!click "):
            sel = text_clean[7:].strip()
            send_action(chat_id)
            r = browser_click(sel)
            if r.get("status") == "ok":
                send_message(chat_id, f"✅ Klick uf <code>{sel}</code>")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean.startswith("!type "):
            rest = text_clean[6:].strip()
            sel, txt = "body", rest
            if "|" in rest:
                sel, txt = rest.split("|", 1)
                sel, txt = sel.strip(), txt.strip()
            r = browser_type(sel, txt) if sel else browser_type(rest, "")
            if r.get("status") == "ok":
                send_message(chat_id, f"✅ Tippet i <code>{sel}</code>")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean.startswith("!text"):
            sel = text_clean[5:].strip() or "body"
            r = browser_text(sel)
            if r.get("status") == "ok":
                send_chunked(chat_id, f"📄 {r.get('text', '')[:4000]}")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean == "!screenshot":
            send_action(chat_id, "upload_photo")
            r = browser_screenshot()
            if r.get("status") == "ok":
                send_message(chat_id, f"📸 Screenshot gmacht")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean.startswith("!js "):
            code = text_clean[4:].strip()
            send_action(chat_id)
            r = browser_js(code)
            if r.get("status") == "ok":
                send_chunked(chat_id, f"<b>JS Result:</b>\n<code>{r.get('result','')[:3000]}</code>")
            else:
                send_message(chat_id, f"❌ {r.get('message', 'Fehler')}")
            return True

        if text_clean == "!login":
            send_message(chat_id, "🔄 Öffne Login-Site... Säg mir d'URL und ich logge mich ii!")
            return True

        return False

    def handle_message(self, chat_id, text, reply_to=None):
        # Browser-Befähl zersch priefe
        if self.handle_browse(chat_id, text, reply_to):
            self.self_improving.record_interaction(text, f"[Browser-Befehl: {text[:50]}]")
            return

        # Support-Befähl
        if text.startswith("/"):
            return

        # Normal gschribe — DeepSeek beziege
        send_action(chat_id)
        self.add_message(chat_id, "user", text)

        # Prüefe obs en Korrektur isch
        historical_response = None
        history = self.get_history(chat_id)
        if len(history) >= 3:
            last_bot_msg = None
            for m in reversed(history):
                if m["role"] == "assistant":
                    last_bot_msg = m
                    break
            if last_bot_msg and any(w in text.lower() for w in ["falsch", "falsche", "nei", "nöd so", "stimmt nöd", "ander", "korrektur"]):
                historical_response = last_bot_msg["content"][:300]

        try:
            response = deepseek_chat(self.get_history(chat_id))
        except Exception as e:
            response = f"❌ Fehler bi de Verarbeitig: {e}"
            self.self_improving.record_interaction(text, "", error=str(e))
            send_message(chat_id, response, reply_to)
            return

        self.add_message(chat_id, "assistant", response)

        # Logge Interaktion
        error = None
        if "❌" in response or "Fehler" in response:
            error = "Bot het en Fehler g'meldet"

        self.self_improving.record_interaction(text, response, error)

        # Korrektur erkannt?
        if historical_response:
            self.self_improving.record_correction(text, historical_response, "Korrektur festgstellt")

        # Self-Reflexion (alli 20 Nohrichte)
        if self.self_improving.should_self_review():
            log.info(f"🔄 Starte Selbstreflexion #{self.self_improving.message_count // 20}")
            self.self_improving.run_self_review(chat_id)

        send_message(chat_id, response, reply_to)

    def handle_start(self, chat_id, first_name=""):
        memories = self.self_improving.load_memories()
        memory_status = f"🧠 Gspiichert: {len(memories)} Lektionen" if memories else "🧠 Noni gspiicherti Erfahrige"
        send_message(chat_id,
            f"👋 Hoi {first_name}!\n\n"
            f"Ich bin <b>{BOT_NAME}</b> 🤖\n"
            f"📌 Projekt: <b>{PROJEKT_ID}</b>\n"
            f"{memory_status}\n\n"
            f"<b>Befähl:</b>\n"
            f"<code>!browse https://...</code> — Site öffne\n"
            f"<code>!click button</code> — Element klicke\n"
            f"<code>!type input | Text</code> — Text igäh\n"
            f"<code>!screenshot</code> — Screenshot mache\n"
            f"<code>!reflect</code> — Jetzt reflektiere\n"
            f"<code>!memory</code> — Gspiicherti Lektion ahluege\n\n"
            f"Schrib mir eifach — ich bin für dich da! 🚀")

    def handle_help(self, chat_id):
        send_message(chat_id,
            f"<b>🤖 {BOT_NAME} — Hilfe</b>\n\n"
            f"💬 <b>Befähl:</b>\n"
            f"/start — Neustart\n"
            f"/help — Die Hilfe\n"
            f"/info — Über mich\n\n"
            f"<b>🌐 Browser-Befähl:</b>\n"
            f"<code>!browse URL</code> — Site öffne & Inhalt zeige\n"
            f"<code>!click SELECTOR</code> — Element klicke\n"
            f"<code>!type SELECTOR | TEXT</code> — Text igäh\n"
            f"<code>!screenshot</code> — Screenshot mache\n"
            f"<code>!js JAVASCRIPT</code> — JS usführe\n\n"
            f"<b>🧠 Selbstreflexion:</b>\n"
            f"<code>!reflect</code> — Manuelli Selbstreflexion starte\n"
            f"<code>!memory</code> — Gspiicherti Lektion ahluege\n"
            f"<code>!forget</code> — Gedächtnis zruggsetze\n\n"
            f"Sus chasch mir eifach schriibe!")

    def handle_info(self, chat_id):
        n_memories = len(self.self_improving.load_memories())
        send_message(chat_id,
            f"<b>ℹ️ {BOT_NAME}</b>\n"
            f"📁 Projekt: {PROJEKT_ID}\n"
            f"🧠 Modell: {DEEPSEEK_MODEL}\n"
            f"🌐 Browser: {BROWSER_URL}\n"
            f"🧠 Self-Improving: ✅ Aktiv ({n_memories} Lektionen)\n"
            f"📦 Version: 3.0 (Docker + Browser + Learning)")

    def handle_reflect(self, chat_id):
        send_message(chat_id, "🔄 Starte Selbstreflexion...")
        self.self_improving.run_self_review(chat_id)

    def handle_memory(self, chat_id):
        memories = self.self_improving.load_memories()
        if memories:
            send_chunked(chat_id,
                f"<b>🧠 Gspiicherti Lektion:</b>\n\n{memories[:4000]}")
        else:
            send_message(chat_id, "📭 No kei Lektion gspiicheret. Schrib mir eifach — mit <code>!reflect</code> chansch selber reflektiere!")

    def handle_forget(self, chat_id):
        try:
            for f in [self.self_improving.memory_file, self.self_improving.corrections_file, self.self_improving.interactions_file]:
                if os.path.exists(f):
                    os.remove(f)
            self.self_improving.message_count = 0
            self.self_improving._save_state()
            self._refresh_system_prompt(chat_id)
            send_message(chat_id, "🧹 Gedächtnis zrugggsetzt! Starte frisch 🆕")
        except Exception as e:
            send_message(chat_id, f"❌ Fehler: {e}")

    def poll(self):
        result = tg_call("getUpdates", {"timeout": POLL_TIMEOUT, "offset": self.last_update_id + 1, "allowed_updates": ["message"]})
        if not result.get("ok"):
            return
        for update in result.get("result", []):
            self.last_update_id = update["update_id"]
            msg = update.get("message")
            if not msg: continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()
            first_name = msg.get("from", {}).get("first_name", "")
            reply_to = msg.get("message_id")
            if not text: continue
            log.info(f"📨 {first_name}: {text[:60]}")

            if text.startswith("/start"):
                self.handle_start(chat_id, first_name)
            elif text.startswith("/help"):
                self.handle_help(chat_id)
            elif text.startswith("/info"):
                self.handle_info(chat_id)
            elif text == "!reflect":
                self.handle_reflect(chat_id)
            elif text == "!memory":
                self.handle_memory(chat_id)
            elif text == "!forget":
                self.handle_forget(chat_id)
            else:
                self.handle_message(chat_id, text, reply_to)

    def run(self):
        log.info("Polling aktiv...")
        while True:
            try:
                self.poll()
            except KeyboardInterrupt:
                log.info("Gestoppt"); break
            except Exception as e:
                log.error(f"Fehler: {e}")
                time.sleep(5)

if __name__ == "__main__":
    if not BOT_TOKEN:
        os.environ.get("Kei TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    BotAgent().run()
