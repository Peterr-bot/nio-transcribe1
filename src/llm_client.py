import os
import json
import re
import math
import uuid
import time
import traceback
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from src import config
from src.extraction import parse_moment_response
from src.cache_utils import get_cached_moments, save_moments_to_cache

# Initialize new OpenAI client (reads OPENAI_API_KEY from environment)
client = OpenAI()
# Default model from config
DEFAULT_MODEL = config.PRIMARY_MODEL

SYSTEM_PROMPT = """
VIRAL MOMENT RULES

You are a Catholic media viral short-form editor. Your job:
- Read a transcript chunk.
- Extract ONLY the strongest short-form "viral moments".
- Return STRICT JSON only. No prose, no markdown, no fences.

CLIP RULES (NON-NEGOTIABLE):

1) TARGET CLIP LENGTH: 13–24 seconds.
    - If a natural moment is shorter than 13 seconds, MERGE adjacent transcript lines until the final stitched clip is 13–24 seconds.
    - If merging is impossible, reject the moment unless it's an extremely viral, self-contained punch.

2) MUST contain a HOOK within the first ~3 seconds.
    - Hook types allowed: SHOCK, STATUS HIT, IDENTITY SPLIT, DOCTRINAL SLAM, CATHOLIC TRUTH DROP.

3) MOMENT STRUCTURE:
    A. Hook → B. Build tension → C. Punch line (end strong)
    - End the clip exactly on the punch. Never after it.

4) LINE FIDELITY:
    - Do NOT paraphrase.
    - Use EXACT raw transcript lines in order.

5) SELECTIVITY:
    - No rambly theology.
    - No "cool thought." Only HIGH-SPIKE lines that travel on TikTok/Reels/Shorts.
    - Avoid low-energy moments.

6) CLIPS OVER 30s:
    - If a moment is too strong to cut down, include the flag: "BROKEN RULE MAJOR REEL"

OUTPUT FORMAT (STRICT):

Return ONLY the following JSON structure. NEVER wrap in code fences or add commentary.

{
  "moments": [
     {
        "timestamps": "00:04.23-00:21.90",
        "quote": "EXACT transcript lines for this moment.",
        "clip_duration_seconds": 17,
        "viral_trigger": "SHOCK | STATUS HIT | IDENTITY SPLIT | DOCTRINAL SLAM | HOPE | AWE",
        "why_it_hits": "One sharp sentence explaining why this goes viral.",
        "energy_tag": "3-5 words describing tone",
        "flags": ["optional", "BROKEN RULE MAJOR REEL", "REWATCH"],
        "persona_captions": {
            "historian": "Under 10s. Authority tone.",
            "thomist": "Under 10s. Logic punch.",
            "ex_protestant": "Under 10s. Testimony contrast.",
            "meme_catholic": "Under 10s. TikTok-native joke/punch.",
            "old_world_catholic": "Under 10s. Ancient gravity.",
            "catholic": "Under 10s. Clean, bold Catholic line."
        }
     }
  ]
}

IMPORTANT:
- NEVER invent transcript text.
- "quote" must be 100% faithful to the transcript chunk text; do not invent or paraphrase.
- If a chunk has nothing usable, return: { "moments": [] }

End of instructions.
""".strip()

def build_prompt_for_chunk(transcript_chunk: str, chunk_index: int, total_chunks: int) -> str:
    """Build the user prompt for a single transcript chunk.

    The chunk index is 1-based.
    """
    header = f"Chunk {chunk_index} of {total_chunks}. The text below is a continuous portion of a longer talk.\n"
    instructions = (
        f"Find at most {config.MAX_MOMENTS_PER_CHUNK} of the strongest viral clip moments ONLY from this chunk.\n"
        "Return them in the JSON format described in the system prompt.\n"
        "Transcript chunk:\n"
    )
    return header + instructions + transcript_chunk


def call_llm(user_prompt: str, model: Optional[str] = None, temperature: float = 0.3) -> str:
    """Simple wrapper with a generic system prompt using the new OpenAI client."""
    return call_llm_with_system("You are a helpful assistant.", user_prompt, model=model, temperature=temperature)


def call_llm_with_system(system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.3) -> str:
    """Call OpenAI chat API using the new client interface.

    Uses `client.chat.completions.create(...)` from the `openai` package v1+.
    """
    model = model or DEFAULT_MODEL

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )

    # new client returns choices with message objects
    try:
        return resp.choices[0].message.content.strip()
    except Exception:
        # Fallback to dict-style access if needed
        return getattr(resp.choices[0].message, "content", str(resp))

# parse_moment_response is provided by src.extraction; use that implementation

