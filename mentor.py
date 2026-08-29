#!/usr/bin/env python3
"""Laravel Senior Developer Mentor Bot — Gamified Edition"""

import json
import os
import sys
import argparse
import subprocess
import random
import re
from datetime import datetime, date, timedelta
from pathlib import Path
import urllib.request
import urllib.error
import time

import force_ipv4  # IPv6-sız şəbəkə üçün, şəbəkə çağırışlarından ƏVVƏL

BASE_DIR = Path(__file__).parent
ROADMAP_FILE  = BASE_DIR / "roadmap.json"
PROGRESS_FILE = BASE_DIR / "progress.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Çətinlik ──────────────────────────────────────────────────────────────────
DIFFICULTY_ORDER  = ["starter", "easy", "medium", "hard"]
DIFFICULTY_LABELS = {
    "starter": "🔰 Başlanğıc",
    "easy":    "🟢 Asan",
    "medium":  "🟡 Orta",
    "hard":    "🔴 Çətin",
}
DIFFICULTY_XP_MULT = {"starter": 0.3, "easy": 0.6, "medium": 1.5, "hard": 2.5}
DIFFICULTY_GUIDE   = {
    "starter": (
        "ÇOXTƏCÜBSÜZ başlanğıc sualı. Tək bir anlayışı soruşur. "
        "Cavablamaq üçün 5 dəqiqəlik bilik bəs edər. "
        "Heç bir mürəkkəblik olmasın. Nümunə: 'interface nədir, nümunə göstər'."
    ),
    "easy": (
        "Asan sual. Birbaşa, tək konsept. "
        "Junior developer rahatlıqla cavablaya bilər."
    ),
    "medium": (
        "Orta sual. İki-üç konsepti birləşdir. Real ssenari işlət. "
        "Fikirləşmək lazımdır."
    ),
    "hard": (
        "Çətin sual. Edge case, performans, arxitektura qərarı. "
        "Senior düşüncəsi tələb edir."
    ),
}

# ── Sual tipləri ──────────────────────────────────────────────────────────────
TYPE_LABELS = {
    "theory":     "💬 Nəzəriyyə",
    "code_write": "✍️ Kod yaz",
    "code_read":  "🔍 Kodu oxu",
    "debug":      "🐛 Debug",
    "logic":      "🧠 Məntiq",
    "trick":      "🎩 PHP Trick",
}
TYPE_PROMPTS = {
    "theory":     "Nəzəri sual: istifadəçi konsepti sadə sözlə izah etməlidir.",
    "code_write": "Kod yazmaq tapşırığı: istifadəçi PHP/Laravel kodu yazmalıdır.",
    "code_read":  "Bir kod parçası göstər (max 25 sətir). İstifadəçi nə etdiyini izah etsin.",
    "debug":      "Buglu kod parçası göstər. İstifadəçi xətanı tapsın.",
    "logic":      "PHP-də sadə alqoritm/məntiq sualı. Collection, array, rekursiya.",
    "trick":      "PHP TRICK SUAL. Aşağıdakı kateqoriyalardan birini seç və qısa kod snippet göstər. İstifadəçi 'Bu kod nə çap edir? Niyə?' sualına cavab verməlidir.",
}

# PHP trick kateqoriyaları — sual yaradarkən prompt-a əlavə olunur
TRICK_CATEGORIES = [
    "array copy-on-write ($a=[1,2,3]; $b=$a; $b[]=4; — $a dəyişirmi?)",
    "reference assignment ($b=&$a — $b dəyişəndə $a nə olur?)",
    "loose vs strict comparison (0=='foo', ''==false, null==false, '0'==false)",
    "type juggling (string-dən int-ə avtomatik çevrilmə)",
    "foreach ilə reference ($arr as &$v — loop-dan sonra son element problemi)",
    "static dəyişən funksiyada (hər çağırışda artır, reset olmur)",
    "pre vs post increment (++$a vs $a++, return dəyəri fərqi)",
    "isset vs empty vs is_null (null/''/0/false üçün fərqli nəticələr)",
    "string-ə array kimi müraciət ($s='hello'; echo $s[1];)",
    "PHP 8 match vs switch (strict comparison, return dəyəri, default)",
    "null coalescing (?? vs ?: fərqi)",
    "closure use by value vs by reference (use($x) vs use(&$x))",
    "array_map vs foreach — hansı dəyişəni dəyişdirir?",
    "list() / array destructuring [$a, $b] = [1, 2]",
    "integer overflow və float dəqiqliyi (PHP-də 0.1+0.2==0.3?)",
    "string multiplication ('2'*3 vs '2abc'*3)",
    "compact() / extract() gözlənilməz davranış",
    "ternary zəncirlənməsi ($a?$b:$c?$d:$e PHP 7 vs PHP 8 fərqi)",
    "array_keys, array_values — orijinal array dəyişirmi?",
    "Laravel Collection lazy vs eager — toArray() çağırılmadan nə baş verir?",
]

# starter çətinlikdə yalnız sadə tiplər + trick (çünki trick-lər əyləncəli və qısdır)
STARTER_TYPES = ["theory", "code_write", "trick"]

# ── Player level sistemi ───────────────────────────────────────────────────────
PLAYER_LEVELS = [
    (0,     1, "🌱 Trainee"),
    (2000,  2, "⚡ Junior"),
    (6000,  3, "🔥 Junior+"),
    (15000, 4, "💎 Mid"),
    (30000, 5, "🚀 Mid+"),
    (60000, 6, "👑 Senior"),
]

# Keyfiyyət qapıları: level-up üçün XP kifayət deyil — bu şərtlər də ödənməlidir.
LEVEL_GATES = {
    2: {"medium_correct": 5},
    3: {"medium_correct": 15, "hard_correct": 3},
    4: {"hard_correct": 15, "hard_topics": 5},
    5: {"hard_correct": 40, "hard_topics": 10},
    6: {"hard_correct": 80, "hard_topics": 15},
}

