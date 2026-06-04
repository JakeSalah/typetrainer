#!/usr/bin/env python3
"""
typetrainer — a zero-dependency terminal typing trainer.

Modes
  • Quick test      — 30 words, weak-key targeted
  • Daily Workout   — warm-up → weak-key drill → speed run, builds a streak
  • Weak-key Drill  — hammers the letters you miss most
  • Stats           — progress, trend, weak keys

Clean, calm palette. No animations.
Progress saved locally to ~/.typetrainer/stats.json.

Run:  tt   (or python3 typetrainer.py)
Keys: just type. Backspace fixes. Esc/Ctrl-C backs out. q quits menus.
"""

import curses
import datetime
import json
import os
import random
import time
from pathlib import Path

DATA_DIR = Path.home() / ".typetrainer"
STATS_FILE = DATA_DIR / "stats.json"
WORDS_PER_TEST = 30
HISTORY_KEEP = 200

WORDS = """
the be to of and a in that have it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up out
if about who get which go me when make can like time no just him know take people
into year your good some could them see other than then now look only come its over
think also back after use two how our work first well way even new want because any
these give day most us man find here thing tell very big high small large long little
own under last great old high right different following large because while between
both under house point world place feel still nation hand old life tell write become
here show house both because turn group such begin seem talk where help through much
before move right boy too mean old same tell does set three want air well also play
small end put home read hand port large spell add even land here must big high such
follow act why ask men change went light kind off need picture try us again animal
point mother world near build self earth father head stand own page should country
found answer school grow study still learn plant cover food sun four thought let keep
eye never last door between city tree cross since hard start might story saw far sea
draw left late run press close night real life few stop open seem together next white
children begin got walk example ease paper often always music those both mark book
letter until mile river car feet care second group carry took rain eat room friend
began idea fish mountain north once base hear horse cut sure watch color face wood
main enough plain girl usual young ready above ever red list though feel talk bird
soon body dog family direct pose leave song measure state product black short numeral
class wind question happen complete ship area half rock order fire south problem piece
told knew pass farm top whole king size heard best hour better true during hundred
five remember step early hold west ground interest reach fast verb sing listen six
table travel less morning ten simple several vowel toward war lay against pattern slow
center love person money serve appear road map science rule govern pull cold notice
voice fall power town fine certain fly unit lead cry dark machine note wait plan figure
star box noun field rest correct able pound done beauty drive stood contain front teach
week final gave green oh quick develop sleep warm free minute strong special mind behind
clear tail produce fact street inch lot nothing course stay wheel full force blue object
""".split()


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------
def load_stats():
    try:
        with open(STATS_FILE) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("keys", {})
    s.setdefault("history", [])
    s.setdefault("tests", 0)
    s.setdefault("best_wpm", 0.0)
    s.setdefault("streak", 0)
    s.setdefault("workouts", 0)
    s.setdefault("last_workout", None)
    return s


def save_stats(s):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, STATS_FILE)
    except Exception:
        pass


def weakness_map(stats):
    w = {}
    keys = stats.get("keys", {})
    for c in "abcdefghijklmnopqrstuvwxyz":
        d = keys.get(c, {})
        a, e = d.get("attempts", 0), d.get("errors", 0)
        w[c] = (e + 1.0) / (a + 2.0)
    return w


def choose_words(stats, n=WORDS_PER_TEST, intensity=1.0):
    """Pick n words. intensity 0 = uniform random; higher = stronger weak-key bias."""
    w = weakness_map(stats)
    base = max(w.values()) if w else 1.0

    def score(word):
        letters = [c for c in word.lower() if c.isalpha()]
        if not letters:
            return 0.01
        vals = [w.get(c, base) for c in letters]
        return 0.7 * max(vals) + 0.3 * (sum(vals) / len(vals))

    exp = 4.0 * intensity
    weights = [max(score(word), 1e-6) ** exp for word in WORDS]
    return random.choices(WORDS, weights=weights, k=n)