def extract_moments(transcript: str, video_metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """Chunk the transcript, call GPT-5.1 on each chunk, and collect viral moments.

    Args:
        transcript: The transcript text to process
        video_metadata: Optional video metadata for better caching

    Raises:
        RuntimeError: if no usable moments are found from any chunk.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise RuntimeError("Transcript is empty; cannot extract moments.")

    # Check cache first
    cached_moments = get_cached_moments(transcript, video_metadata)
    if cached_moments is not None:
        return cached_moments

    # Character-based chunking using config
    max_chunk_chars = config.CHARS_PER_CHUNK
    chunks: List[str] = []
    current = []

    for line in transcript.splitlines():
        if sum(len(l) for l in current) + len(line) + 1 > max_chunk_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))

    total_chunks = len(chunks)
    all_moments: List[Dict[str, Any]] = []
    last_raw_response: Optional[str] = None

    print(f"[extract_moments] Transcript length: {len(transcript)} chars, chunks: {total_chunks}")

    # Process chunks in parallel for speed
    all_moments = _process_chunks_parallel(chunks)

    if not all_moments:
        print(f"[WARN] No viral moments could be extracted from transcript. Transcript length: {len(transcript)} chars, Chunks processed: {total_chunks}.")
        return []

    # Cache the results
    save_moments_to_cache(all_moments, transcript, video_metadata)

    return all_moments


def _process_single_chunk(chunk_data: tuple) -> List[Dict[str, Any]]:
    """Process a single chunk - used for parallel processing.

    Args:
        chunk_data: Tuple of (chunk_text, chunk_index, total_chunks)

    Returns:
        List of moments from this chunk
    """
    chunk, idx, total_chunks = chunk_data

    try:
        user_prompt = build_prompt_for_chunk(chunk, idx, total_chunks)

        # Log chunk info for debugging
        print(f"[extract_moments] Processing chunk {idx}/{total_chunks} (chars: {len(chunk)})")

        raw_response = call_llm_with_system(SYSTEM_PROMPT, user_prompt)
        snippet = raw_response[:400].replace("\n", " ")
        print(f"[extract_moments] Chunk {idx}/{total_chunks} raw response (truncated): {snippet}...")
        if idx == 1:
            # Print more of the first chunk's raw response for debugging
            print(f"[extract_moments] Chunk 1 raw response (first 2000 chars):\n{raw_response[:2000]}")

        moments = parse_moment_response(raw_response)

        # Safety limit: truncate if too many moments returned
        if len(moments) > config.MOMENT_SAFETY_LIMIT:
            print(f"[extract_moments] Chunk {idx} returned {len(moments)} moments, truncating to {config.MOMENT_SAFETY_LIMIT}")
            moments = moments[:config.MOMENT_SAFETY_LIMIT]

        if not moments:
            print(f"[extract_moments] No moments parsed for chunk {idx}")
            return []
        else:
            print(f"[extract_moments] Parsed {len(moments)} moments for chunk {idx}")
            return moments

    except Exception as e:
        print(f"[extract_moments] Error processing chunk {idx}: {e}")
        print("[extract_moments] Full traceback:")
        print(traceback.format_exc())
        return []


def _process_chunks_parallel(chunks: List[str]) -> List[Dict[str, Any]]:
    """Process chunks in parallel for better performance.

    Args:
        chunks: List of transcript chunks to process

    Returns:
        Combined list of all moments from all chunks
    """
    all_moments = []
    total_chunks = len(chunks)

    # Prepare chunk data for parallel processing
    chunk_data = [(chunk, idx, total_chunks) for idx, chunk in enumerate(chunks, start=1)]

    # Process chunks in parallel with limited concurrency
    with ThreadPoolExecutor(max_workers=config.MAX_PARALLEL_CHUNKS) as executor:
        # Submit all chunks
        future_to_chunk = {executor.submit(_process_single_chunk, data): data[1] for data in chunk_data}

        # Collect results as they complete
        for future in as_completed(future_to_chunk):
            chunk_idx = future_to_chunk[future]
            try:
                chunk_moments = future.result()
                if chunk_moments:
                    all_moments.extend(chunk_moments)
            except Exception as e:
                print(f"[extract_moments] Parallel processing error for chunk {chunk_idx}: {e}")

    return all_moments


# Clean function boundaries for future 2-model pipeline
def find_candidate_moments_fast(transcript: str) -> List[Dict[str, Any]]:
    """Future: Use fast model to find candidate timestamps only.

    For now, this is just a placeholder that calls the main extract_moments.
    In the future, this could use FAST_MODEL to quickly identify potential moments.
    """
    # Placeholder for future fast candidate detection
    return extract_moments(transcript)


def enrich_moments_with_persona_and_cuts(candidate_moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Future: Use primary model to enrich candidates with full persona captions.

    For now, this just returns the input moments unchanged.
    In the future, this could use PRIMARY_MODEL for detailed persona caption generation.
    """
    # Placeholder for future persona enrichment
    return candidate_moments

