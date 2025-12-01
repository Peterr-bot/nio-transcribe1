"""PDF export utilities for Nio Transcribe.

Builds a simple, readable PDF cut sheet for all generated clips.
"""

from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from src.export_utils import format_clip_summary


def clips_to_pdf(moments_with_cuts, metadata=None) -> bytes:
    """
    Build a simple, readable PDF summary of all clips.
    Returns PDF bytes suitable for Streamlit's download_button.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    x_margin = 40
    y = height - 50
    line_height = 14

    def write_line(text: str = "", bold: bool = False):
        nonlocal y
        if y < 60:  # new page if too low
            c.showPage()
            y = height - 50
        if bold:
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 10)
        # Truncate very long lines so they don't run off the page
        max_chars = 110
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        c.drawString(x_margin, y, text)
        y -= line_height

    # Header
    write_line("Nio Transcribe – Viral Clips Cut Sheet", bold=True)
    write_line()

    # Basic video metadata
    if metadata:
        title = metadata.get("title") or ""
        channel = metadata.get("channel_name") or ""
        url = metadata.get("url") or ""
        if title:
            write_line(f"Title: {title}", bold=True)
        if channel:
            write_line(f"Channel: {channel}")
        if url:
            write_line(f"URL: {url}")
        write_line()

    # Overall summary
    summary = format_clip_summary(moments_with_cuts)
    for line in summary.splitlines():
        write_line(line)
    write_line()
    write_line("-" * 60)

    # Per-clip detail
    for i, moment in enumerate(moments_with_cuts, 1):
        cut = moment.get("editor_cut_sheet", {}) or {}

        write_line(f"Clip {i}: {cut.get('clip_label', f'CLIP_{i}')}", bold=True)

        timestamps = moment.get("timestamps", "")
        if timestamps:
            write_line(f"Timestamps: {timestamps}")

        duration = moment.get("clip_duration_seconds", None)
        if duration is not None:
            write_line(f"Duration: {duration} s")

        energy = moment.get("energy_tag", "")
        if energy:
            write_line(f"Energy: {energy}")

        trigger = moment.get("viral_trigger", "")
        if trigger:
            write_line(f"Trigger: {trigger}")

        why = moment.get("why_it_hits", "")
        if why:
            write_line("Why it hits:")
            for line in why.splitlines():
                write_line(f"  {line}")

        quote = moment.get("quote", "")
        if quote:
            write_line("Quote:")
            for line in quote.splitlines():
                write_line(f"  {line}")

        # Cut sheet info
        write_line("Cut sheet:")
        write_line(f"  In → Out: {cut.get('in_point', 'N/A')} → {cut.get('out_point', 'N/A')}")
        write_line(f"  Aspect: {cut.get('aspect_ratio', '9:16')}")
        hook = cut.get("opening_hook_subtitle", "")
        if hook:
            write_line(f"  Hook: {hook}")
        emphasis = cut.get("emphasis_words_caps", [])
        if emphasis:
            write_line("  Emphasis: " + ", ".join(emphasis))
        b_roll = cut.get("b_roll_ideas", "")
        if b_roll:
            write_line(f"  B-roll: {b_roll}")
        tos = cut.get("text_on_screen_idea", "")
        if tos:
            write_line(f"  Text on screen: {tos}")
        thumb_text = cut.get("thumbnail_text", "")
        if thumb_text:
            write_line(f"  Thumbnail text: {thumb_text}")
        thumb_face = cut.get("thumbnail_face_cue", "")
        if thumb_face:
            write_line(f"  Thumbnail cue: {thumb_face}")
        platform = cut.get("platform_priority", "")
        if platform:
            write_line(f"  Platform priority: {platform}")

        write_line("-" * 60)

    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf 
