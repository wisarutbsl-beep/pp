#!/usr/bin/env python3
"""Render podcast/segments.json to an MP3 with the free Google Translate Thai voice.

One female voice throughout. Each narration paragraph is split only at spaces
(Thai phrase boundaries), never inside a phrase, number or unit. Silences come
from segments.json, so the only long pauses are the quiz pauses.

Usage: render_audio.py <workdir> <out.mp3> [--tempo 1.3]
Writes <workdir>/durations.json (segment id -> seconds, after tempo) for
build_script.py --durations.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
import wave

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 24000
MAX_CHARS = 190      # the endpoint rejects requests somewhat above 200 characters
JOIN_GAP = 0.10      # seconds between chunks of the same paragraph (pre-tempo)


def chunks(text):
    out, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > MAX_CHARS:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
        assert len(cur) <= MAX_CHARS, f"phrase too long to keep whole: {cur[:40]}"
    return out + [cur]


def fetch(text, work):
    """Return trimmed 24 kHz mono PCM for one chunk (cached on disk)."""
    key = hashlib.sha1(text.encode()).hexdigest()[:16]
    mp3, wav = os.path.join(work, key + ".mp3"), os.path.join(work, key + ".wav")
    if not os.path.exists(mp3):
        for attempt in range(5):
            try:
                r = requests.get("https://translate.google.com/translate_tts",
                                 params={"ie": "UTF-8", "q": text, "tl": "th", "client": "tw-ob"},
                                 headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
                r.raise_for_status()
                open(mp3, "wb").write(r.content)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
        time.sleep(0.4)
    if not os.path.exists(wav):
        trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ac", "1", "-ar", str(RATE),
                        "-af", f"{trim},areverse,{trim},areverse", wav], check=True)
    with wave.open(wav) as w:
        return w.readframes(w.getnframes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("out")
    ap.add_argument("--tempo", type=float, default=1.3)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    segs = json.load(open(os.path.join(HERE, "segments.json"), encoding="utf-8"))["segments"]
    silence = lambda sec: b"\0\0" * int(round(sec * RATE))

    raw = os.path.join(a.work, "all.wav")
    durations, stats = {}, []
    with wave.open(raw, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        for s in segs:
            if s["type"] == "pause":
                # pre-stretch so the pause has its nominal length after the tempo change
                w.writeframes(silence(s["seconds"] * a.tempo))
                continue
            n = 0
            for i, c in enumerate(chunks(s["text"])):
                pcm = fetch(c, a.work)
                sec = len(pcm) / 2 / RATE
                stats.append((s["id"], len(c.replace(" ", "")), sec))
                if i:
                    w.writeframes(silence(JOIN_GAP)); n += int(JOIN_GAP * RATE)
                w.writeframes(pcm); n += len(pcm) // 2
            durations[s["id"]] = round(n / RATE / a.tempo, 2)
            print(s["id"], durations[s["id"]], flush=True)

    json.dump(durations, open(os.path.join(a.work, "durations.json"), "w"))
    json.dump(stats, open(os.path.join(a.work, "chunk_stats.json"), "w"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw,
                    "-af", f"atempo={a.tempo},loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", str(RATE), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k",
                    "-metadata", "title=Direct Shear Test จากศูนย์ ถึงอ่านผลแล็บเป็น",
                    "-metadata", "album=ASTM D3080/D3080M-11", "-metadata", "genre=Podcast",
                    a.out], check=True)


if __name__ == "__main__":
    main()