def _count_correct_at(progress: dict, difficulty: str) -> int:
    return sum(1 for h in progress.get("history", [])
               if h.get("difficulty") == difficulty
               and h.get("evaluation", {}).get("score") == "correct")

def _distinct_topics_correct_at(progress: dict, difficulty: str) -> int:
    return len({h.get("topic") for h in progress.get("history", [])
                if h.get("difficulty") == difficulty
                and h.get("evaluation", {}).get("score") == "correct"})

def check_level_gate(progress: dict, target_level: int) -> tuple[bool, list[str]]:
    gate = LEVEL_GATES.get(target_level, {})
    missing = []
    if "medium_correct" in gate:
        c, r = _count_correct_at(progress, "medium"), gate["medium_correct"]
        if c < r: missing.append(f"Medium correct: {c}/{r}")
    if "hard_correct" in gate:
        c, r = _count_correct_at(progress, "hard"), gate["hard_correct"]
        if c < r: missing.append(f"Hard correct: {c}/{r}")
    if "hard_topics" in gate:
        c, r = _distinct_topics_correct_at(progress, "hard"), gate["hard_topics"]
        if c < r: missing.append(f"Fərqli hard mövzu: {c}/{r}")
    return (not missing), missing

def get_player_level(progress: dict) -> tuple[int, str, int, int, list[str]]:
    """(level_num, label, current_xp_in_level, xp_needed_for_next, gate_missing).
    Gate keçilməsə XP kifayət olsa belə level yüksəlmir."""
    xp = progress.get("xp", 0)
    xp_tier = 1
    for threshold, num, _ in PLAYER_LEVELS:
        if xp >= threshold: xp_tier = num
    effective, gate_missing = 1, []
    for _, num, _ in PLAYER_LEVELS:
        if num == 1 or num > xp_tier: continue
        passed, missing = check_level_gate(progress, num)
        if passed:
            effective = num
        else:
            gate_missing = missing
            break
    eff_label   = next(l for _, n, l in PLAYER_LEVELS if n == effective)
    cur_thresh  = next(t for t, n, _ in PLAYER_LEVELS if n == effective)
    next_list   = [t for t, n, _ in PLAYER_LEVELS if n == effective + 1]
    next_thresh = next_list[0] if next_list else cur_thresh + 9999
    cur_in_lvl  = max(0, min(xp, next_thresh) - cur_thresh)
    need_in_lvl = next_thresh - cur_thresh
    return effective, eff_label, cur_in_lvl, need_in_lvl, gate_missing

def xp_bar(current: int, needed: int, width: int = 10) -> str:
    filled = round(current / needed * width) if needed else width
    filled = min(filled, width)
    return "▓" * filled + "░" * (width - filled)

# ── Badges ────────────────────────────────────────────────────────────────────
BADGE_CHECKS = [
    ("first_answer",  "🎯 İlk Cavab",       lambda p: p["score"]["correct"] + p["score"]["partial"] + p["score"]["incorrect"] >= 1),
    ("streak_3",      "🔥 3 Gün Streak",    lambda p: p.get("streak", 0) >= 3),
    ("streak_7",      "⚡ 7 Gün Streak",    lambda p: p.get("streak", 0) >= 7),
    ("streak_30",     "👑 30 Gün Streak",   lambda p: p.get("streak", 0) >= 30),
    ("correct_10",    "✅ 10 Düzgün",       lambda p: p["score"]["correct"] >= 10),
    ("correct_50",    "🏅 50 Düzgün",       lambda p: p["score"]["correct"] >= 50),
    ("xp_1000",       "💎 1000 XP",         lambda p: p.get("xp", 0) >= 1000),
    ("xp_5000",       "🚀 5000 XP",         lambda p: p.get("xp", 0) >= 5000),
    ("no_wrong_5",    "🎯 5 Ardıcıl Düzgün",lambda p: p.get("consecutive_correct", 0) >= 5),
    ("hard_correct",  "💪 Çətin Sual Həll", lambda p: any(h.get("difficulty") == "hard" and h.get("evaluation", {}).get("score") == "correct" for h in p.get("history", []))),
]

def check_badges(progress: dict) -> list[str]:
    """Yeni qazanılan badge-ları qaytar."""
    earned = set(progress.get("badges", []))
    new_badges = []
    for bid, label, check in BADGE_CHECKS:
        if bid not in earned and check(progress):
            earned.add(bid)
            new_badges.append(label)
    progress["badges"] = list(earned)
    return new_badges


# ── Topic mastery & spaced repetition ────────────────────────────────────────
REVIEW_INTERVALS = [1, 3, 7, 21, 60]   # gün, Anki-style

# Mastery şərti: kifayət qədər cavab + medium+ correct + orta grade
MASTERY_MIN_ANSWERS         = 5
MASTERY_MIN_CORRECT         = 3
MASTERY_MIN_HIGHEST_DIFF    = "medium"   # ən azı medium correct
MASTERY_MIN_AVG_GRADE       = 6.5

def _new_topic_stats(difficulty: str = "starter") -> dict:
    return {
        "answers": 0, "correct": 0, "partial": 0, "incorrect": 0,
        "grades_sum": 0, "avg_grade": 0.0,
        "highest_diff_correct": None,
        "current_difficulty": difficulty,
        "consecutive_correct": 0, "consecutive_wrong": 0,
        "last_asked_date": None,
        "next_review_date": None,
        "review_interval_days": 0,
        "mastered": False,
    }

def is_topic_mastered(stats: dict) -> bool:
    if not stats: return False
    order = DIFFICULTY_ORDER
    highest = stats.get("highest_diff_correct")
    return (
        stats.get("answers", 0) >= MASTERY_MIN_ANSWERS and
        stats.get("correct", 0) >= MASTERY_MIN_CORRECT and
        highest is not None and
        order.index(highest) >= order.index(MASTERY_MIN_HIGHEST_DIFF) and
        stats.get("avg_grade", 0) >= MASTERY_MIN_AVG_GRADE
    )

