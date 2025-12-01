"""
Export utilities for generating CSV, Markdown, summaries, and ffmpeg-friendly JSON.
"""

import csv
import io
import json
import re
from typing import List, Dict, Any


# -------------------------------
# SRT → ffmpeg JSON
# -------------------------------


def srt_to_ffmpeg_json(srt_text: str) -> str:
    """
    Parse a .srt subtitle file and export ffmpeg-friendly JSON.

    Output format:
    [
        {"index": 1, "label": "SRT_CLIP_1", "start": "HH:MM:SS.mmm", "end": "HH:MM:SS.mmm"},
        ...
    ]
    """
    ts_re = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
    )

    clips: List[Dict[str, Any]] = []
    idx = 0

    for line in srt_text.splitlines():
        m = ts_re.search(line)
        if not m:
            continue

        idx += 1
        sh, sm, ss, sms, eh, em, es, ems = m.groups()
        start = f"{sh}:{sm}:{ss}.{sms}"
        end = f"{eh}:{em}:{es}.{ems}"

        clips.append({
            "index": idx,
            "label": f"SRT_CLIP_{idx}",
            "start": start,
            "end": end,
        })

    return json.dumps(clips, indent=2)


# -------------------------------
# Catholic Cuts → ffmpeg JSON
# -------------------------------


def to_ffmpeg_json(moments_with_cuts: List[Dict[str, Any]]) -> str:
    """Export moments as ffmpeg-friendly JSON for auto-clipping."""

    def normalize_timestamp(ts: str) -> str:
        # Accepts MM:SS.xx or HH:MM:SS.xx → return HH:MM:SS.xx
        parts = ts.strip().split(":")
        if len(parts) == 2:
            h = 0
            m, s = parts
        elif len(parts) == 3:
            h, m, s = parts
        else:
            return ts
        try:
            h = int(h)
            m = int(m)
            s = float(s)
        except Exception:
            return ts
        return f"{h:02d}:{m:02d}:{s:05.2f}"

    def timestamp_to_seconds(ts: str) -> float:
        """Convert timestamp string to seconds."""
        parts = ts.strip().split(":")
        try:
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            elif len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    def seconds_to_timestamp(secs: float) -> str:
        """Convert seconds to HH:MM:SS.xx format."""
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:05.2f}"

    ffmpeg_clips = []
    for idx, moment in enumerate(moments_with_cuts, 1):
        cut_sheet = moment.get("editor_cut_sheet") or {}
        label = cut_sheet.get("clip_label") or f"CLIP_{idx}"

        # PRIORITY: Use editor cut sheet in_point FIRST, fall back to timestamps start
        in_point = cut_sheet.get("in_point", "").strip()

        if in_point:
            start_raw = in_point
        else:
            # Fall back to timestamps field
            timestamps = (moment.get("timestamps") or "").strip()
            match = re.match(r"([0-9:.]+)[\-–]([0-9:.]+)", timestamps)
            if not match:
                continue
            start_raw, _ = match.groups()

        # Convert start to seconds
        start_sec = timestamp_to_seconds(normalize_timestamp(start_raw))

        # PRIMARY: Calculate end_sec = start + duration + 2.0 (follows QUOTE length, not token timestamps)
        clip_duration = moment.get("clip_duration_seconds")
        if not clip_duration or clip_duration <= 0:
            # If no duration, must fall back to timestamps/out_point
            out_point = cut_sheet.get("out_point", "").strip()
            if out_point:
                end_sec = timestamp_to_seconds(normalize_timestamp(out_point))
            else:
                timestamps = (moment.get("timestamps") or "").strip()
                match = re.match(r"([0-9:.]+)[\-–]([0-9:.]+)", timestamps)
                if not match:
                    continue
                _, end_raw = match.groups()
                end_sec = timestamp_to_seconds(normalize_timestamp(end_raw))
        else:
            # Use duration + 4.0 second buffer (follows quote length, runs long not short)
            # IGNORE timestamps/out_point - they are unreliable and cause clips to end too early
            end_sec = start_sec + clip_duration + 4.0

        # Convert back to timestamp strings
        start = seconds_to_timestamp(start_sec)
        end = seconds_to_timestamp(end_sec)

        ffmpeg_clips.append({
            "index": idx,
            "label": label,
            "start": start,
            "end": end,
        })

    return json.dumps(ffmpeg_clips, indent=2)


