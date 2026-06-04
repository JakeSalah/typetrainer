# typetrainer

A zero-dependency terminal typing trainer with a clean, calm palette. Built to
improve typing speed during downtime — it learns the keys you miss most and
feeds them back to you, and shows the correct finger for every key.

```
┌─ TYPE TRAINER ────────────────────────────────┐
   best 62 wpm · recent avg 58 wpm · 4 day streak
   weak keys → l  b  v  k

   ▶ Daily Workout    ✓ done today
     Quick Test
     Weak-key Drill
     Key Trainer
     Stats
     Quit
└────────────────────────────────────────────────┘
```

## Features

- **Weak-key targeting** — every miss is tallied per letter; upcoming words are
  biased toward your weakest keys (keybr-style adaptive drilling).
- **Modes**
  - **Daily Workout** — warm-up → weak-key drill → speed run, builds a daily streak.
  - **Quick Test** — 30 words, weak-key targeted.
  - **Weak-key Drill** — hammers the letters you miss most.
  - **Key Trainer** — pick the exact keys to drill (or auto-fill your weak keys).
  - **Stats** — best / recent / all-time WPM, trend sparkline, weak-key bars.
- **Finger guidance** — shows the correct touch-typing finger for each key, live
  during drills and when picking keys.
- **Local progress** — everything saves to `~/.typetrainer/stats.json`. Portable,
  atomic writes, survives across sessions.
- **No dependencies** — pure Python standard library (`curses`). No `pip install`.

## Requirements

- Python 3.8+ (uses only the standard library)
- A terminal with 256-color support recommended (falls back to 8 colors)

## Run

```sh
python3 typetrainer.py
```

Or use the launcher:

```sh
./tt
```

### Make it global (optional)

Symlink the launcher into a directory on your `PATH`:

```sh
ln -sf "$PWD/tt" ~/.local/bin/tt   # then run `tt` from anywhere
```

## Keys

- Just type. Correct letters are green, mistakes red (underlined).
- **Backspace** fixes a mistake.
- **Esc** cancels a test / backs out of a screen.
- In menus: **↑/↓** (or `j`/`k`) to move, **Enter** to select, number keys to jump,
  **q** to quit.

## How weak-key targeting works

Each letter keeps a Laplace-smoothed error rate. Word selection scores every
candidate word by its weakest letter (blended with the average) and samples
words weighted toward your problem keys, so practice naturally concentrates
where you need it. Targeted drills don't skew your speed trend — only Quick
Tests and the workout's speed run are recorded to history.

## License

MIT