def topic_mastery_pct(stats: dict) -> int:
    if not stats or stats.get("answers", 0) == 0: return 0
    order = DIFFICULTY_ORDER
    ans     = min(stats.get("answers", 0) / MASTERY_MIN_ANSWERS, 1.0)
    correct = min(stats.get("correct", 0) / MASTERY_MIN_CORRECT, 1.0)
    grade   = min(stats.get("avg_grade", 0) / 10.0, 1.0)
    highest = stats.get("highest_diff_correct") or "starter"
    diff    = order.index(highest) / (len(order) - 1)  # 0..1
    return round((0.15*ans + 0.25*correct + 0.30*grade + 0.30*diff) * 100)

def compute_next_review(current_interval: int, grade: int, from_date: str | None = None) -> tuple[str, int]:
    """Qrade-ə görə növbəti review-un tarixini və interval-ı qaytarır."""
    if grade >= 7:
        if current_interval in REVIEW_INTERVALS:
            i = REVIEW_INTERVALS.index(current_interval)
            new = REVIEW_INTERVALS[min(i + 1, len(REVIEW_INTERVALS) - 1)]
        else:
            new = REVIEW_INTERVALS[0]
    elif grade >= 5:
        new = current_interval if current_interval > 0 else REVIEW_INTERVALS[0]
    else:
        new = REVIEW_INTERVALS[0]
    base = date.fromisoformat(from_date) if from_date else date.today()
    return (base + timedelta(days=new)).isoformat(), new

def _bump_topic_difficulty(stats: dict, grade: int) -> str:
    order = DIFFICULTY_ORDER
    cur   = stats.get("current_difficulty", "starter")
    idx   = order.index(cur) if cur in order else 0
    cc, cw = stats.get("consecutive_correct", 0), stats.get("consecutive_wrong", 0)
    if grade >= 8:
        cc += 1; cw = 0
        if cc >= 2 and idx < len(order) - 1: idx += 1; cc = 0
    elif grade <= 3:
        cw += 1; cc = 0
        if cw >= 2 and idx > 0: idx -= 1; cw = 0
    else:
        cc = 0; cw = 0
    stats["consecutive_correct"], stats["consecutive_wrong"] = cc, cw
    return order[idx]

def update_topic_stats(progress: dict, topic_id: str, difficulty: str,
                       grade: int, score: str, today: str) -> dict:
    all_stats = progress.setdefault("topic_stats", {})
    s = all_stats.setdefault(topic_id, _new_topic_stats(difficulty))
    s["answers"]      += 1
    s[score]           = s.get(score, 0) + 1
    s["grades_sum"]    = s.get("grades_sum", 0) + grade
    s["avg_grade"]     = round(s["grades_sum"] / s["answers"], 2)
    s["last_asked_date"] = today
    if score == "correct":
        order = DIFFICULTY_ORDER
        cur_h = s.get("highest_diff_correct")
        if cur_h is None or order.index(difficulty) > order.index(cur_h):
            s["highest_diff_correct"] = difficulty
    s["current_difficulty"] = _bump_topic_difficulty(s, grade)
    s["next_review_date"], s["review_interval_days"] = compute_next_review(
        s.get("review_interval_days", 0), grade, from_date=today
    )
    s["mastered"] = is_topic_mastered(s)
    return s

def rebuild_topic_stats(progress: dict, topic_id: str) -> dict:
    """Bir mövzunun statistikasını history-dən sıfırdan yenidən qurur.
    Qiymət sonradan düzəldiləndə lazımdır: update_topic_stats() sayğacları artırır,
    ona görə düzəliş üçün onu ikinci dəfə çağırmaq cavab sayını ikiqat edərdi.
    Replay isə interval/consecutive kimi yol-asılı sahələri də dəqiq bərpa edir."""
    entries = [h for h in progress.get("history", [])
               if h.get("topic_id") == topic_id and h.get("evaluation")]
    if not entries:
        return progress.get("topic_stats", {}).get(topic_id, {})

    progress.setdefault("topic_stats", {})[topic_id] = \
        _new_topic_stats(entries[0].get("difficulty", "starter"))

    stats = {}
    for h in entries:
        ev = h["evaluation"]
        stats = update_topic_stats(
            progress, topic_id,
            h.get("difficulty", "starter"),
            ev.get("grade", 5),
            ev.get("score", "partial"),
            h.get("date") or date.today().isoformat(),
        )
    return stats

def _all_topics_with_level(roadmap: dict) -> list[tuple[dict, dict]]:
    return [(lvl, t) for lvl in roadmap["levels"] for t in lvl["topics"]]

def get_next_topic(roadmap: dict, progress: dict) -> tuple[dict | None, dict | None, bool]:
    """Prioritet: overdue review > linear cari mövzu.
    Qaytarır (level, topic, is_review)."""
    today = date.today().isoformat()
    topic_stats = progress.get("topic_stats", {})
    overdue = []
    for lvl, topic in _all_topics_with_level(roadmap):
        s = topic_stats.get(topic["id"])
        if not s or s.get("mastered"): continue
        nr = s.get("next_review_date")
        if nr and nr <= today:
            overdue.append((nr, lvl, topic))
    if overdue:
        overdue.sort(key=lambda x: x[0])
        _, lvl, topic = overdue[0]
        return lvl, topic, True
    # Linear
    lvl, topic = get_current_topic(roadmap, progress)
    return lvl, topic, False


# ── Utility ───────────────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path) as f: return json.load(f)

def save_json(path: Path, data: dict):
    with open(path, "w") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def ask_claude(prompt: str) -> str:
    r = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=120)
    if r.returncode != 0: raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()

def extract_json(text: str) -> dict:
    """Claude-un mətn cavabından JSON obyektini etibarlı şəkildə çıxarır.
    Claude bəzən ```json``` fence-i ilə əhatə edir, bəzən xam JSON qaytarır —
    sadə 'ilk { - son }' kəsimi hər ikisini eyni etibarla tutmur."""
    candidates = []
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text.strip())
    s, e = text.find("{"), text.rfind("}") + 1
    if s >= 0 and e > s:
        candidates.append(text[s:e])

    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return {}

