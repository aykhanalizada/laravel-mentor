#!/usr/bin/env python3
"""
Local web UI — kod suallarını brauzerdə cavabla.
http://localhost:7000
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "progress.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PORT = 7000

DIFFICULTY_LABELS = {"easy": "🟢 Asan", "medium": "🟡 Orta", "hard": "🔴 Çətin"}
TYPE_LABELS = {
    "theory": "💬 Nəzəriyyə", "code_write": "✍️ Kod yaz",
    "code_read": "🔍 Kodu oxu", "debug": "🐛 Debug", "logic": "🧠 Məntiq",
}


def load_progress():
    with open(PROGRESS_FILE) as f:
        return json.load(f)


def render_question(pending: dict) -> str:
    q = pending.get("question", "")
    # Code blokları HTML-ə çevir
    import re
    q_html = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre><code>\1</code></pre>", q, flags=re.DOTALL)
    q_html = q_html.replace("\n", "<br>")
    return q_html


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

  window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});
}}

document.addEventListener('keydown', function(e) {{
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submitAnswer();
}});
</script>
</body>
</html>"""


def build_page(pending: dict | None) -> str:
    if not pending or pending.get("answered"):
        content = """
        <div class="no-question">
          <h2>Aktiv sual yoxdur</h2>
          <p>Telegram-da <strong>/sual</strong> yazaraq yeni sual al.</p>
        </div>"""
        return HTML_TEMPLATE.format(badges="", content=content)

    diff = pending.get("difficulty", "easy")
    q_type = pending.get("q_type", "code_write")
    topic = pending.get("topic", "")
    day = pending.get("day", 1)

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
    """

    return HTML_TEMPLATE.format(badges=badges, content=content)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # server loglarını sustur

    def do_GET(self):
        try:
            progress = load_progress()
            pending = progress.get("pending_question")
            html = build_page(pending)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))

    def do_POST(self):
        if self.path != "/submit":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        answer = unquote_plus(params.get("answer", [""])[0]).strip()

        if not answer:
            self._json({"error": "boş cavab"}, 400)
            return

        # mentor.py process_answer-ı çağır
        result = subprocess.run(
            ["python3", "-c", f"""
import sys, os
sys.path.insert(0, '{BASE_DIR}')
os.environ['TELEGRAM_BOT_TOKEN'] = os.environ.get('TELEGRAM_BOT_TOKEN', '')
os.environ['TELEGRAM_CHAT_ID'] = os.environ.get('TELEGRAM_CHAT_ID', '')
from mentor import process_answer
print(process_answer({json.dumps(answer)}))
"""],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT_ID}
        )

        if result.returncode != 0:
            self._json({"error": result.stderr[:200]}, 500)
            return

        output = result.stdout.strip()

        # Qiyməti parse et
        grade = 5
        score = "partial"
        import re
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
