#!/usr/bin/env python3
"""
Local web UI — kod suallarını brauzerdə cavabla.
http://localhost:8731
"""

import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus
import force_ipv4  # IPv6-sız şəbəkə üçün, şəbəkə çağırışlarından ƏVVƏL

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "progress.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PORT = 8731

DIFFICULTY_LABELS = {"starter": "🔰 Başlanğıc", "easy": "🟢 Asan", "medium": "🟡 Orta", "hard": "🔴 Çətin"}
TYPE_LABELS = {
    "theory": "💬 Nəzəriyyə", "code_write": "✍️ Kod yaz",
    "code_read": "🔍 Kodu oxu", "debug": "🐛 Debug", "logic": "🧠 Məntiq",
}


def load_progress():
    with open(PROGRESS_FILE) as f:
        return json.load(f)


def escape_html(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_question(entry: dict) -> str:
    q = entry.get("question", "")
    # Code blokları HTML-ə çevir
    q_html = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre><code>\1</code></pre>", q, flags=re.DOTALL)
    q_html = q_html.replace("\n", "<br>")
    return q_html


def render_evaluation(evaluation: dict) -> str:
    grade     = evaluation.get("grade", 5)
    score     = evaluation.get("score", "partial")
    cls       = "correct" if score == "correct" else "partial" if score == "partial" else "incorrect"
    bar_color = "#22c55e" if grade >= 7 else "#eab308" if grade >= 5 else "#ef4444"
    emoji     = "✅" if score == "correct" else "🟡" if score == "partial" else "❌"
    feedback  = escape_html(evaluation.get("feedback", ""))

    missing = evaluation.get("missing_points", [])
    missing_html = ""
    if missing:
        items = "".join(f"<li>{escape_html(m)}</li>" for m in missing)
        missing_html = f"<div style='margin-top:12px'><strong>⚠️ Əskik məqamlar:</strong><ul style='margin:6px 0 0 18px'>{items}</ul></div>"

    hint = evaluation.get("correct_answer_hint", "")
    hint_html = f"<div style='margin-top:12px'><strong>💎 Düzgün cavab:</strong> {escape_html(hint)}</div>" if hint else ""

    return f"""
    <div class="result-card result-{cls}">
      <div class="grade-bar">
        <span class="grade-num">{emoji} {grade}/10</span>
        <div class="bar"><div class="bar-fill" style="width:{grade*10}%;background:{bar_color}"></div></div>
      </div>
      <div class="result-text">{feedback}</div>
      {missing_html}
      {hint_html}
    </div>"""


def render_discussion_thread(discussion: list) -> str:
    parts = []
    for d in discussion:
        student = escape_html(d.get("student", ""))
        mentor  = escape_html(d.get("mentor", "")).replace("\n", "<br>")
        parts.append(f'<div class="disc-bubble disc-student">🙋 {student}</div>')
        parts.append(f'<div class="disc-bubble disc-mentor">🧑‍🏫 {mentor}</div>')
    return "".join(parts)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="az">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Laravel Mentor</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
  .container {{ max-width: 860px; margin: 0 auto; padding: 24px 16px; }}
  header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }}
  header h1 {{ font-size: 1.3rem; color: #f8fafc; }}
  .badge {{ padding: 4px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }}
  .easy {{ background: #166534; color: #bbf7d0; }}
  .medium {{ background: #713f12; color: #fef08a; }}
  .hard {{ background: #7f1d1d; color: #fecaca; }}
  .type-badge {{ background: #1e3a5f; color: #93c5fd; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #334155; }}
  .card h2 {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 12px; }}
  .question-text {{ line-height: 1.7; color: #cbd5e1; }}
  .question-text pre {{ background: #0f172a; border-radius: 8px; padding: 14px; margin: 12px 0; overflow-x: auto; border: 1px solid #334155; }}
  .question-text code {{ font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.88rem; color: #a5f3fc; }}
  .question-text br {{ display: block; content: ""; margin: 4px 0; }}
  textarea {{ width: 100%; height: 340px; background: #0f172a; color: #a5f3fc; border: 1px solid #334155; border-radius: 8px; padding: 14px; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.9rem; resize: vertical; outline: none; line-height: 1.6; transition: border-color 0.2s; }}
  textarea:focus {{ border-color: #3b82f6; }}
  .actions {{ display: flex; gap: 12px; margin-top: 12px; }}
  button {{ padding: 12px 28px; border-radius: 8px; border: none; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
  .btn-primary {{ background: #3b82f6; color: white; flex: 1; }}
  .btn-primary:hover {{ background: #2563eb; }}
  .btn-primary:disabled {{ background: #1e40af; opacity: 0.6; cursor: not-allowed; }}
  .btn-secondary {{ background: #334155; color: #94a3b8; }}
  .btn-secondary:hover {{ background: #475569; }}
  .result {{ display: none; margin-top: 16px; }}
  .result.show {{ display: block; }}
  .result-card {{ border-radius: 12px; padding: 20px; border: 1px solid; }}
  .result-correct {{ background: #052e16; border-color: #166534; }}
  .result-partial {{ background: #1c1a08; border-color: #713f12; }}
  .result-incorrect {{ background: #1c0a0a; border-color: #7f1d1d; }}
  .result-text {{ line-height: 1.7; white-space: pre-wrap; color: #cbd5e1; }}
  .grade-bar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
  .grade-num {{ font-size: 1.5rem; font-weight: 700; }}
  .bar {{ flex: 1; height: 8px; background: #334155; border-radius: 99px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 99px; transition: width 0.6s ease; }}
  .spinner {{ display: inline-block; width: 18px; height: 18px; border: 2px solid #ffffff40; border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; margin-right: 8px; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .no-question {{ text-align: center; padding: 60px 20px; color: #64748b; }}
  .no-question h2 {{ font-size: 1.2rem; margin-bottom: 8px; color: #94a3b8; }}
  .hint {{ background: #172033; border-left: 3px solid #3b82f6; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: 10px; font-size: 0.85rem; color: #93c5fd; }}
  .starter {{ background: #1e3a5f; color: #93c5fd; }}
  .discussion-section textarea {{ height: 90px; margin-top: 10px; }}
  #discussion-thread {{ display: flex; flex-direction: column; gap: 8px; max-height: 360px; overflow-y: auto; margin-bottom: 4px; }}
  .disc-bubble {{ padding: 10px 14px; border-radius: 8px; line-height: 1.6; white-space: pre-wrap; font-size: 0.92rem; }}
  .disc-student {{ background: #1e3a5f; color: #dbeafe; align-self: flex-end; max-width: 85%; }}
  .disc-mentor {{ background: #334155; color: #e2e8f0; align-self: flex-start; max-width: 85%; }}
  .answer-readonly {{ line-height: 1.7; color: #cbd5e1; white-space: pre-wrap; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>⚡ Laravel Mentor</h1>
    {badges}
  </header>
  {content}
</div>
<script>
async function submitAnswer() {{
  const answer = document.getElementById('answer').value.trim();
  if (!answer) {{ alert('Cavab boşdur!'); return; }}

  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Qiymətləndirilir...';

  const res = await fetch('/submit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: 'answer=' + encodeURIComponent(answer)
  }});
  const data = await res.json();

  const resultDiv = document.getElementById('result');
  const resultCard = document.getElementById('result-card');
  const grade = data.grade || 0;
  const scoreClass = data.score === 'correct' ? 'correct' : data.score === 'partial' ? 'partial' : 'incorrect';
  const barColor = grade >= 7 ? '#22c55e' : grade >= 5 ? '#eab308' : '#ef4444';
  const emoji = data.score === 'correct' ? '✅' : data.score === 'partial' ? '🟡' : '❌';

  resultCard.className = 'result-card result-' + scoreClass;
  resultCard.innerHTML = `
    <div class="grade-bar">
      <span class="grade-num">${{emoji}} ${{grade}}/10</span>
      <div class="bar"><div class="bar-fill" style="width:${{grade*10}}%;background:${{barColor}}"></div></div>
    </div>
    <div class="result-text">${{data.text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</div>
  `;
  resultDiv.classList.add('show');

  btn.innerHTML = '✅ Göndərildi — Telegram-a bax';
  btn.style.background = '#166534';

  const discSection = document.getElementById('discussion-section');
  if (discSection) discSection.style.display = 'block';

  window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});
}}

async function submitDiscussion() {{
  const input = document.getElementById('discuss-input');
  const message = input.value.trim();
  if (!message) {{ alert('Mesaj boşdur!'); return; }}

  const btn = document.getElementById('discuss-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Fikirləşir...';

  const thread = document.getElementById('discussion-thread');
  const studentDiv = document.createElement('div');
  studentDiv.className = 'disc-bubble disc-student';
  studentDiv.textContent = '🙋 ' + message;
  thread.appendChild(studentDiv);

  const res = await fetch('/discuss', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: 'message=' + encodeURIComponent(message)
  }});
  const data = await res.json();

  const mentorDiv = document.createElement('div');
  mentorDiv.className = 'disc-bubble disc-mentor';
  mentorDiv.textContent = '🧑‍🏫 ' + (data.text || data.error || 'Xəta baş verdi.');
  thread.appendChild(mentorDiv);

  input.value = '';
  btn.disabled = false;
  btn.innerHTML = 'Göndər';
  thread.scrollTop = thread.scrollHeight;
}}

document.addEventListener('keydown', function(e) {{
  if (!(e.ctrlKey || e.metaKey) || e.key !== 'Enter') return;
  if (e.target && e.target.id === 'discuss-input') submitDiscussion();
  else submitAnswer();
}});
</script>
</body>
</html>"""


def build_page(pending: dict | None, last_entry: dict | None) -> str:
    # Vəziyyət A: aktiv (cavablanmamış) sual var — sual + cavab forması
    if pending and not pending.get("answered"):
        diff   = pending.get("difficulty", "easy")
        q_type = pending.get("q_type", "code_write")
        topic  = pending.get("topic", "")
        day    = pending.get("day", 1)

        badges = f"""
          <span class="badge {diff}">{DIFFICULTY_LABELS.get(diff, diff)}</span>
          <span class="badge type-badge">{TYPE_LABELS.get(q_type, q_type)}</span>
          <span style="margin-left:auto;color:#64748b;font-size:0.85rem">Gün {day}</span>
        """

        q_html = render_question(pending)

        content = f"""
        <div class="card">
          <h2>📚 {topic}</h2>
          <div class="question-text">{q_html}</div>
          <div class="hint">💡 Ctrl+Enter ilə göndər</div>
        </div>
        <div class="card">
          <h2>✍️ Cavabın</h2>
          <textarea id="answer" placeholder="PHP kodunu bura yaz...&#10;&#10;// nümunə:&#10;interface PaymentInterface {{&#10;    public function pay(float $amount): string;&#10;}}" spellcheck="false"></textarea>
          <div class="actions">
            <button class="btn-primary" id="submit-btn" onclick="submitAnswer()">Göndər</button>
            <button class="btn-secondary" onclick="document.getElementById('answer').value=''">Təmizlə</button>
          </div>
        </div>
        <div class="result" id="result">
          <div class="result-card" id="result-card"></div>
        </div>
        <div class="card discussion-section" id="discussion-section" style="display:none">
          <h2>💬 Müzakirə</h2>
          <div id="discussion-thread"></div>
          <textarea id="discuss-input" placeholder="Qiymətə etirazın və ya əlavə izahatın... (Ctrl+Enter ilə göndər)" spellcheck="false"></textarea>
          <div class="actions">
            <button class="btn-primary" id="discuss-btn" onclick="submitDiscussion()">Göndər</button>
          </div>
        </div>
        """
        return HTML_TEMPLATE.format(badges=badges, content=content)

    # Vəziyyət B: aktiv sual yoxdur, amma sonuncu sual cavablanıb — müzakirə rejimi
    if last_entry:
        evaluation = last_entry.get("evaluation", {})
        diff   = last_entry.get("difficulty", "easy")
        q_type = last_entry.get("q_type", "theory")
        topic  = last_entry.get("topic", "")
        day    = last_entry.get("day", 1)

        badges = f"""
          <span class="badge {diff}">{DIFFICULTY_LABELS.get(diff, diff)}</span>
          <span class="badge type-badge">{TYPE_LABELS.get(q_type, q_type)}</span>
          <span style="margin-left:auto;color:#64748b;font-size:0.85rem">Gün {day} — cavablanıb</span>
        """

        q_html      = render_question(last_entry)
        answer_html = escape_html(last_entry.get("answer", "")).replace("\n", "<br>")
        eval_html   = render_evaluation(evaluation)
        thread_html = render_discussion_thread(last_entry.get("discussion", []))

        content = f"""
        <div class="card">
          <h2>📚 {topic}</h2>
          <div class="question-text">{q_html}</div>
        </div>
        <div class="card">
          <h2>✍️ Sənin cavabın</h2>
          <div class="answer-readonly">{answer_html}</div>
        </div>
        <div class="card">
          <h2>📝 Qiymətləndirmə</h2>
          {eval_html}
        </div>
        <div class="card discussion-section" id="discussion-section">
          <h2>💬 Müzakirə</h2>
          <div id="discussion-thread">{thread_html}</div>
          <textarea id="discuss-input" placeholder="Qiymətə etirazın və ya əlavə izahatın... (Ctrl+Enter ilə göndər)" spellcheck="false"></textarea>
          <div class="actions">
            <button class="btn-primary" id="discuss-btn" onclick="submitDiscussion()">Göndər</button>
          </div>
        </div>
        <div class="hint">💡 Yeni sual üçün Telegram-da <strong>/sual</strong> yaz</div>
        """
        return HTML_TEMPLATE.format(badges=badges, content=content)

    # Vəziyyət C: heç bir sual yoxdur
    content = """
    <div class="no-question">
      <h2>Aktiv sual yoxdur</h2>
      <p>Telegram-da <strong>/sual</strong> yazaraq yeni sual al.</p>
    </div>"""
    return HTML_TEMPLATE.format(badges="", content=content)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # server loglarını sustur

    def do_GET(self):
        try:
            progress   = load_progress()
            pending    = progress.get("pending_question")
            last_entry = None
            if not pending or pending.get("answered"):
                history = progress.get("history", [])
                if history:
                    last_entry = history[-1]
            html = build_page(pending, last_entry)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))

    def do_POST(self):
        if self.path == "/submit":
            self._handle_submit()
        elif self.path == "/discuss":
            self._handle_discuss()
        else:
            self.send_error(404)

    def _run_mentor_call(self, func: str, arg: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", "-c", f"""
import sys, os
sys.path.insert(0, '{BASE_DIR}')
os.environ['TELEGRAM_BOT_TOKEN'] = os.environ.get('TELEGRAM_BOT_TOKEN', '')
os.environ['TELEGRAM_CHAT_ID'] = os.environ.get('TELEGRAM_CHAT_ID', '')
from mentor import {func}
print({func}({json.dumps(arg)}))
"""],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT_ID}
        )

    def _handle_submit(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        answer = unquote_plus(params.get("answer", [""])[0]).strip()

        if not answer:
            self._json({"error": "boş cavab"}, 400)
            return

        result = self._run_mentor_call("process_answer", answer)

        if result.returncode != 0:
            self._json({"error": result.stderr[:200]}, 500)
            return

        output = result.stdout.strip()

        # Qiyməti parse et
        grade = 5
        score = "partial"
        m = re.search(r"Qiymət: (\d+)/10", output)
        if m:
            grade = int(m.group(1))
        if "✅" in output:
            score = "correct"
        elif "❌" in output:
            score = "incorrect"

        # HTML taglarını təmizlə
        clean = re.sub(r"<[^>]+>", "", output)

        self._json({"text": clean, "grade": grade, "score": score})

    def _handle_discuss(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        message = unquote_plus(params.get("message", [""])[0]).strip()

        if not message:
            self._json({"error": "boş mesaj"}, 400)
            return

        result = self._run_mentor_call("process_discussion", message)

        if result.returncode != 0:
            self._json({"error": result.stderr[:200]}, 500)
            return

        clean = re.sub(r"<[^>]+>", "", result.stdout.strip())
        self._json({"text": clean})

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def run():
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Web UI: http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