def escape_html(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def safe_html(text: str) -> str:
    def fence_to_html(m):
        lang = m.group(1)
        code = escape_html(m.group(2).strip("\n"))
        cls  = f' class="language-{lang}"' if lang else ""
        return f"<pre><code{cls}>{code}</code></pre>"

    text  = re.sub(r"```(\w*)\n?(.*?)```", fence_to_html, text, flags=re.DOTALL)
    text  = re.sub(r"`([^`\n]+?)`", lambda m: f"<code>{escape_html(m.group(1))}</code>", text)
    parts = re.split(r"(<b>.*?</b>|<code>.*?</code>|<i>.*?</i>|<pre>.*?</pre>|<a href=\"[^\"]*\">.*?</a>)", text, flags=re.DOTALL)
    return "".join(p if p.startswith(("<b>","<code>","<i>","<pre>","<a ")) else escape_html(p) for p in parts)

def send_telegram(text: str, retries: int = 4) -> bool:
    """Mesajı Telegram-a göndərir. Uğuru bool kimi qaytarır.
    Bu maşında api.telegram.org üçün AAAA yazısı var, amma IPv6 default route yoxdur —
    urllib vaxtaşırı [Errno 101] verir. Uğursuzluq səssiz qalmamalıdır: xəta stderr-ə
    yazılır ki, bot_listener-in log-una düşsün."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return True

    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": safe_html(text), "parse_mode": "HTML"}).encode()
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.loads(r.read())
            if res.get("ok"):
                return True
            last_err = res                      # 400/parse xətası — təkrar cəhd kömək etməz
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:200]!r}"
            break
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * attempt)

    print(f"[Telegram xəta] göndərilmədi ({retries} cəhd): {last_err}", file=sys.stderr)
    return False


# ── Roadmap naviqasiyası ───────────────────────────────────────────────────────
def get_current_topic(roadmap: dict, progress: dict) -> tuple:
    level_id  = progress["current_level"]
    topic_idx = progress["current_topic_index"]
    levels = roadmap["levels"]
    level  = next((l for l in levels if l["id"] == level_id), levels[0])
    topics = level["topics"]

    if topic_idx >= len(topics):
        nxt = next((l for l in levels if l["id"] == level_id + 1), None)
        if nxt:
            progress.update({"current_level": nxt["id"], "current_topic_index": 0, "difficulty": "starter"})
            save_json(PROGRESS_FILE, progress)
            level, topics, topic_idx = nxt, nxt["topics"], 0
        else:
            return level, None
    return level, topics[topic_idx]


# ── Sual generasiyası ─────────────────────────────────────────────────────────
def pick_question_type(topic: dict, progress: dict, difficulty: str) -> str:
    available = STARTER_TYPES if difficulty == "starter" else topic.get("types", ["theory", "code_write"])
    recent    = progress.get("question_type_history", [])[-3:]
    fresh     = [t for t in available if t not in recent]
    return random.choice(fresh if fresh else available)

def adjust_difficulty(progress: dict, grade: int):
    order = DIFFICULTY_ORDER
    diff  = progress.get("difficulty", "starter")
    idx   = order.index(diff) if diff in order else 1
    cc, cw = progress.get("consecutive_correct", 0), progress.get("consecutive_wrong", 0)

    if grade >= 8:
        cc += 1; cw = 0
        if cc >= 2 and idx < len(order) - 1:
            idx += 1; cc = 0
    elif grade <= 3:
        cw += 1; cc = 0
        if cw >= 2 and idx > 0:
            idx -= 1; cw = 0
    else:
        cc = 0; cw = 0

    progress["difficulty"]          = order[idx]
    progress["consecutive_correct"] = cc
    progress["consecutive_wrong"]   = cw

def generate_question(progress: dict, level: dict, topic: dict, q_type: str) -> str:
    difficulty = progress.get("difficulty", "starter")
    recent     = [h["topic"] for h in progress["history"][-4:]]
    weak       = ", ".join(progress.get("weak_topics", [])) or "yoxdur"

    # Trick suallar üçün xüsusi prompt
    if q_type == "trick":
        used_tricks = [
            h.get("trick_category", "") for h in progress["history"]
            if h.get("q_type") == "trick"
        ]
        available = [c for c in TRICK_CATEGORIES if c not in used_tricks]
        category  = random.choice(available if available else TRICK_CATEGORIES)
        # Seçilən kateqoriyanı pending-ə saxlamaq üçün progress-ə qoy
        progress["_next_trick_category"] = category

        prompt = f"""Sən PHP/Laravel müəllimsən. Maraqlı PHP trick sualı hazırla.

Kateqoriya: {category}

TAPŞIRIQ: Bu kateqoriya üzrə qısa PHP snippet göstər və "Bu kod nə çap edir? Niyə?" soruş.

QAYDALAR:
- Azərbaycan dilində
- Snippet maksimum 8-10 sətir olsun
- Kod ``` blokunda olsun
- Çıxış gözlənilməz/maraqlı olsun — trick hissəsi məhz buradadır
- Cavabda nəyi izah etməli olduğunu 2 bullet ilə göstər

DƏQIQ FORMAT:
🎩 PHP Trick
🔰 Başlanğıc | 🎩 PHP Trick

❓ Bu kod nə çap edir?

```php
[kod buraya]
```

💡 Cavabında bunları əhatə et:
• Çıxışın nə olduğunu yaz
• Niyə belə olduğunu izah et"""

        return ask_claude(prompt)

    prompt = f"""Sən peşəkar Laravel mentor-san. Tələbəni tədricən junior-dan senior-a hazırlayırsan.

Tələbə haqqında:
- Cari roadmap səviyyəsi: {level['name']}
- Mövzu: {topic['name']}
- Alt mövzular: {', '.join(topic['subtopics'])}
- Çətinlik: {difficulty} — {DIFFICULTY_GUIDE[difficulty]}
- Sual tipi: {q_type} — {TYPE_PROMPTS[q_type]}
- Son mövzular: {recent}
- Zəif mövzular: {weak}

TAPŞIRIQ: Tək bir sual hazırla. Çətinlik çox vacibdir — "{difficulty}" qaydalarına tam riayət et.

QAYDALAR:
- Azərbaycan dilində
- code_read/debug tiplərdə PHP kodu göstər (``` blokunda, maksimum 20 sətir)
- Sualın sonunda 3 bullet ilə nəyi cavablandırmalı olduğunu yaz
- VACİB: bu bullet-lər YALNIZ hansı ASPEKTƏ toxunmaq lazım olduğunu göstərsin (məs. "hansı metoddan istifadə etdiyini", "niyə bu yanaşmanı seçdiyini"). Konkret cavabı (funksiya/metod adları, rule adları, dəqiq sintaksis, düzgün kodu) heç vaxt bullet-lərin içində YAZMA — bu, sualı ifşa edir və tələbə düşünmədən kopyalayır.
- starter/easy üçün: çox sadə, birbaşa, tək anlayış

