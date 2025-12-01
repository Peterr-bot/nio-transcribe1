from typing import List, Dict, Any, Optional
import uuid


def parse_moment_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse GPT's JSON response into structured moment data.

    This is intentionally defensive because models sometimes:
    - wrap JSON in prose,
    - wrap JSON in markdown fences,
    - return a top-level list instead of {"moments": [...]},
    - or include extra keys around the "moments" array.
    """
    import json
    import re

    def strip_code_fences(text: str) -> str:
        t = text.strip()

        # Strip ```json ... ``` or ``` ... ```
        if t.startswith("```"):
            # remove leading ```... first line
            # e.g. ```json\n{...}
            first_newline = t.find("\n")
            if first_newline != -1:
                t = t[first_newline + 1 :]
            # remove trailing ```
            if t.endswith("```"):
                t = t[:-3]
        return t.strip()

    def try_load_json(candidate: str) -> Optional[Any]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    # 1) Clean obvious markdown wrappers
    clean_response = strip_code_fences(response_text)

    # 2) First attempt: direct parse of the whole thing
    data = try_load_json(clean_response)

    # 3) If that fails, try to extract the biggest JSON-looking block
    if data is None:
        # Try object first
        obj_match = re.search(r"\{[\s\S]*\}", clean_response)
        list_match = re.search(r"\[[\s\S]*\]", clean_response)

        candidate = None
        if obj_match:
            candidate = obj_match.group(0)
        elif list_match:
            candidate = list_match.group(0)

        if candidate:
            data = try_load_json(candidate)

    if data is None:
        # Still nothing usable
        print("JSON Parse Error: could not parse LLM response as JSON.")
        print(f"Raw response (truncated): {response_text[:500]}...")
        return []

    # 4) Normalize to a list of moments
    if isinstance(data, list):
        # Model returned a bare list of moment objects
        moments = data
    elif isinstance(data, dict):
        # Preferred format: {"moments": [...]}
        moments = data.get("moments", [])
        # Fallback: if "moments" missing but data looks like a single moment
        if not moments and ("quote" in data or "timestamps" in data):
            moments = [data]
    else:
        print(f"Unexpected JSON root type: {type(data)}")
        return []

    # 5) Validate and enrich each moment
    processed_moments = []
    for i, moment in enumerate(moments):
        if not isinstance(moment, dict):
            print(f"Warning: Skipping non-dict moment at index {i}")
            continue

        # Add unique ID
        moment["id"] = str(uuid.uuid4())[:8]

        # Ensure required fields exist
        # We require at least a quote. If timestamps are missing, keep the moment
        # but set an empty timestamps string so downstream code can still operate
        if not moment.get("quote"):
            print(f"Warning: Skipping incomplete moment {i+1} (missing quote)")
            continue
        if not moment.get("timestamps"):
            print(f"Warning: Moment {i+1} missing timestamps; including with empty timestamps")
            moment.setdefault("timestamps", "")
        # Recalculate clip_duration_seconds based on word count (more reliable than token timestamps)
        quote = moment.get("quote", "")
        word_count = len(quote.split()) if quote else 0

        # Use words-per-second rule: typical speech is ~2.6 words/second
        # Use the LLM's estimate as a baseline, but ensure it's at least word_count / 2.6
        llm_duration = moment.get("clip_duration_seconds", 0)
        try:
            llm_duration = int(llm_duration) if llm_duration else 0
        except Exception:
            llm_duration = 0

        word_based_duration = int(word_count / 2.6) if word_count > 0 else 0

        # Use the maximum of LLM estimate and word-based calculation
        moment["clip_duration_seconds"] = max(llm_duration, word_based_duration)

        # Ensure optional structures exist so downstream UI doesn't explode
        moment.setdefault("viral_trigger", "")
        moment.setdefault("why_it_hits", "")
        moment.setdefault("energy_tag", "")
        moment.setdefault("flags", [])
        moment.setdefault("persona_captions", {})
        for key in ["historian", "thomist", "ex_protestant", "meme_catholic", "old_world_catholic", "catholic"]:
            moment["persona_captions"].setdefault(key, "")

        processed_moments.append(moment)

    return processed_moments