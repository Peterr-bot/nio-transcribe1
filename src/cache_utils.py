"""Simple caching utilities for parsed moments.

Provides file-based caching to avoid re-processing identical transcripts.
"""

import os
import json
import hashlib
from typing import List, Dict, Any, Optional
from src import config


def _get_cache_dir() -> str:
    """Get the cache directory, creating it if needed."""
    cache_dir = config.CACHE_DIR
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _build_cache_key(transcript_text: str, video_metadata: Optional[Dict] = None) -> str:
    """Build a stable cache key from transcript or video metadata.

    Priority:
    1. If video_metadata has video_id and language, use those
    2. Otherwise, use hash of transcript text

    Args:
        transcript_text: The transcript content
        video_metadata: Optional metadata from YouTube extraction

    Returns:
        Stable cache key string
    """
    # Try video-based key first (more stable)
    if video_metadata:
        video_id = video_metadata.get("video_id", "")
        language = video_metadata.get("language", "en")
        if video_id:
            return f"video_{video_id}_{language}"

    # Fallback to transcript hash
    transcript_hash = hashlib.md5(transcript_text.encode('utf-8')).hexdigest()
    return f"transcript_{transcript_hash}"


def _get_cache_path(cache_key: str) -> str:
    """Get the full file path for a cache key."""
    cache_dir = _get_cache_dir()
    return os.path.join(cache_dir, f"{cache_key}.json")


def get_cached_moments(transcript_text: str, video_metadata: Optional[Dict] = None) -> Optional[List[Dict[str, Any]]]:
    """Retrieve cached moments if available.

    Args:
        transcript_text: The transcript content
        video_metadata: Optional video metadata

    Returns:
        Cached moments list or None if not found/disabled
    """
    if not config.CACHE_ENABLED:
        return None

    try:
        cache_key = _build_cache_key(transcript_text, video_metadata)
        cache_path = _get_cache_path(cache_key)

        if not os.path.exists(cache_path):
            return None

        with open(cache_path, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)

        # Validate cache structure
        if not isinstance(cached_data, dict) or 'moments' not in cached_data:
            print(f"[cache] Invalid cache structure for key {cache_key}")
            return None

        moments = cached_data['moments']
        if not isinstance(moments, list):
            print(f"[cache] Invalid moments structure for key {cache_key}")
            return None

        print(f"[cache] Cache hit for key {cache_key} – returning {len(moments)} cached moments")
        return moments

    except Exception as e:
        print(f"[cache] Error reading cache: {e}")
        return None


def save_moments_to_cache(moments: List[Dict[str, Any]], transcript_text: str, video_metadata: Optional[Dict] = None) -> None:
    """Save moments to cache.

    Args:
        moments: The parsed moments to cache
        transcript_text: The transcript content
        video_metadata: Optional video metadata
    """
    if not config.CACHE_ENABLED:
        return

    try:
        cache_key = _build_cache_key(transcript_text, video_metadata)
        cache_path = _get_cache_path(cache_key)

        cache_data = {
            'cache_key': cache_key,
            'moments_count': len(moments),
            'moments': moments
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        print(f"[cache] Saved {len(moments)} moments to cache with key {cache_key}")

    except Exception as e:
        print(f"[cache] Error saving to cache: {e}")


def clear_cache() -> None:
    """Clear all cached files."""
    try:
        cache_dir = _get_cache_dir()
        cache_files = [f for f in os.listdir(cache_dir) if f.endswith('.json')]

        for cache_file in cache_files:
            cache_path = os.path.join(cache_dir, cache_file)
            os.remove(cache_path)

        print(f"[cache] Cleared {len(cache_files)} cache files")

    except Exception as e:
        print(f"[cache] Error clearing cache: {e}")