DƏQIQ FORMAT:
📚 {topic['name']}
{DIFFICULTY_LABELS[difficulty]} | {TYPE_LABELS[q_type]}

❓ [sual mətni]

[kod bloku əgər lazımdırsa]

💡 Cavabında bunları əhatə et:
• [nöqtə 1]
• [nöqtə 2]
• [nöqtə 3]"""

    return ask_claude(prompt)


# ── Cavab qiymətləndirmə ──────────────────────────────────────────────────────
def evaluate_answer(question: str, answer: str, topic: str, difficulty: str, q_type: str) -> dict:
    prompt = f"""Sən Laravel ekspert mentor-san. Tələbənin cavabını qiymətləndir.

Mövzu: {topic}
Çətinlik: {difficulty}
Sual tipi: {q_type}
Sual: {question}
Tələbənin cavabı: {answer}

Qiymətləndirmə qaydaları:
- "correct" (8-10): əsas məqamları düzgün başa düşüb
- "partial" (5-7): qismən düzgün, əskiklik var
- "incorrect" (0-4): əsaslı səhv, boş cavab, və ya mövzudan kənar
- starter/easy suallar üçün: sadə, doğru cavab bəs edir — çox tələbkar olma
- Boş/mövzusuz cavab həmişə incorrect + grade 0

Yalnız JSON cavab ver:
{{
  "score": "correct",
  "grade": 8,
  "feedback": "Azərbaycanca 2-3 cümlə. Nəyi yaxşı etdi, nəyi əskik buraxdı.",
  "missing_points": ["əskik 1", "əskik 2"],
  "correct_answer_hint": "Tam düzgün cavabın qısa xülasəsi",
  "next_step": "Növbəti öyrənmə tövsiyəsi"
}}"""

    text   = ask_claude(prompt)
    result = extract_json(text)
    if result:
        return result
    return {"score": "partial", "grade": 5, "feedback": text, "missing_points": [], "correct_answer_hint": "", "next_step": ""}


# ── Müzakirə (qiymətə etiraz) ─────────────────────────────────────────────────
def process_discussion(message: str) -> str:
    """Cavablanmış sualla bağlı əlavə mesajı (etiraz/əlavə izahat) emal edir."""
    progress = load_json(PROGRESS_FILE)
    history  = progress.get("history", [])
    if not history:
        return "⚠️ Müzakirə ediləcək sual yoxdur. /sual yazaraq yeni sual al."

    entry      = history[-1]
    evaluation = entry.get("evaluation", {})
    discussion = entry.setdefault("discussion", [])

    thread = "\n".join(f"Tələbə: {d['student']}\nMentor: {d['mentor']}" for d in discussion)

    prompt = f"""Sən Laravel ekspert mentor-san. Tələbə əvvəlki sual/cavab/qiymətləndirmənlə bağlı sənə yazıb. Bu HƏMİŞƏ qiymətə etiraz demək deyil — çox vaxt sadəcə əlavə sualdır: "boşluğum harda idi", "düzgün cavab necə olardı", "bunu necə öyrənim", ümumi davam sualı və s.

Mövzu: {entry.get('topic', '')}
Sual: {entry.get('question', '')}
Tələbənin ilk cavabı: {entry.get('answer', '')}
Sənin ilk qiymətləndirmən: {evaluation.get('grade', 5)}/10 ({evaluation.get('score', 'partial')})
İlk rəyin: {evaluation.get('feedback', '')}
Əskik hesab etdiyin məqamlar: {', '.join(evaluation.get('missing_points', [])) or 'yoxdur'}
{f"{chr(10)}Əvvəlki müzakirə:{chr(10)}{thread}" if thread else ""}
Tələbənin yeni mesajı: {message}

TAPŞIRIQ:
1. Əvvəlcə tələbənin NƏ soruşduğunu diqqətlə oxu:
   - Əgər bu sual/izahat istəyidirsə (boşluğunu öyrənmək, düzgün cavabı görmək, növbəti addımı bilmək və s.) — birbaşa, faydalı, mentor kimi cavab ver. Qiymətdən danışmaq MƏCBURI deyil, sual nəyə aiddirsə ona cavab ver.
   - Yalnız tələbə AÇIQ ŞƏKİLDƏ qiymətə etiraz edir və ya haqlı olduğunu sübut etməyə çalışırsa, ilk qiyməti yenidən düşün: həqiqətən haqlıdırsa düzəlt və niyə fikrini dəyişdiyini izah et, deyilsə nəzakətlə amma konkret dəlillərlə izah et.
2. Səmimi, qısa (3-6 cümlə), konkret ol. Təkrar-təkrar "qiyməti dəyişmirəm" demə — yalnız əgər söhbət elə buna görədirsə.
3. Qərəzsiz ol, amma özünə güzəştə getmə.

