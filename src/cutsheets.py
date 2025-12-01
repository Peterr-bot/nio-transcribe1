"""Cut sheet generation using GPT-5.1 with the specified prompt.

Takes extracted moments and generates detailed editor cut sheets.
"""

import re
from typing import List, Dict, Any
from src.llm_client import call_llm


# The exact CUT_SHEET_PROMPT as specified in requirements
CUT_SHEET_PROMPT = r"""
You are optimizing already-extracted viral moments for a short-form video editor.

INPUT:
I will give you one or more "Moment" blocks in the following format:

MOMENT HEADER
- timestamps: 00:00–00:00
- quote: "EXACT RAW QUOTE"
- clip duration: X seconds
- viral trigger: TRIGGER_TAG
- why it hits: one blunt sentence
- energy tag: 3–5 words
- flags: (may be empty, or contain BROKEN RULE MAJOR REEL, REWATCH, SILENCE FIX
REQUIRED)

PERSONA CAPTION LINES
- Historian: ...
- Thomist: ...
- Ex-Protestant: ...
- Meme Catholic: ...
- Old World Catholic: ...
- Catholic: ...

TASK:
For EACH moment you receive, keep the original content untouched, and ADD an "EDITOR
CUT SHEET" section directly under it.

Do NOT change any quotes or captions.

For every moment, output exactly this structure:

MOMENT HEADER
[unchanged, copy from input]

PERSONA CAPTION LINES
[unchanged, copy from input]

EDITOR CUT SHEET
- clip_label: [UPPER_SNAKE_CASE name for the moment]
- in_point: [copy start timestamp from moment header]
- out_point: [copy end timestamp from moment header]
- aspect_ratio: 9:16
- crop_note: [1 short line: e.g. "tight on face, slow push in", "medium shot, quick punch-in on last
line"]
- opening_hook_subtitle: [1–2 lines under 3 seconds, strongest idea in the quote]
- emphasis_words_caps: [3–8 words or phrases from the quote to be in ALL CAPS in subtitles]
- pacing_note: [e.g. "fast, no pauses", "let last line breathe", "trim any filler before the hook"]
- b_roll_ideas: [optional; only if naturally obvious, 1 short line or "none"]
- text_on_screen_idea: [optional big text word/phrase or "none"]
- silence_handling: ["none", "hard cut silence", or "cover with b-roll"] — if the moment was
flagged SILENCE FIX REQUIRED, you MUST choose one.
- thumbnail_text: [2–5 word all-caps phrase that matches the punch of the quote]
- thumbnail_face_cue: [1 short line: e.g., "use frame where he leans in", "use frame where he
looks deadly serious"]
- platform_priority: [TikTok / Reels / YouTube Shorts / All]
- use_persona_caption: [choose the single strongest persona caption line to use as default;
copy it exactly]

RULES:
- Never paraphrase the quote or the persona captions.
- Keep all notes short, sharp, and literal so the editor can execute without thinking.
- Always make the opening_hook_subtitle the hardest-hitting idea from the quote.
- Thumbnail_text must be brutal and simple, not pious or wordy.
"""


def format_moments_for_cutsheet_prompt(moments: List[Dict[str, Any]]) -> str:
    """Format extracted moments into the text format expected by the cut sheet prompt.

    Args:
        moments: List of moment dictionaries from extraction

    Returns:
        Formatted text string with all moments
    """
    formatted_blocks = []

    for moment in moments:
        # Build moment header
        header_lines = [
            "MOMENT HEADER",
            f"- timestamps: {moment.get('timestamps', '')}",
            f"- quote: \"{moment.get('quote', '')}\"",
            f"- clip duration: {moment.get('clip_duration_seconds', 'unknown')} seconds" if moment.get('clip_duration_seconds') else "- clip duration: unknown",
            f"- viral trigger: {moment.get('viral_trigger', '')}",
            f"- why it hits: {moment.get('why_it_hits', '')}",
            f"- energy tag: {moment.get('energy_tag', '')}",
            f"- flags: {', '.join(moment.get('flags', []))}" if moment.get('flags') else "- flags: "
        ]

        # Build persona caption lines
        persona_lines = ["", "PERSONA CAPTION LINES"]
        captions = moment.get('persona_captions', {})

        persona_lines.append(f"- Historian: {captions.get('historian', '')}")
        persona_lines.append(f"- Thomist: {captions.get('thomist', '')}")
        persona_lines.append(f"- Ex-Protestant: {captions.get('ex_protestant', '')}")
        persona_lines.append(f"- Meme Catholic: {captions.get('meme_catholic', '')}")
        persona_lines.append(f"- Old World Catholic: {captions.get('old_world_catholic', '')}")
        persona_lines.append(f"- Catholic: {captions.get('catholic', '')}")

        # Combine into single block
        block = "\n".join(header_lines + persona_lines)
        formatted_blocks.append(block)

    return "\n\n" + "="*60 + "\n\n".join([""] + formatted_blocks)


