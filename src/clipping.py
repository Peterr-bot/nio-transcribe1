import ffmpeg
import json
from pathlib import Path

def cut_video(input_video: str, start: str, end: str, output_path: str) -> None:
    """
    Cut a segment from input_video into output_path using absolute start/end timestamps.

    start and end are strings like 'HH:MM:SS.mmm' (or MM:SS.mmm), and we convert them
    to seconds, then tell ffmpeg to seek to start and cut for (end - start) seconds.
    This is more reliable than using `to=` with timestamps.
    """
    # Convert to seconds
    start_sec = _timestamp_to_seconds(start)
    end_sec = _timestamp_to_seconds(end)
    duration = max(0.0, end_sec - start_sec)

    stream = ffmpeg.input(input_video, ss=start_sec)
    stream = ffmpeg.output(
        stream,
        output_path,
        t=duration,
        c='copy',
        map='0',
    )
    ffmpeg.run(stream, overwrite_output=True)

def _timestamp_to_seconds(ts: str) -> float:
    # Accepts HH:MM:SS.mmm or HH:MM:SS.xx or MM:SS.xx
    import re
    ts = ts.strip()
    m = re.match(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)", ts)
    if not m:
        # fallback: try without ms
        m = re.match(r"(?:(\d+):)?(\d+):(\d+)", ts)
        if not m:
            return 0.0
        h, m_, s = m.groups(default="0")
        ms = "0"
    else:
        h, m_, s, ms = m.groups(default="0")
    h = int(h or 0)
    m_ = int(m_ or 0)
    s = int(s or 0)
    ms = int(ms or 0)
    return h * 3600 + m_ * 60 + s + ms / (1000 if len(str(ms)) == 3 else 100)

def _seconds_to_timestamp(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int(round((secs - int(secs)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def cut_from_ffmpeg_json(input_video: str, ffmpeg_json: str, output_dir: str = "clips") -> list[str]:
    data = json.loads(ffmpeg_json)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pre_roll = 1.0  # seconds before start
    post_roll = 2.0  # seconds after end

    outputs: list[str] = []
    for clip in data:
        idx = clip.get("index", 0)
        label = str(clip.get("label", f"CLIP_{idx}")).replace(" ", "_")
        start = clip["start"]
        end = clip["end"]

        # Convert to seconds, apply padding
        start_sec = max(0.0, _timestamp_to_seconds(start) - pre_roll)
        end_sec = max(start_sec, _timestamp_to_seconds(end) + post_roll)

        # Convert back to timestamp
        start_padded = _seconds_to_timestamp(start_sec)
        end_padded = _seconds_to_timestamp(end_sec)

        filename = f"{idx:02d}_{label}.mp4"
        out_path = out_dir / filename
        cut_video(input_video, start_padded, end_padded, str(out_path))
        outputs.append(str(out_path))
    return outputs