CAVABINI DƏQİQ BU FORMATDA VER, başqa heç nə yazma:
###META###
{{"grade_changed": false, "new_grade": {evaluation.get('grade', 5)}, "new_score": "{evaluation.get('score', 'partial')}"}}
###CAVAB###
Azərbaycanca tələbəyə birbaşa müraciət, 3-6 cümlə. Bu hissədə dırnaq işarələrini sərbəst istifadə edə bilərsən — JSON deyil, sadə mətndir."""

    text = ask_claude(prompt)
    if "###CAVAB###" in text:
        meta_part, response_text = text.split("###CAVAB###", 1)
        meta = extract_json(meta_part.replace("###META###", ""))
        result = {
            "grade_changed": meta.get("grade_changed", False),
            "new_grade": meta.get("new_grade", evaluation.get("grade", 5)),
            "new_score": meta.get("new_score", evaluation.get("score", "partial")),
            "response": response_text.strip(),
        }
    else:
        result = extract_json(text)
        if not result:
            result = {"grade_changed": False, "new_grade": evaluation.get("grade", 5),
                       "new_score": evaluation.get("score", "partial"), "response": text}

    discussion.append({"student": message, "mentor": result.get("response", "")})

    reply_lines = ["💬 <b>Müzakirə:</b>", "", result.get("response", "")]

    old_grade = evaluation.get("grade", 5)
    new_grade = result.get("new_grade", old_grade)
    if result.get("grade_changed") and new_grade != old_grade:
        difficulty = entry.get("difficulty", "easy")
        streak     = progress.get("streak", 1)
        delta      = calc_xp(new_grade, difficulty, streak) - calc_xp(old_grade, difficulty, streak)

        old_score = evaluation.get("score", "partial")
        new_score = result.get("new_score", old_score)

        # Köhnə snapshot-lar — dəyişikliklərdən ƏVVƏL (level gate-ləri history-dən asılıdır)
        tid          = entry.get("topic_id")
        topic_name   = entry.get("topic", "")
        was_mastered = progress.get("topic_stats", {}).get(tid, {}).get("mastered", False)
        old_lvl_num  = get_player_level(progress)[0]

        progress["xp"] = max(0, progress.get("xp", 0) + delta)
        if new_score != old_score:
            progress["score"][old_score] = max(0, progress["score"].get(old_score, 0) - 1)
            progress["score"][new_score] = progress["score"].get(new_score, 0) + 1

        evaluation["grade"]  = new_grade
        evaluation["score"]  = new_score
        entry["evaluation"]  = evaluation

        # Mövzu statistikası + spaced repetition (düzəldilmiş qiymətlə yenidən qurulur)
        stats = rebuild_topic_stats(progress, tid) if tid else {}

        # Güclü / zəif mövzu siyahıları
        if topic_name:
            strong = progress.setdefault("strong_topics", [])
            weak   = progress.setdefault("weak_topics", [])
            if new_grade >= 8:
                if topic_name not in strong: strong.append(topic_name)
                if topic_name in weak:       weak.remove(topic_name)
            elif new_grade <= 3:
                if topic_name not in weak:   weak.append(topic_name)
                if topic_name in strong:     strong.remove(topic_name)

        # Düzəliş nəticəsində mövzu mənimsənildisə → linear cursor irəli
        if tid and stats.get("mastered") and not was_mastered \
                and entry.get("level_id") == progress.get("current_level"):
            cur_lvl = next((l for l in load_json(ROADMAP_FILE)["levels"]
                            if l["id"] == entry["level_id"]), None)
            if cur_lvl:
                cur_idx = progress.get("current_topic_index", 0)
                if cur_idx < len(cur_lvl["topics"]) and cur_lvl["topics"][cur_idx]["id"] == tid:
                    progress["current_topic_index"] = cur_idx + 1

        # Level (XP + gate) yenidən hesablanır
        new_lvl_num, new_lvl_label, _, _, _ = get_player_level(progress)
        progress["player_level"] = new_lvl_num

        new_badges = check_badges(progress)

        reply_lines += [
            "",
            f"📝 Qiymət düzəldildi: {old_grade}/10 → {new_grade}/10",
            f"⚡ XP fərqi: {'+' if delta >= 0 else ''}{delta}  |  Cəmi: {progress['xp']} XP",
        ]
        if stats and stats.get("mastered") and not was_mastered:
            reply_lines += ["", f"🎓 <b>{topic_name}</b> mənimsənildi! ({topic_mastery_pct(stats)}%)"]
        if new_lvl_num > old_lvl_num:
            reply_lines += ["", f"🎉 <b>LEVEL UP!</b> → {new_lvl_label}"]
        if new_badges:
            reply_lines += ["", "🏆 <b>Yeni badge:</b> " + "  ".join(new_badges)]

    save_json(PROGRESS_FILE, progress)
    return "\n".join(reply_lines)


# ── XP hesablaması ────────────────────────────────────────────────────────────
def calc_xp(grade: int, difficulty: str, streak: int) -> int:
    base     = {10: 120, 9: 110, 8: 100, 7: 70, 6: 55, 5: 40, 4: 20, 3: 15, 2: 10, 1: 5, 0: 0}.get(grade, 0)
    mult     = DIFFICULTY_XP_MULT.get(difficulty, 1.0)
    streak_b = min(streak, 7) * 5
    return round(base * mult) + streak_b


# ── Nəticə formatı ────────────────────────────────────────────────────────────
def format_evaluation(evaluation: dict, progress: dict, streak: int,
                       xp_earned: int, new_badges: list[str],
                       level_up: bool, new_level_label: str) -> str:
    score   = evaluation.get("score", "partial")
    grade   = evaluation.get("grade", 5)
    emoji   = {"correct": "✅", "partial": "🟡", "incorrect": "❌"}[score]
    bar     = "█" * grade + "░" * (10 - grade)

    total_xp = progress.get("xp", 0)
    lvl_num, lvl_label, lvl_xp, lvl_need, gate_missing = get_player_level(progress)
    prog_bar = xp_bar(lvl_xp, lvl_need)

    lines = [f"{emoji} <b>Qiymət: {grade}/10</b>  {bar}"]

    if level_up:
        lines += ["", f"🆙 <b>LEVEL UP! {new_level_label}</b> 🎉"]

    lines += [
        "",
        f"⚡ <b>+{xp_earned} XP</b>  |  Cəmi: {total_xp} XP",
        f"{lvl_label}  {prog_bar}  {lvl_xp}/{lvl_need} XP",
    ]

    if gate_missing:
        lines += ["", "🔒 <b>Level-up qapısı bağlı:</b>"]
        for m in gate_missing: lines.append(f"  • {m}")

    if new_badges:
        lines += ["", "🏆 <b>Yeni badge:</b> " + "  ".join(new_badges)]

    lines += ["", "📝 <b>Rəy:</b>", evaluation.get("feedback", "")]

    missing = evaluation.get("missing_points", [])
    if missing:
        lines += ["", "⚠️ <b>Əskik məqamlar:</b>"]
        for m in missing: lines.append(f"  • {m}")

    hint = evaluation.get("correct_answer_hint", "")
    if hint: lines += ["", "💎 <b>Düzgün cavab:</b>", hint]

    ns = evaluation.get("next_step", "")
    if ns: lines += ["", "🚀 <b>Növbəti addım:</b>", ns]

    streak_str = f"  🔥 {streak} gün streak!" if streak > 1 else ""
    lines += ["", "━━━━━━━━━━━━━━━", f"📅 Gün {progress['day']} | Sual #{progress.get('questions_answered', 0)}{streak_str}"]
    return "\n".join(lines)


# ── Ana funksiyalar ───────────────────────────────────────────────────────────
def cmd_question(args):
    roadmap  = load_json(ROADMAP_FILE)
    progress = load_json(PROGRESS_FILE)
    level, topic, is_review = get_next_topic(roadmap, progress)

    if topic is None:
        send_telegram("🎉 Roadmap tamamlandı! Sən artıq Senior Laravel Developer-sən! 👑")
        return

    topic_stats = progress.get("topic_stats", {}).get(topic["id"], {})
    difficulty  = topic_stats.get("current_difficulty") or "starter"
    q_type      = pick_question_type(topic, progress, difficulty)

    review_tag = " [🔁 review]" if is_review else ""
    print(f"⏳ [{difficulty}] {topic['name']}{review_tag} ({q_type})")
    question = generate_question(progress, level, topic, q_type)

    pending: dict = {
        "date":       datetime.now().strftime("%Y-%m-%d"),
        "day":        progress["day"],
        "level":      level["name"],
        "level_id":   level["id"],
        "topic_id":   topic["id"],
        "topic":      topic["name"],
        "q_type":     q_type,
        "difficulty": difficulty,
        "is_review":  is_review,
        "question":   question,
        "answered":   False,
    }
    if q_type == "trick":
        pending["trick_category"] = progress.pop("_next_trick_category", "")
    progress["pending_question"] = pending
    save_json(PROGRESS_FILE, progress)

    if q_type in ("code_write", "debug"):
        answer_hint = '💻 <b>Kodu buradan yaz:</b> <a href="http://127.0.0.1:8731">http://127.0.0.1:8731</a>'
    else:
        answer_hint = "✍️ Cavabını birbaşa Telegram-a yaz!"

    header = "🔁 <b>Review — köhnə mövzu təkrar</b>" if is_review else f"🎯 <b>Gün {progress['day']} — Laravel Mentor</b>"
    send_telegram(
        f"{header}\n\n"
        f"{question}\n\n"
        f"━━━━━━━━━━━━━━━\n{answer_hint}"
    )
    print("✅ Göndərildi.")


def process_answer(answer: str) -> str:
    """Bot listener və web UI tərəfindən çağırılır."""
    progress = load_json(PROGRESS_FILE)
    pending  = progress.get("pending_question")

    if not pending or pending.get("answered"):
        return "⚠️ Aktiv sual yoxdur. /sual yazaraq yeni sual al."

    evaluation = evaluate_answer(
        pending["question"], answer,
        pending["topic"], pending.get("difficulty", "easy"),
        pending.get("q_type", "theory")
    )

    grade      = evaluation.get("grade", 5)
    difficulty = pending.get("difficulty", "easy")

    # Tarix və streak
    today = datetime.now().strftime("%Y-%m-%d")
    last  = progress.get("last_answer_date")
    streak = progress.get("streak", 0)
    if last:
        delta = (date.today() - date.fromisoformat(last)).days
        if delta == 1:
            streak += 1
        elif delta > 1:
            streak = 1
        # delta == 0 → eyni gün, streak dəyişmir
    else:
        streak = 1

    # Gün sayı: yalnız yeni təqvim günündə artır
    answered_dates = set(progress.get("answered_dates", []))
    is_new_day = today not in answered_dates
    if is_new_day:
        progress["day"] += 1
        answered_dates.add(today)
    progress["answered_dates"] = sorted(answered_dates)

    # Sual sayı (gündən asılı olmayaraq)
    progress["questions_answered"] = progress.get("questions_answered", 0) + 1

    xp_earned = calc_xp(grade, difficulty, streak)
    old_xp    = progress.get("xp", 0)
    new_xp    = old_xp + xp_earned

    # Köhnə level snapshot-u (gate-lər də history-dən asılıdır → dəyişikliklərdən əvvəl)
    old_lvl_num, _, _, _, _ = get_player_level(progress)

    # Progress güncəllə
    pending.update({"answered": True, "answer": answer, "evaluation": evaluation})
    progress["history"].append(pending)
    progress.pop("pending_question", None)
    progress["xp"]               = new_xp
    progress["streak"]           = streak
    progress["last_answer_date"] = today
    progress["score"][evaluation.get("score", "partial")] = \
        progress["score"].get(evaluation.get("score","partial"), 0) + 1

    topic = pending["topic"]
    if grade >= 8:
        if topic not in progress["strong_topics"]: progress["strong_topics"].append(topic)
        if topic in progress.get("weak_topics", []): progress["weak_topics"].remove(topic)
    elif grade <= 3:
        if topic not in progress.get("weak_topics", []): progress.setdefault("weak_topics", []).append(topic)

    progress.setdefault("question_type_history", []).append(pending.get("q_type", "theory"))

    # Per-topic stats + spaced repetition
    tid   = pending.get("topic_id")
    lvlid = pending.get("level_id")
    score_lbl = evaluation.get("score", "partial")
    if tid:
        stats = update_topic_stats(progress, tid, difficulty, grade, score_lbl, today)
        # Cari linear mövzu mastered olsa → linear cursor irəli
        if lvlid == progress["current_level"]:
            roadmap_l = load_json(ROADMAP_FILE)
            cur_lvl   = next((l for l in roadmap_l["levels"] if l["id"] == lvlid), None)
            if cur_lvl:
                cur_idx = progress["current_topic_index"]
                if cur_idx < len(cur_lvl["topics"]) and cur_lvl["topics"][cur_idx]["id"] == tid and stats["mastered"]:
                    progress["current_topic_index"] += 1

    # Yeni level (XP + gate)
    new_lvl_num, new_lvl_label, _, _, _ = get_player_level(progress)
    level_up = new_lvl_num > old_lvl_num
    progress["player_level"] = new_lvl_num

    new_badges = check_badges(progress)
    save_json(PROGRESS_FILE, progress)

    return format_evaluation(
        evaluation, progress, streak,
        xp_earned, new_badges,
        level_up, new_lvl_label
    )


def cmd_answer(args):
    progress = load_json(PROGRESS_FILE)
    pending  = progress.get("pending_question")
    if not pending or pending.get("answered"):
        print("Aktiv sual yoxdur."); return

    print(f"\n{pending['topic']} | {DIFFICULTY_LABELS.get(pending.get('difficulty','easy'))} | {TYPE_LABELS.get(pending.get('q_type','theory'))}")
    print(f"\n{pending['question']}\n")
    print("Cavabını yaz ('DONE' ilə bitir):\n")
    lines = []
    try:
        while True:
            ln = input()
            if ln.strip().upper() == "DONE": break
            lines.append(ln)
    except EOFError: pass

    answer = "\n".join(lines).strip()
    if not answer: print("Boş cavab."); return

    print("\n⏳ Qiymətləndirilir...")
    result = process_answer(answer)
    send_telegram(result)
    print("\n" + result)


def cmd_status(args):
    progress = load_json(PROGRESS_FILE)
    roadmap  = load_json(ROADMAP_FILE)
    level, topic, is_review = get_next_topic(roadmap, progress)
    topic_stats_all = progress.get("topic_stats", {})

    xp      = progress.get("xp", 0)
    score   = progress["score"]
    total   = sum(score.values())
    streak  = progress.get("streak", 0)
    cur_topic_stats = topic_stats_all.get(topic["id"], {}) if topic else {}
    diff    = cur_topic_stats.get("current_difficulty", "starter")

    lvl_num, lvl_label, lvl_xp, lvl_need, gate_missing = get_player_level(progress)
    prog_bar = xp_bar(lvl_xp, lvl_need)
    pct      = round(score.get("correct", 0) / total * 100) if total else 0

    # Roadmap xəritəsi
    all_levels = roadmap["levels"]
    cur_lid    = progress["current_level"]
    road_lines = []
    for lv in all_levels:
        if lv["id"] < cur_lid:
            road_lines.append(f"  ✅ {lv['name']}")
        elif lv["id"] == cur_lid:
            t_idx   = progress["current_topic_index"]
            t_total = len(lv["topics"])
            road_lines.append(f"  ▶️ {lv['name']}  ({t_idx}/{t_total} mövzu)")
        else:
            road_lines.append(f"  ⬜ {lv['name']}")

    # Cari level-də mövzu mastery
    cur_level_obj = next((l for l in all_levels if l["id"] == cur_lid), None)
    mastery_lines = []
    today = date.today().isoformat()
    if cur_level_obj:
        for t in cur_level_obj["topics"]:
            s = topic_stats_all.get(t["id"], {})
            pct_m = topic_mastery_pct(s)
            bar_m = xp_bar(pct_m, 100, width=8)
            mark  = "🏆" if s.get("mastered") else ("🔁" if s.get("next_review_date") and s["next_review_date"] <= today else "  ")
            mastery_lines.append(f"  {mark} {t['name'][:32]:32s}  {bar_m}  {pct_m}%")

    badges = progress.get("badges", [])
    badge_labels = {bid: lbl for bid, lbl, _ in BADGE_CHECKS}
    badge_str = "  ".join(badge_labels.get(b, b) for b in badges) if badges else "hələ yoxdur"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚡ <b>{lvl_label}</b>",
        f"{prog_bar}  {lvl_xp}/{lvl_need} XP",
        f"💰 Cəmi XP: {xp}",
    ]
    if gate_missing:
        lines += ["", "🔒 <b>Növbəti level qapısı:</b>"]
        for m in gate_missing: lines.append(f"  • {m}")
    lines += [
        "",
        "📍 <b>Yol xəritəsi:</b>",
    ] + road_lines + [
        "",
        f"🎯 Növbəti mövzu: <b>{topic['name'] if topic else 'Tamamlandı!'}</b>" + (" 🔁" if is_review else ""),
        f"⚡ Çətinlik: {DIFFICULTY_LABELS.get(diff)}",
    ]
    if mastery_lines:
        lines += ["", f"📈 <b>{cur_level_obj['name']} — mövzu mastery:</b>"] + mastery_lines
    lines += [
        "",
        "📊 <b>Statistika:</b>",
        f"  🗓 Gün: {progress['day']}  📝 Sual: {progress.get('questions_answered', 0)}  🔥 Streak: {streak}",
        f"  ✅ {score.get('correct',0)}  🟡 {score.get('partial',0)}  ❌ {score.get('incorrect',0)}",
        f"  🏆 Uğur: {pct}%",
        "",
        f"🎖 <b>Badge-lər:</b>",
        f"  {badge_str}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    msg = "\n".join(lines)
    send_telegram(msg)
    print(msg)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("question")
    sub.add_parser("answer")
    sub.add_parser("status")
    args = parser.parse_args()
    {"question": cmd_question, "answer": cmd_answer, "status": cmd_status}.get(
        args.command, lambda _: parser.print_help()
    )(args)


if __name__ == "__main__":
    main()