def parse_cut_sheet_response(response_text: str, original_moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse GPT's cut sheet response and merge with original moments.

    Args:
        response_text: Raw response from GPT with cut sheets
        original_moments: Original moment dictionaries

    Returns:
        Updated moments with editor_cut_sheet data added
    """
    updated_moments = []

    # Split response into moment blocks (heuristic approach)
    blocks = re.split(r'\n\s*(?=MOMENT HEADER)', response_text, flags=re.IGNORECASE)

    # Match blocks to original moments (by order, since we sent them in order)
    for i, moment in enumerate(original_moments):
        updated_moment = moment.copy()

        # Try to find corresponding cut sheet block
        if i < len(blocks):
            cut_sheet = parse_single_cut_sheet_block(blocks[i])
            if cut_sheet:
                updated_moment["editor_cut_sheet"] = cut_sheet

        # If no cut sheet found, create a minimal one
        if "editor_cut_sheet" not in updated_moment:
            updated_moment["editor_cut_sheet"] = create_fallback_cut_sheet(moment)

        updated_moments.append(updated_moment)

    return updated_moments


def parse_single_cut_sheet_block(block_text: str) -> Dict[str, Any]:
    """Parse a single cut sheet block into structured data.

    Args:
        block_text: Text block containing cut sheet data

    Returns:
        Cut sheet dictionary
    """
    cut_sheet = {
        "clip_label": "",
        "in_point": "",
        "out_point": "",
        "aspect_ratio": "9:16",
        "crop_note": "",
        "opening_hook_subtitle": "",
        "emphasis_words_caps": [],
        "pacing_note": "",
        "b_roll_ideas": "",
        "text_on_screen_idea": "",
        "silence_handling": "none",
        "thumbnail_text": "",
        "thumbnail_face_cue": "",
        "platform_priority": "All",
        "use_persona_caption": ""
    }

    lines = block_text.split('\n')
    in_cut_sheet_section = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        line_lower = line.lower()

        # Check if we're in the editor cut sheet section
        if 'editor cut sheet' in line_lower:
            in_cut_sheet_section = True
            continue

        if in_cut_sheet_section and '-' in line:
            # Parse cut sheet fields
            field_name, field_value = extract_field_value(line)

            if field_name == "clip_label":
                cut_sheet["clip_label"] = field_value
            elif field_name == "in_point":
                cut_sheet["in_point"] = field_value
            elif field_name == "out_point":
                cut_sheet["out_point"] = field_value
            elif field_name == "aspect_ratio":
                cut_sheet["aspect_ratio"] = field_value
            elif field_name == "crop_note":
                cut_sheet["crop_note"] = field_value
            elif field_name == "opening_hook_subtitle":
                cut_sheet["opening_hook_subtitle"] = field_value
            elif field_name == "emphasis_words_caps":
                # Parse list of words/phrases
                caps_list = parse_caps_list(field_value)
                cut_sheet["emphasis_words_caps"] = caps_list
            elif field_name == "pacing_note":
                cut_sheet["pacing_note"] = field_value
            elif field_name == "b_roll_ideas":
                cut_sheet["b_roll_ideas"] = field_value
            elif field_name == "text_on_screen_idea":
                cut_sheet["text_on_screen_idea"] = field_value
            elif field_name == "silence_handling":
                cut_sheet["silence_handling"] = field_value
            elif field_name == "thumbnail_text":
                cut_sheet["thumbnail_text"] = field_value
            elif field_name == "thumbnail_face_cue":
                cut_sheet["thumbnail_face_cue"] = field_value
            elif field_name == "platform_priority":
                cut_sheet["platform_priority"] = field_value
            elif field_name == "use_persona_caption":
                cut_sheet["use_persona_caption"] = field_value

    return cut_sheet


def extract_field_value(line: str) -> tuple[str, str]:
    """Extract field name and value from a cut sheet line.

    Args:
        line: Line like "- clip_label: SOME_VALUE"

    Returns:
        Tuple of (field_name, field_value)
    """
    # Remove bullet and split on colon
    line = re.sub(r'^-\s*', '', line.strip())

    if ':' in line:
        parts = line.split(':', 1)
        field_name = parts[0].strip().lower()
        field_value = parts[1].strip()

        # Clean up field value
        field_value = re.sub(r'^\[|\]$', '', field_value)  # Remove brackets
        field_value = field_value.strip('"\'')  # Remove quotes

        return field_name, field_value

    return "", ""


def parse_caps_list(caps_text: str) -> List[str]:
    """Parse emphasis words caps field into list.

    Args:
        caps_text: Text like "WORD1, PHRASE TWO, WORD3" or "[word1, word2, word3]"

    Returns:
        List of words/phrases to capitalize
    """
    if not caps_text:
        return []

    # Remove brackets and split on commas
    caps_text = re.sub(r'[\[\]]', '', caps_text)

    # Split on commas and clean up
    words = []
    for word in caps_text.split(','):
        word = word.strip().strip('"\'')
        if word:
            words.append(word)

    return words


def create_fallback_cut_sheet(moment: Dict[str, Any]) -> Dict[str, Any]:
    """Create a minimal fallback cut sheet when parsing fails.

    Args:
        moment: Original moment dictionary

    Returns:
        Basic cut sheet dictionary
    """
    # Extract timestamps
    timestamps = moment.get('timestamps', '')
    start_ts, end_ts = '', ''
    if '–' in timestamps or '—' in timestamps or '-' in timestamps:
        parts = re.split(r'[–—-]', timestamps)
        if len(parts) >= 2:
            start_ts = parts[0].strip()
            end_ts = parts[1].strip()

    # Create basic label from energy tag or trigger
    label_base = moment.get('energy_tag', '') or moment.get('viral_trigger', '') or 'MOMENT'
    clip_label = re.sub(r'[^A-Z0-9]+', '_', label_base.upper()).strip('_')

    return {
        "clip_label": clip_label,
        "in_point": start_ts,
        "out_point": end_ts,
        "aspect_ratio": "9:16",
        "crop_note": "medium shot, standard framing",
        "opening_hook_subtitle": moment.get('quote', '')[:50] + "...",
        "emphasis_words_caps": [],
        "pacing_note": "standard pacing",
        "b_roll_ideas": "none",
        "text_on_screen_idea": "none",
        "silence_handling": "hard cut silence" if "SILENCE FIX REQUIRED" in moment.get('flags', []) else "none",
        "thumbnail_text": clip_label,
        "thumbnail_face_cue": "use strongest expression",
        "platform_priority": "All",
        "use_persona_caption": moment.get('persona_captions', {}).get('catholic', '')
    }


def generate_cut_sheets(moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate cut sheets for extracted moments using GPT-5.1.

    Main function that orchestrates the cut sheet generation process.

    Args:
        moments: List of moment dictionaries from extraction

    Returns:
        Updated moments with editor_cut_sheet data

    Raises:
        RuntimeError: If LLM call fails
    """
    if not moments:
        return []

    try:
        # Format moments for the prompt
        formatted_input = format_moments_for_cutsheet_prompt(moments)

        # Build full prompt
        full_prompt = f"{CUT_SHEET_PROMPT}\n\n{formatted_input}"

        # Call GPT-5.1
        response = call_llm(full_prompt)

        # Parse response and merge with original data
        updated_moments = parse_cut_sheet_response(response, moments)

        return updated_moments

    except Exception as e:
        raise RuntimeError(f"Failed to generate cut sheets: {e}")