def weakest_letters(stats, k=6, min_attempts=8):
    keys = stats.get("keys", {})
    rows = []
    for c in "abcdefghijklmnopqrstuvwxyz":
        d = keys.get(c, {})
        a, e = d.get("attempts", 0), d.get("errors", 0)
        if a >= min_attempts:
            rows.append((c, e / a, a))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:k]


# standard touch-typing finger assignment (QWERTY)
FINGER = {
    "q": "left pinky", "a": "left pinky", "z": "left pinky",
    "w": "left ring", "s": "left ring", "x": "left ring",
    "e": "left middle", "d": "left middle", "c": "left middle",
    "r": "left index", "f": "left index", "v": "left index",
    "t": "left index", "g": "left index", "b": "left index",
    "y": "right index", "h": "right index", "n": "right index",
    "u": "right index", "j": "right index", "m": "right index",
    "i": "right middle", "k": "right middle",
    "o": "right ring", "l": "right ring",
    "p": "right pinky",
    " ": "either thumb",
}
HOME_KEYS = {"a", "s", "d", "f", "j", "k", "l"}


def finger_name(ch):
    return FINGER.get(ch.lower(), "—")


def commit_result(stats, r, record_history=True):
    keys = stats["keys"]
    for c, (a, e) in r["key_tally"].items():
        d = keys.setdefault(c, {"attempts": 0, "errors": 0})
        d["attempts"] += a
        d["errors"] += e
    stats["tests"] = stats.get("tests", 0) + 1
    if record_history:
        stats["best_wpm"] = max(stats.get("best_wpm", 0.0), r["wpm"])
        stats["history"].append({"wpm": round(r["wpm"], 1),
                                 "acc": round(r["acc"], 1),
                                 "ts": r["ts"]})
        stats["history"] = stats["history"][-HISTORY_KEEP:]


def update_streak(stats):
    """Returns (streak, already_done_today)."""
    today = datetime.date.today()
    last = stats.get("last_workout")
    streak = stats.get("streak", 0)
    if last == today.isoformat():
        return streak, True
    if last:
        gap = (today - datetime.date.fromisoformat(last)).days
        streak = streak + 1 if gap == 1 else 1
    else:
        streak = 1
    stats["last_workout"] = today.isoformat()
    stats["streak"] = streak
    stats["workouts"] = stats.get("workouts", 0) + 1
    return streak, False


