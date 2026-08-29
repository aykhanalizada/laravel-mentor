#!/usr/bin/env python3
"""
Telegram bot listener — istifadəçi cavabını Telegram-da yazır.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import re
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "progress.json"
OFFSET_FILE = BASE_DIR / ".tg_offset"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", ""))

DIFFICULTY_LABELS = {"starter": "🔰 Başlanğıc", "easy": "🟢 Asan", "medium": "🟡 Orta", "hard": "🔴 Çətin"}
TYPE_LABELS = {
    "theory": "💬 Nəzəriyyə", "code_write": "✍️ Kod yaz",
    "code_read": "🔍 Kodu oxu", "debug": "🐛 Debug", "logic": "🧠 Məntiq",
    "trick": "🎩 PHP Trick",
}

BOT_COMMANDS = [
    {"command": "sual",       "description": "Günün sualını al (və ya aktivini göstər)"},
    {"command": "status",     "description": "Proqresinə bax"},
    {"command": "ipucu",      "description": "Aktiv sualda ipucu al"},
    {"command": "komandalar", "description": "Bütün əmrlərin siyahısı"},
]


def _log_child_stderr(tag: str, result) -> None:
    """mentor.py səssiz uğursuzluqları (məs. Telegram göndərilmədi) stderr-ə yazır,
    lakin çıxış kodu 0 qalır — ona görə stderr həmişə log-a köçürülür."""
    err = (getattr(result, "stderr", "") or "").strip()
    if err:
        print(f"[{tag} stderr] {err[:500]}")


def tg_api(method: str, data: dict = None) -> dict:
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    payload = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"} if payload else {}
    )
    # api.telegram.org-un AAAA yazısı var, bu maşında isə IPv6 default route yoxdur →
    # urllib vaxtaşırı [Errno 101] atır. Bir dəfəlik uğursuzluq mesajı itirməməlidir.
    last_err = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(1.5 * attempt)
    print(f"[API xəta] {method} (3 cəhd): {last_err}")
    return {}


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def safe_html(text: str) -> str:
    def fence_to_html(m):
        lang = m.group(1)
        code = escape_html(m.group(2).strip("\n"))
        cls  = f' class="language-{lang}"' if lang else ""
        return f"<pre><code{cls}>{code}</code></pre>"

    text = re.sub(r"```(\w*)\n?(.*?)```", fence_to_html, text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+?)`", lambda m: f"<code>{escape_html(m.group(1))}</code>", text)
    parts = re.split(r"(<b>.*?</b>|<code>.*?</code>|<i>.*?</i>|<pre>.*?</pre>|<a href=\"[^\"]*\">.*?</a>)", text, flags=re.DOTALL)
    return "".join(
        part if part.startswith(("<b>", "<code>", "<i>", "<pre>", "<a ")) else escape_html(part)
        for part in parts
    )


def send(text: str, reply_to: int = None):
    payload = {"chat_id": CHAT_ID, "text": safe_html(text), "parse_mode": "HTML"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    tg_api("sendMessage", payload)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def run_mentor(cmd: str) -> str:
    result = subprocess.run(
        ["python3", str(BASE_DIR / "mentor.py"), cmd],
        capture_output=True, text=True, timeout=180,
        env={**os.environ, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT_ID}
    )
    _log_child_stderr("mentor", result)
    return result.stdout.strip() if result.returncode == 0 else f"❌ Xəta: {result.stderr[:300]}"


def handle_discussion(message: str, message_id: int):
    progress = load_json(PROGRESS_FILE)
    if not progress.get("history"):
        send("⚠️ Aktiv sual yoxdur. /sual yazaraq yeni sual al.", reply_to=message_id)
        return

    send("⏳ Fikirləşirəm...", reply_to=message_id)

    result = subprocess.run(
        ["python3", "-c", f"""
import sys
sys.path.insert(0, '{BASE_DIR}')
import os
os.environ['TELEGRAM_BOT_TOKEN'] = '{TOKEN}'
os.environ['TELEGRAM_CHAT_ID'] = '{CHAT_ID}'
from mentor import process_discussion
result = process_discussion({json.dumps(message)})
print(result)
"""],
        capture_output=True, text=True, timeout=180
    )

    _log_child_stderr("mentor", result)
    if result.returncode == 0:
        send(result.stdout.strip())
    else:
        send(f"❌ Xəta: {result.stderr[:200]}")


def handle_answer(answer: str, message_id: int):
    progress = load_json(PROGRESS_FILE)
    pending = progress.get("pending_question")

    if not pending or pending.get("answered"):
        handle_discussion(answer, message_id)
        return

    topic = pending.get("topic", "")
    diff = pending.get("difficulty", "easy")
    q_type = pending.get("q_type", "theory")

    send(
        f"⏳ Qiymətləndirilir...\n"
        f"<i>{topic} | {DIFFICULTY_LABELS.get(diff)} | {TYPE_LABELS.get(q_type)}</i>",
        reply_to=message_id
    )

    # mentor.py process_answer-ı çağır
    result = subprocess.run(
        ["python3", "-c", f"""
