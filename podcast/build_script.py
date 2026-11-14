#!/usr/bin/env python3
"""Build the podcast script deliverables from podcast/src/*.txt.

Source markup (one item per line, blank lines ignored):
  ## title | location      section heading (producer only, never spoken)
  > note                   producer note (never spoken)
  [[pause N]]              silence of N seconds (producer cue)
  anything else            one narration paragraph = one TTS segment

Outputs (in podcast/):
  script.md        full script: narration separated from producer cues, with time cues
  narration.txt    spoken text only, one paragraph per line (safe to paste into a TTS tool)
  segments.json    ordered segments with pause lengths, for automated rendering

Timing is an ESTIMATE unless --durations <json> (segment id -> seconds, measured
from rendered audio) is given.
"""
import argparse
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CPS = 13.5            # assumed Thai speaking rate: characters per second, spaces excluded
GAP_PARAGRAPH = 0.5   # seconds of silence between paragraphs
GAP_SECTION = 1.0     # seconds of silence before a new section


def parse():
    sections = []
    for path in sorted(glob.glob(os.path.join(HERE, "src", "*.txt"))):
        for raw in open(path, encoding="utf-8"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("## "):
                title, _, where = line[3:].partition("|")
                sections.append({"title": title.strip(), "where": where.strip(),
                                 "notes": [], "items": []})
            elif line.startswith(">"):
                sections[-1]["notes"].append(line[1:].strip())
            else:
                m = re.fullmatch(r"\[\[pause (\d+(?:\.\d+)?)\]\]", line)
                if m:
                    sections[-1]["items"].append(("pause", float(m.group(1))))
                else:
                    sections[-1]["items"].append(("say", line))
    return sections


def est(text):
    return len(re.sub(r"\s", "", text)) / CPS


def clock(t):
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--durations", help="JSON of measured segment durations")
    args = ap.parse_args()
    measured = json.load(open(args.durations)) if args.durations else None

    sections = parse()
    segments, t, n = [], 0.0, 0
    md, narr = [], []
    kind = "วัดจากไฟล์เสียงที่เรนเดอร์แล้ว" if measured else "ค่าประมาณ (ยังไม่ได้เรนเดอร์เสียง)"

    body = []
    toc = []
    for si, sec in enumerate(sections):
        if si:
            t += GAP_SECTION
            segments.append({"type": "pause", "seconds": GAP_SECTION})
        start = t
        out = [f"## {sec['title']}", ""]
        out.append(f"**เปิดเอกสารที่:** {sec['where']}" if sec["where"] else "")
        out.append("")
        out.append("<details><summary>โน้ตผู้ผลิต (ไม่อ่านออกเสียง)</summary>")
        out.append("")
        out += [f"- {x}" for x in sec["notes"]]
        out += ["", "</details>", ""]
        prev_say = False
        for typ, val in sec["items"]:
            if typ == "pause":
                out += [f"> ⏸ **คิว (ไม่อ่าน):** เว้นเงียบ {val:g} วินาที ให้ผู้ฟังลองตอบ", ""]
                segments.append({"type": "pause", "seconds": val})
                t += val
                prev_say = False
                continue
            if prev_say:
                t += GAP_PARAGRAPH
                segments.append({"type": "pause", "seconds": GAP_PARAGRAPH})
            n += 1
            sid = f"s{n:03d}"
            dur = measured[sid] if measured else est(val)
            out += [f"`[{clock(t)}]` `{sid}`", "", val, ""]
            narr.append(val)
            segments.append({"type": "say", "id": sid, "section": sec["title"],
                             "text": val, "start": round(t, 1), "seconds": round(dur, 1)})
            t += dur
            prev_say = True
        toc.append((clock(start), sec["title"], sec["where"], t - start))
        out[0] = f"## [{clock(start)}] {sec['title']}"
        body += out
    total = t
    chars = sum(len(re.sub(r"\s", "", x)) for x in narr)

    md += ["# Direct Shear Test จากศูนย์ ถึงอ่านผลแล็บเป็น", "",
           "สคริปต์พอดแคสต์ภาษาไทยแบบเต็มคำพูด อิง ASTM D3080/D3080M‑11 "
           "(ตรวจจากหัวกระดาษของไฟล์ต้นฉบับ แม้ชื่อไฟล์ลงท้าย ‑04)", "",
           f"- **ความยาวรวม:** {clock(total)} นาที — {kind}",
           f"- **จำนวนช่วงพูด:** {n} ช่วง, {chars:,} อักขระ (ไม่นับช่องว่าง)"]
    if not measured:
        md += [f"- **สมมติฐานเวลา:** อัตราพูด {CPS:g} อักขระต่อวินาที, เว้น {GAP_PARAGRAPH:g} วินาทีระหว่างย่อหน้า, "
               f"{GAP_SECTION:g} วินาทีระหว่างหัวข้อ, และ 5–6 วินาทีหลัง “ลองตอบก่อนนะคะ” ในควิซ "
               "เวลาจริงขึ้นกับเสียงและความเร็วของระบบสร้างเสียงที่ใช้ (ถ้าเสียงพูด 12.5–14.5 อักขระต่อวินาที ความยาวรวมจะอยู่ราว 49–56 นาที)"]
    md += ["- **เสียงที่ต้องการ:** ผู้หญิงไทยหนึ่งคน สำเนียงไทยกลาง เสียงเดียวตลอดตอน น้ำเสียงวิศวกรพาเดินดูแล็บ", "",
           "## วิธีใช้ไฟล์ชุดนี้", "",
           "- ข้อความที่ **อ่านออกเสียง** คือย่อหน้าธรรมดาใต้รหัสเวลา `[นาที:วินาที]` เท่านั้น "
           "ตัวเลข หน่วย เลขข้อ และชื่อมาตรฐานเขียนเป็นคำอ่านไว้แล้ว เพื่อให้ระบบสร้างเสียงออกเสียงชัดและไม่เว้นระหว่างตัวเลขกับหน่วย",
           "- หัวข้อ, บรรทัด “เปิดเอกสารที่”, กล่อง “โน้ตผู้ผลิต”, รหัสเวลา และบรรทัด “⏸ คิว” **ไม่อ่านออกเสียง**",
           "- `narration.txt` มีเฉพาะคำพูด หนึ่งย่อหน้าต่อหนึ่งบรรทัด (หนึ่งบรรทัด = หนึ่งความคิด ให้สร้างเสียงทีละบรรทัดโดยไม่ตัดกลางบรรทัด)",
           "- `segments.json` เรียงช่วงพูดและช่วงเงียบตามลำดับ พร้อมความยาวช่วงเงียบ สำหรับเรนเดอร์อัตโนมัติ",
           "- เว้นยาวเฉพาะในควิซ จุดอื่นเว้นสั้นตามค่าใน `segments.json`", "",
           "## สารบัญและคิวเวลา", "",
           "| เริ่ม | ช่วง | เปิดเอกสารที่ | ยาว (นาที) |", "|---|---|---|---|"]
    md += [f"| {c} | {ti} | {w} | {d / 60:.1f} |" for c, ti, w, d in toc]
    md += ["", "---", ""] + body

    out = lambda name: os.path.join(HERE, name)
    open(out("script.md"), "w", encoding="utf-8").write("\n".join(md).rstrip() + "\n")
    open(out("narration.txt"), "w", encoding="utf-8").write("\n".join(narr) + "\n")
    json.dump({"timing": "measured" if measured else "estimated",
               "total_seconds": round(total, 1), "segments": segments},
              open(out("segments.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"total {clock(total)}  segments {n}  chars {chars}")
    for c, ti, w, d in toc:
        print(f"  {c}  {d / 60:4.1f} min  {ti}")


if __name__ == "__main__":
    main()