# -------------------------------
# CSV Export
# -------------------------------


def to_csv(moments_with_cuts: List[Dict[str, Any]]) -> str:
    """Convert moments with cut sheets to CSV format."""
    if not moments_with_cuts:
        return ""

    output = io.StringIO()

    fieldnames = [
        "clip_id", "clip_label", "timestamps", "quote", "clip_duration_seconds",
        "viral_trigger", "why_it_hits", "energy_tag", "flags",
        "historian_caption", "thomist_caption", "ex_protestant_caption",
        "meme_catholic_caption", "old_world_catholic_caption", "catholic_caption",
        "in_point", "out_point", "aspect_ratio", "crop_note",
        "opening_hook_subtitle", "emphasis_words_caps", "pacing_note",
        "b_roll_ideas", "text_on_screen_idea", "silence_handling",
        "thumbnail_text", "thumbnail_face_cue", "platform_priority",
        "use_persona_caption",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for moment in moments_with_cuts:
        cut = moment.get("editor_cut_sheet", {}) or {}
        personas = moment.get("persona_captions", {}) or {}

        row = {
            "clip_id": moment.get("id", ""),
            "clip_label": cut.get("clip_label", ""),
            "timestamps": moment.get("timestamps", ""),
            "quote": moment.get("quote", ""),
            "clip_duration_seconds": moment.get("clip_duration_seconds", ""),
            "viral_trigger": moment.get("viral_trigger", ""),
            "why_it_hits": moment.get("why_it_hits", ""),
            "energy_tag": moment.get("energy_tag", ""),
            "flags": "; ".join(moment.get("flags", [])),
            "historian_caption": personas.get("historian", ""),
            "thomist_caption": personas.get("thomist", ""),
            "ex_protestant_caption": personas.get("ex_protestant", ""),
            "meme_catholic_caption": personas.get("meme_catholic", ""),
            "old_world_catholic_caption": personas.get("old_world_catholic", ""),
            "catholic_caption": personas.get("catholic", ""),
            "in_point": cut.get("in_point", ""),
            "out_point": cut.get("out_point", ""),
            "aspect_ratio": cut.get("aspect_ratio", ""),
            "crop_note": cut.get("crop_note", ""),
            "opening_hook_subtitle": cut.get("opening_hook_subtitle", ""),
            "emphasis_words_caps": "; ".join(cut.get("emphasis_words_caps", [])),
            "pacing_note": cut.get("pacing_note", ""),
            "b_roll_ideas": cut.get("b_roll_ideas", ""),
            "text_on_screen_idea": cut.get("text_on_screen_idea", ""),
            "silence_handling": cut.get("silence_handling", ""),
            "thumbnail_text": cut.get("thumbnail_text", ""),
            "thumbnail_face_cue": cut.get("thumbnail_face_cue", ""),
            "platform_priority": cut.get("platform_priority", ""),
            "use_persona_caption": cut.get("use_persona_caption", ""),
        }

        writer.writerow(row)

    return output.getvalue()


# -------------------------------
# Markdown Export
# -------------------------------


def to_markdown(moments_with_cuts: List[Dict[str, Any]]) -> str:
    """Convert moments with cut sheets to Markdown format."""
    if not moments_with_cuts:
        return "# Viral Clips\n\nNo clips found."

    lines = ["# Viral Clips", "", f"Generated {len(moments_with_cuts)} clips for editing.", ""]

    for i, moment in enumerate(moments_with_cuts, 1):
        cut = moment.get("editor_cut_sheet", {}) or {}
        personas = moment.get("persona_captions", {}) or {}

        clip_label = cut.get("clip_label", f"CLIP_{i}")
        lines.append(f"## Clip {i} – {clip_label}")
        lines.append("")
        lines.append(f"- **Timestamps:** {moment.get('timestamps', 'N/A')}")
        lines.append(f"- **Duration:** {moment.get('clip_duration_seconds', 'N/A')} seconds")
        lines.append(f"- **Trigger:** {moment.get('viral_trigger', 'N/A')}")
        lines.append(f"- **Energy:** {moment.get('energy_tag', 'N/A')}")
        flags = moment.get("flags", [])
        if flags:
            lines.append(f"- **Flags:** {', '.join(flags)}")
        lines.append("")

        quote = moment.get("quote", "")
        if quote:
            lines.append("**Quote:**")
            for l in quote.splitlines():
                lines.append(f"> {l}")
            lines.append("")

        why = moment.get("why_it_hits", "")
        if why:
            lines.append("**Why it hits:**")
            for l in why.splitlines():
                lines.append(f"> {l}")
            lines.append("")

        lines.append("**Persona Captions:**")
        for key, name in [
            ("historian", "Historian"),
            ("thomist", "Thomist"),
            ("ex_protestant", "Ex-Protestant"),
            ("meme_catholic", "Meme Catholic"),
            ("old_world_catholic", "Old World Catholic"),
            ("catholic", "Catholic"),
        ]:
            lines.append(f"- {name}: {personas.get(key, '')}")
        lines.append("")

        lines.append("**Editor Cut Sheet:**")
        lines.append(f"- **In Point:** {cut.get('in_point', 'N/A')}")
        lines.append(f"- **Out Point:** {cut.get('out_point', 'N/A')}")
        lines.append(f"- **Aspect Ratio:** {cut.get('aspect_ratio', '9:16')}")
        lines.append(f"- **Crop Note:** {cut.get('crop_note', 'N/A')}")
        lines.append(f"- **Opening Hook Subtitle:** {cut.get('opening_hook_subtitle', 'N/A')}")
        emphasis_words = cut.get("emphasis_words_caps", [])
        lines.append(
            f"- **Emphasis Words (ALL CAPS):** {', '.join(emphasis_words) if emphasis_words else 'None specified'}"
        )
        lines.append(f"- **Pacing Note:** {cut.get('pacing_note', 'N/A')}")
        lines.append(f"- **B-Roll Ideas:** {cut.get('b_roll_ideas', 'none')}")
        lines.append(f"- **Text on Screen Idea:** {cut.get('text_on_screen_idea', 'none')}")
        lines.append(f"- **Silence Handling:** {cut.get('silence_handling', 'none')}")
        lines.append(f"- **Thumbnail Text:** {cut.get('thumbnail_text', 'N/A')}")
        lines.append(f"- **Thumbnail Face Cue:** {cut.get('thumbnail_face_cue', 'N/A')}")
        lines.append(f"- **Platform Priority:** {cut.get('platform_priority', 'All')}")
        lines.append(f"- **Use Persona Caption:** {cut.get('use_persona_caption', 'N/A')}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# -------------------------------
# Summary
# -------------------------------


def format_clip_summary(moments_with_cuts: List[Dict[str, Any]]) -> str:
    """Generate a brief summary of clips."""
    if not moments_with_cuts:
        return "No clips generated."

    total = len(moments_with_cuts)
    triggers: Dict[str, int] = {}
    flagged = 0

    for m in moments_with_cuts:
        t = m.get("viral_trigger", "Unknown")
        triggers[t] = triggers.get(t, 0) + 1
        if m.get("flags"):
            flagged += 1

    parts = [f"Generated **{total}** viral clips"]

    if triggers:
        parts.append("Triggers: " + ", ".join(f"{count} {name}" for name, count in triggers.items()))

    if flagged:
        parts.append(f"{flagged} clips have special flags")

    return " • ".join(parts)