import sys
sys.path.insert(0, '{BASE_DIR}')
import os
os.environ['TELEGRAM_BOT_TOKEN'] = '{TOKEN}'
os.environ['TELEGRAM_CHAT_ID'] = '{CHAT_ID}'
from mentor import process_answer
result = process_answer({json.dumps(answer)})
print(result)
"""],
        capture_output=True, text=True, timeout=180
    )

    _log_child_stderr("mentor", result)
    if result.returncode == 0:
        send(result.stdout.strip())
    else:
        send(f"❌ Qiymətləndirmə xətası: {result.stderr[:200]}")


def handle_command(text: str, message_id: int):
    cmd = text.strip().lower().split()[0]

    if cmd in ("/sual", "/question", "/start"):
        progress = load_json(PROGRESS_FILE)
        pending = progress.get("pending_question")
        if pending and not pending.get("answered"):
            q = pending["question"]
            diff = pending.get("difficulty", "easy")
            q_type = pending.get("q_type", "theory")
            msg = (
                f"🎯 <b>Gün {pending['day']} — aktiv sual</b>\n"
                f"{DIFFICULTY_LABELS.get(diff)} | {TYPE_LABELS.get(q_type)}\n\n"
                f"{q}\n\n"
            )
            if q_type in ("code_write", "debug"):
                msg += '💻 <b>Kodu buradan yaz:</b> <a href="http://localhost:8731">http://localhost:8731</a>'
            else:
                msg += "✍️ Cavabını birbaşa bura yaz!"
            send(msg)
            return

        send("⏳ Yeni sual hazırlanır...")
        result = subprocess.run(
            ["python3", str(BASE_DIR / "mentor.py"), "question"],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT_ID}
        )
        _log_child_stderr("mentor", result)
        if result.returncode != 0:
            send(f"❌ Xəta: {result.stderr[:200]}")

    elif cmd == "/status":
        send("⏳ Hesabat hazırlanır...")
        result = subprocess.run(
            ["python3", str(BASE_DIR / "mentor.py"), "status"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT_ID}
        )
        _log_child_stderr("mentor", result)
        if result.returncode != 0:
            send(f"❌ Xəta: {result.stderr[:200]}")

    elif cmd == "/ipucu":
        progress = load_json(PROGRESS_FILE)
        pending = progress.get("pending_question")
        if not pending or pending.get("answered"):
            send("Aktiv sual yoxdur.")
            return
        topic = pending.get("topic", "")
        subtopics = []
        try:
            roadmap = load_json(BASE_DIR / "roadmap.json")
            for level in roadmap["levels"]:
                for t in level["topics"]:
                    if t["name"] == topic:
                        subtopics = t.get("subtopics", [])
        except Exception:
            pass
        hint = f"💡 <b>{topic}</b> mövzusunda bu anlayışlara bax:\n"
        for s in subtopics:
            hint += f"  • {s}\n"
        send(hint)

    elif cmd == "/komandalar":
        send(
            "📋 <b>Komandalar:</b>\n\n"
            "/sual — yeni sual al (və ya aktivini göstər)\n"
            "/status — proqresinə bax\n"
            "/ipucu — aktiv sualda ipucu al\n"
            "/komandalar — bu siyahı\n\n"
            "💬 <b>Sual gəldikdən sonra cavabını birbaşa yaz</b> — bot qiymətləndirir.\n"
            "🗣 <b>Qiymətə razı deyilsənsə, cavab gələndən sonra yenə yaz</b> — bot arqumentini dinləyib lazım gələrsə qiyməti düzəldir."
        )


def get_offset() -> int:
    return int(OFFSET_FILE.read_text().strip()) if OFFSET_FILE.exists() else 0


def save_offset(offset: int):
    OFFSET_FILE.write_text(str(offset))


def check_daily_reminder():
    """Axşam 20:00-da cavablanmamış sual varsa xatırlatma göndər."""
    now = datetime.now()
    if now.hour != 20 or now.minute > 5:
        return

    reminder_file = BASE_DIR / ".last_reminder"
    today = now.strftime("%Y-%m-%d")
    if reminder_file.exists() and reminder_file.read_text().strip() == today:
        return

    try:
        progress = load_json(PROGRESS_FILE)
        pending = progress.get("pending_question")
        if pending and not pending.get("answered"):
            send(
                f"⏰ <b>Xatırlatma!</b>\n\n"
                f"Bu günün sualı hələ cavablanmayıb.\n"
                f"Mövzu: <b>{pending['topic']}</b>\n\n"
                f"/sual yazaraq sualı göstər."
            )
            reminder_file.write_text(today)
    except Exception:
        pass


def run():
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM_BOT_TOKEN və ya TELEGRAM_CHAT_ID yoxdur.")
        return

    tg_api("setMyCommands", {"commands": BOT_COMMANDS})

    print(f"Bot başladı. Chat: {CHAT_ID}")
    send(
        "🤖 <b>Laravel Mentor Bot aktiv oldu!</b>\n\n"
        "/sual — günün sualını al\n"
        "/status — proqresinə bax\n"
        "/ipucu — sualda kömək\n"
        "/komandalar — bütün əmrlər"
    )

    offset = get_offset()
    last_reminder_check = 0

    while True:
        try:
            # Axşam xatırlatma yoxlaması (hər 5 dəqiqədən bir)
            if time.time() - last_reminder_check > 300:
                check_daily_reminder()
                last_reminder_check = time.time()

            resp = tg_api("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message"]})
            updates = resp.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)

                msg = update.get("message", {})
                if not msg:
                    continue
                if str(msg.get("chat", {}).get("id", "")) != CHAT_ID:
                    continue

                text = msg.get("text", "").strip()
                message_id = msg.get("message_id")
                if not text:
                    continue

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Mesaj: {text[:50]!r}")
                if text.startswith("/"):
                    handle_command(text, message_id)
                else:
                    handle_answer(text, message_id)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Emal edildi.")

        except KeyboardInterrupt:
            print("\nBot dayandırıldı.")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Xəta] {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run()