# ---------------------------------------------------------------------------
# colors — one clean, calm palette
# ---------------------------------------------------------------------------
class C:
    CORRECT = 1   # typed correctly
    WRONG = 2     # typed wrong
    PENDING = 3   # not yet typed (read-ahead)
    CURSOR = 4    # current position
    ACCENT = 5    # headings / highlights
    DIM = 6       # labels, footers
    GOOD = 7      # positive numbers
    BAD = 8       # negative / weak


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    if curses.COLORS >= 256:
        curses.init_pair(C.CORRECT, 151, bg)   # soft green
        curses.init_pair(C.WRONG, 210, bg)     # soft red (underlined)
        curses.init_pair(C.PENDING, 245, bg)   # readable grey
        curses.init_pair(C.CURSOR, 235, 110)   # dark text on steel-blue block
        curses.init_pair(C.ACCENT, 110, bg)    # steel blue
        curses.init_pair(C.DIM, 240, bg)       # dim grey
        curses.init_pair(C.GOOD, 151, bg)      # green
        curses.init_pair(C.BAD, 210, bg)       # red
    else:
        curses.init_pair(C.CORRECT, curses.COLOR_GREEN, bg)
        curses.init_pair(C.WRONG, curses.COLOR_RED, bg)
        curses.init_pair(C.PENDING, curses.COLOR_WHITE, bg)
        curses.init_pair(C.CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(C.ACCENT, curses.COLOR_CYAN, bg)
        curses.init_pair(C.DIM, curses.COLOR_WHITE, bg)
        curses.init_pair(C.GOOD, curses.COLOR_GREEN, bg)
        curses.init_pair(C.BAD, curses.COLOR_RED, bg)


def cp(pair):
    return curses.color_pair(pair)


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------
def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try:
            stdscr.addstr(y, x, text[: max(0, w - x)], attr)
        except curses.error:
            pass


def center_x(width, w):
    return max(0, (w - width) // 2)


def sparkline(values):
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    return "".join(blocks[min(7, int((v - lo) / rng * 7))] for v in values)


def layout(words, width):
    lines, line, col, gi = [], [], 0, 0
    for wi, word in enumerate(words):
        if col + len(word) > width and line:
            lines.append(line)
            line, col = [], 0
        for ch in word:
            line.append((gi, ch))
            gi += 1
            col += 1
        if wi < len(words) - 1:
            line.append((gi, " "))
            gi += 1
            col += 1
    if line:
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# the typing test
# ---------------------------------------------------------------------------
def run_test(stdscr, stats, words, header_label="", show_finger=False):
    target = " ".join(words)
    n = len(target)
    state = [None] * n
    idx = keystrokes = correct_keys = 0
    start = None
    key_tally = {}

    stdscr.timeout(100)  # tick so the live clock updates
    while True:
        h, w = stdscr.getmaxyx()
        text_w = max(20, min(w - 8, 64))
        lines = layout(words, text_w)
        x0 = center_x(text_w, w)
        y0 = max(4, h // 2 - len(lines) // 2)

        elapsed = (time.time() - start) if start else 0.0
        minutes = elapsed / 60.0
        wpm = (correct_keys / 5.0 / minutes) if minutes > 0 else 0.0
        acc = (correct_keys / keystrokes * 100.0) if keystrokes else 100.0
        progress = idx / n if n else 0

        stdscr.erase()
        if header_label:
            safe_addstr(stdscr, 1, center_x(len(header_label), w),
                        header_label, cp(C.ACCENT) | curses.A_BOLD)
        hdr = f"{wpm:5.0f} wpm   {acc:5.1f}% acc   {int(progress*100):3d}%"
        safe_addstr(stdscr, 2, center_x(len(hdr), w), hdr, cp(C.DIM))

        # simple two-tone progress bar
        filled = int(text_w * progress)
        safe_addstr(stdscr, 3, x0, "━" * filled, cp(C.ACCENT))
        safe_addstr(stdscr, 3, x0 + filled, "─" * (text_w - filled), cp(C.DIM))

        for li, line in enumerate(lines):
            y = y0 + li
            for col, (gi, ch) in enumerate(line):
                x = x0 + col
                if gi < idx:
                    if state[gi]:
                        safe_addstr(stdscr, y, x, ch, cp(C.CORRECT))
                    else:
                        disp = ch if ch != " " else "_"
                        safe_addstr(stdscr, y, x, disp,
                                    cp(C.WRONG) | curses.A_UNDERLINE)
                elif gi == idx:
                    safe_addstr(stdscr, y, x, ch, cp(C.CURSOR))
                else:
                    safe_addstr(stdscr, y, x, ch, cp(C.PENDING))

        base = y0 + len(lines) + 2
        if show_finger and idx < n:
            tch = target[idx]
            label = "space" if tch == " " else tch
            hint = f"next:  {label}  →  {finger_name(tch)}"
            safe_addstr(stdscr, min(h - 3, base), center_x(len(hint), w),
                        hint, cp(C.ACCENT) | curses.A_BOLD)
            foot_y = min(h - 2, base + 1)
        else:
            foot_y = min(h - 2, base)
        foot = "Backspace to fix  ·  Esc to cancel"
        safe_addstr(stdscr, foot_y, center_x(len(foot), w), foot, cp(C.DIM))
        stdscr.refresh()

        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            return None
        if key == -1:
            continue
        if key == 27:
            return None
        if key == curses.KEY_RESIZE:
            continue
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if idx > 0:
                idx -= 1
                state[idx] = None
            continue
        if 32 <= key <= 126:
            if start is None:
                start = time.time()
            typed = chr(key)
            target_ch = target[idx]
            match = typed == target_ch
            state[idx] = match
            keystrokes += 1
            if match:
                correct_keys += 1
            tc = target_ch.lower()
            if tc.isalpha():
                t = key_tally.setdefault(tc, [0, 0])
                t[0] += 1
                if not match:
                    t[1] += 1
            idx += 1
            if idx >= n:
                break

    elapsed = (time.time() - start) if start else 0.0
    minutes = max(elapsed / 60.0, 1e-6)
    return {
        "wpm": correct_keys / 5.0 / minutes,
        "acc": (correct_keys / keystrokes * 100.0) if keystrokes else 0.0,
        "elapsed": elapsed,
        "keystrokes": keystrokes,
        "correct": correct_keys,
        "key_tally": key_tally,
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# result + summary screens
# ---------------------------------------------------------------------------
def draw_results(stdscr, stats, r):
    is_best = abs(r["wpm"] - stats["best_wpm"]) < 1e-6 and stats["tests"] > 1
    stdscr.timeout(-1)
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    prev = stats["history"][-2]["wpm"] if len(stats["history"]) >= 2 else None
    delta = (r["wpm"] - prev) if prev is not None else None

    y = max(2, h // 2 - 7)
    title = "✓  TEST COMPLETE" + ("    ★ new best" if is_best else "")
    safe_addstr(stdscr, y, center_x(len(title), w), title,
                cp(C.GOOD if is_best else C.ACCENT) | curses.A_BOLD)
    y += 2
    big = f"{r['wpm']:.0f} WPM"
    safe_addstr(stdscr, y, center_x(len(big), w), big, cp(C.ACCENT) | curses.A_BOLD)
    y += 1
    sub = f"{r['acc']:.1f}% accuracy   ·   {r['elapsed']:.1f}s"
    safe_addstr(stdscr, y, center_x(len(sub), w), sub, cp(C.DIM))
    y += 1
    if delta is not None:
        d = f"{'▲' if delta >= 0 else '▼'} {abs(delta):.0f} wpm vs last"
        safe_addstr(stdscr, y, center_x(len(d), w), d,
                    cp(C.GOOD if delta >= 0 else C.BAD))
    y += 2

    hist = [x["wpm"] for x in stats["history"][-40:]]
    if len(hist) >= 2:
        spark = sparkline(hist)
        sx = center_x(len("trend  ") + len(spark), w)
        safe_addstr(stdscr, y, sx, "trend  ", cp(C.DIM))
        safe_addstr(stdscr, y, sx + len("trend  "), spark, cp(C.ACCENT))
        y += 2

    weak = weakest_letters(stats)
    if weak:
        wk = "weak keys → " + "  ".join(f"{c} {(1-rt)*100:.0f}%" for c, rt, _ in weak)
        safe_addstr(stdscr, y, center_x(len(wk), w), wk, cp(C.BAD))
        y += 1
        hint = "(drilled more often next round)"
        safe_addstr(stdscr, y, center_x(len(hint), w), hint, cp(C.DIM))
        y += 2

    foot = "ENTER → again    ·    m → menu    ·    q → quit"
    safe_addstr(stdscr, min(h - 2, y + 1), center_x(len(foot), w), foot, cp(C.DIM))
    stdscr.refresh()
    while True:
        k = stdscr.getch()
        if k in (ord("q"), ord("Q")):
            return "quit"
        if k in (ord("m"), ord("M"), 27):
            return "menu"
        if k in (curses.KEY_ENTER, 10, 13, ord(" ")):
            return "again"


def stats_page(stdscr, stats):
    stdscr.timeout(-1)
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        cx = w // 2
        y = 1
        safe_addstr(stdscr, y, center_x(len("YOUR STATS"), w), "YOUR STATS",
                    cp(C.ACCENT) | curses.A_BOLD)
        y += 2

        hist = stats.get("history", [])
        wpms = [x["wpm"] for x in hist]
        recent = wpms[-10:]
        best = stats.get("best_wpm", 0.0)
        avg = sum(recent) / len(recent) if recent else 0.0
        all_avg = sum(wpms) / len(wpms) if wpms else 0.0

        rows = [
            ("best", f"{best:.0f} wpm"),
            ("recent avg (10)", f"{avg:.0f} wpm"),
            ("all-time avg", f"{all_avg:.0f} wpm"),
            ("tests done", f"{stats.get('tests', 0)}"),
            ("workouts", f"{stats.get('workouts', 0)}"),
            ("streak", f"{stats.get('streak', 0)} days"),
        ]
        col = cx - 18
        for label, val in rows:
            safe_addstr(stdscr, y, col, f"{label:<18}", cp(C.DIM))
            safe_addstr(stdscr, y, col + 18, val, cp(C.GOOD) | curses.A_BOLD)
            y += 1
        y += 1

        if len(wpms) >= 2:
            spark = sparkline(wpms[-min(48, len(wpms)):])
            safe_addstr(stdscr, y, center_x(len("wpm trend"), w), "wpm trend", cp(C.DIM))
            y += 1
            safe_addstr(stdscr, y, center_x(len(spark), w), spark, cp(C.ACCENT))
            y += 2

        weak = weakest_letters(stats, k=8)
        if weak:
            safe_addstr(stdscr, y, center_x(len("weakest keys"), w),
                        "weakest keys", cp(C.BAD))
            y += 1
            for c, rate, attempts in weak:
                acc = (1 - rate) * 100
                barlen = max(0, int(rate * 20))
                bar = "█" * barlen
                line = f"  {c}   {acc:5.1f}%  "
                safe_addstr(stdscr, y, cx - 16, line, cp(C.PENDING))
                safe_addstr(stdscr, y, cx - 16 + len(line), bar, cp(C.BAD))
                safe_addstr(stdscr, y, cx - 16 + len(line) + barlen + 1,
                            f"({attempts})", cp(C.DIM))
                y += 1
        else:
            msg = "type a few tests to unlock weak-key stats"
            safe_addstr(stdscr, y, center_x(len(msg), w), msg, cp(C.DIM))
            y += 1

        foot = "Enter / m / Esc → menu    ·    q → quit"
        safe_addstr(stdscr, min(h - 2, y + 2), center_x(len(foot), w), foot, cp(C.DIM))
        stdscr.refresh()

        k = stdscr.getch()
        if k in (ord("q"), ord("Q")):
            raise SystemExit
        if k in (curses.KEY_ENTER, 10, 13, ord(" "), ord("m"), ord("M"), 27):
            return


def workout_summary(stdscr, stats, results, streak, already):
    stdscr.timeout(-1)
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    y = max(2, h // 2 - 8)
    safe_addstr(stdscr, y, center_x(len("DAILY WORKOUT COMPLETE"), w),
                "DAILY WORKOUT COMPLETE", cp(C.ACCENT) | curses.A_BOLD)
    y += 2
    streak_txt = (f"{streak} day streak" if not already
                  else f"{streak} day streak (already logged today — bonus round!)")
    safe_addstr(stdscr, y, center_x(len(streak_txt), w), streak_txt,
                cp(C.GOOD) | curses.A_BOLD)
    y += 2
    for label, r in results:
        line = f"{label:<16} {r['wpm']:5.0f} wpm   {r['acc']:5.1f}%"
        safe_addstr(stdscr, y, center_x(len(line), w), line, cp(C.ACCENT))
        y += 1
    y += 1
    weak = weakest_letters(stats)
    if weak:
        wk = "still weak → " + "  ".join(c for c, _, _ in weak)
        safe_addstr(stdscr, y, center_x(len(wk), w), wk, cp(C.BAD))
        y += 2
    foot = "ENTER → menu    ·    q → quit"
    safe_addstr(stdscr, min(h - 2, y + 1), center_x(len(foot), w), foot, cp(C.DIM))
    stdscr.refresh()
    while True:
        k = stdscr.getch()
        if k in (ord("q"), ord("Q")):
            return "quit"
        if k in (curses.KEY_ENTER, 10, 13, ord(" "), ord("m"), ord("M"), 27):
            return "menu"


def choose_key_words(keys, stats, n=WORDS_PER_TEST):
    """Generate dense practice for specific keys: real words containing them
    plus synthetic letter-groups so the target keys appear constantly."""
    keyset = [k for k in dict.fromkeys(k.lower() for k in keys) if k.isalpha()]
    if not keyset:
        return choose_words(stats, n)
    kset = set(keyset)
    containing = [wd for wd in WORDS if any(c in kset for c in wd)]
    fillers = "asdfghjkl"  # home-row fillers keep it finger-realistic
    out = []
    for _ in range(n):
        if containing and random.random() < 0.5:
            out.append(random.choice(containing))
        else:
            length = random.randint(3, 5)
            chars = []
            for _ in range(length):
                if random.random() < 0.7:
                    chars.append(random.choice(keyset))
                else:
                    chars.append(random.choice(fillers))
            out.append("".join(chars))
    return out


def pick_keys_screen(stdscr, stats):
    """Let the user type which letters to drill. Returns the string or None."""
    buf = []
    stdscr.timeout(-1)
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        y = max(1, h // 2 - 7)
        safe_addstr(stdscr, y, center_x(len("KEY TRAINER"), w), "KEY TRAINER",
                    cp(C.ACCENT) | curses.A_BOLD)
        y += 2
        prompt = "type the letters you want to drill"
        safe_addstr(stdscr, y, center_x(len(prompt), w), prompt, cp(C.DIM))
        y += 2
        shown = "  ".join(buf) if buf else "…"
        safe_addstr(stdscr, y, center_x(max(len(shown), 1), w), shown,
                    cp(C.CORRECT) | curses.A_BOLD)
        y += 2
        # live finger reference for the chosen keys
        for c in buf:
            star = "  (home)" if c in HOME_KEYS else ""
            line = f"{c}  →  {finger_name(c)}{star}"
            safe_addstr(stdscr, y, center_x(24, w), line, cp(C.PENDING))
            y += 1
        y += 1
        tip1 = "Tab = use my weak keys   ·   Backspace = delete"
        tip2 = "Enter = start   ·   Esc = back"
        safe_addstr(stdscr, min(h - 3, y), center_x(len(tip1), w), tip1, cp(C.DIM))
        safe_addstr(stdscr, min(h - 2, y + 1), center_x(len(tip2), w), tip2, cp(C.DIM))
        stdscr.refresh()

        k = stdscr.getch()
        if k == 27:  # Esc
            return None
        if k in (curses.KEY_ENTER, 10, 13):
            if buf:
                return "".join(buf)
            continue
        if k == 9:  # Tab -> autofill weak keys
            buf = [c for c, _, _ in weakest_letters(stats, k=5)]
            continue
        if k in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
            continue
        if 65 <= k <= 90 or 97 <= k <= 122:  # a letter
            ch = chr(k).lower()
            if ch not in buf:
                buf.append(ch)


def key_trainer(stdscr, stats):
    keys = pick_keys_screen(stdscr, stats)
    if not keys:
        return
    label = "KEY TRAINER  [ " + " ".join(keys) + " ]"
    while True:
        words = choose_key_words(keys, stats, WORDS_PER_TEST)
        r = run_test(stdscr, stats, words, label, show_finger=True)
        if r is None:
            return
        commit_result(stats, r, record_history=False)  # targeted drills don't skew trend
        save_stats(stats)
        action = draw_results(stdscr, stats, r)
        if action == "quit":
            raise SystemExit
        if action == "menu":
            return


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------
def quick_test(stdscr, stats):
    while True:
        words = choose_words(stats, WORDS_PER_TEST, intensity=1.0)
        r = run_test(stdscr, stats, words, "QUICK TEST")
        if r is None:
            return
        commit_result(stats, r, record_history=True)
        save_stats(stats)
        action = draw_results(stdscr, stats, r)
        if action == "quit":
            raise SystemExit
        if action == "menu":
            return


def weak_drill(stdscr, stats):
    while True:
        words = choose_words(stats, WORDS_PER_TEST, intensity=3.0)
        r = run_test(stdscr, stats, words, "WEAK-KEY DRILL", show_finger=True)
        if r is None:
            return
        commit_result(stats, r, record_history=False)  # drills don't skew the trend
        save_stats(stats)
        action = draw_results(stdscr, stats, r)
        if action == "quit":
            raise SystemExit
        if action == "menu":
            return


def daily_workout(stdscr, stats):
    stages = [
        ("WARM-UP", 20, 0.2),
        ("WEAK-KEY DRILL", 25, 3.0),
        ("SPEED RUN", 30, 1.0),
    ]
    results = []
    for i, (label, count, intensity) in enumerate(stages):
        words = choose_words(stats, count, intensity)
        r = run_test(stdscr, stats, words, f"{label}   ({i+1}/{len(stages)})",
                     show_finger=(label == "WEAK-KEY DRILL"))
        if r is None:
            return
        commit_result(stats, r, record_history=(label == "SPEED RUN"))
        save_stats(stats)
        results.append((label, r))
    streak, already = update_streak(stats)
    save_stats(stats)
    action = workout_summary(stdscr, stats, results, streak, already)
    if action == "quit":
        raise SystemExit


# ---------------------------------------------------------------------------
# menu
# ---------------------------------------------------------------------------
def draw_menu(stdscr, stats, sel):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    title = "TYPE TRAINER"
    safe_addstr(stdscr, max(1, h // 2 - 8), center_x(len(title), w), title,
                cp(C.ACCENT) | curses.A_BOLD)

    today = datetime.date.today().isoformat()
    done_today = stats.get("last_workout") == today
    best = stats.get("best_wpm", 0.0)
    streak = stats.get("streak", 0)
    recent = stats.get("history", [])[-10:]
    avg = sum(x["wpm"] for x in recent) / len(recent) if recent else 0.0

    line1 = f"best {best:.0f} wpm   ·   recent avg {avg:.0f} wpm   ·   {streak} day streak"
    safe_addstr(stdscr, h // 2 - 5, center_x(len(line1), w), line1, cp(C.DIM))
    weak = weakest_letters(stats)
    if weak:
        wk = "weak keys → " + "  ".join(c for c, _, _ in weak)
        safe_addstr(stdscr, h // 2 - 4, center_x(len(wk), w), wk, cp(C.BAD))

    items = [
        ("Daily Workout" + ("   ✓ done today" if done_today else "   ◷ pending"),
         "warm-up → weak-key drill → speed run"),
        ("Quick Test", "30 words, weak-key targeted"),
        ("Weak-key Drill", "hammer the letters you miss most"),
        ("Key Trainer", "pick specific keys + see the right finger"),
        ("Stats", "your progress, trend, and weak keys"),
        ("Quit", ""),
    ]
    y = h // 2 - 1
    for i, (label, desc) in enumerate(items):
        selected = i == sel
        prefix = "▶ " if selected else "  "
        text = prefix + label
        x = center_x(28, w)
        attr = (cp(C.ACCENT) | curses.A_BOLD) if selected else cp(C.PENDING)
        safe_addstr(stdscr, y, x, text, attr)
        if selected and desc:
            safe_addstr(stdscr, y + 1, center_x(len(desc), w), desc, cp(C.DIM))
        y += 2

    foot = "↑/↓ move · Enter select · q quit"
    safe_addstr(stdscr, min(h - 2, y + 1), center_x(len(foot), w), foot, cp(C.DIM))
    stdscr.refresh()


def app(stdscr):
    curses.curs_set(0)
    init_colors()
    stats = load_stats()
    sel = 0
    actions = [daily_workout, quick_test, weak_drill, key_trainer, stats_page, None]

    stdscr.timeout(-1)
    while True:
        draw_menu(stdscr, stats, sel)
        k = stdscr.getch()
        if k in (ord("q"), ord("Q")):
            return
        if k in (curses.KEY_UP, ord("k")):
            sel = (sel - 1) % len(actions)
        elif k in (curses.KEY_DOWN, ord("j")):
            sel = (sel + 1) % len(actions)
        elif k in (curses.KEY_ENTER, 10, 13, ord(" ")):
            if actions[sel] is None:
                return
            try:
                actions[sel](stdscr, stats)
            except SystemExit:
                return
        elif ord("1") <= k <= ord("6"):
            sel = k - ord("1")


def main():
    try:
        curses.wrapper(app)
    except KeyboardInterrupt:
        pass
    print("nice work — progress saved to", STATS_FILE)


if __name__ == "__main__":
    main()
