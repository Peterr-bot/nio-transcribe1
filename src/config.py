"""Configuration module for Nio Transcribe.

Handles environment variable loading and validation for API keys and settings.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file, overriding existing ones
load_dotenv(override=True)


def get_required_env(name: str) -> str:
    """Get a required environment variable or raise an error with clear message.

    Args:
        name: Environment variable name

    Returns:
        Environment variable value

    Raises:
        RuntimeError: If environment variable is missing or empty
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Please set {name} in your environment or .env file."
        )
    return value


def get_optional_env(name: str, default: str = "") -> str:
    """Get an optional environment variable with default value.

    Args:
        name: Environment variable name
        default: Default value if not found

    Returns:
        Environment variable value or default
    """
    return os.getenv(name, default)


# API Configuration
OPENAI_API_KEY: Optional[str] = None
APIFY_TOKEN: Optional[str] = None
APIFY_ACTOR_ID: Optional[str] = None

# Model Configuration
DEFAULT_GPT_MODEL = "gpt-5.1"
PRIMARY_MODEL = "gpt-5.1"
FAST_MODEL = "gpt-4.1-mini"

# Extraction Performance Settings
CHARS_PER_CHUNK = 9000  # Increased from ~5000 for fewer API calls
MAX_MOMENTS_PER_CHUNK = 3  # Limit moments per chunk for speed
MAX_PARALLEL_CHUNKS = 3  # Parallel processing limit
MOMENT_SAFETY_LIMIT = 5  # Hard limit to protect downstream processing

# Cache Settings
CACHE_ENABLED = True
CACHE_DIR = ".nio_cache"


def initialize_config() -> None:
    """Initialize configuration by loading required environment variables.

    Should be called once at application startup.

    Raises:
        RuntimeError: If any required environment variables are missing
    """
    global OPENAI_API_KEY, APIFY_TOKEN, APIFY_ACTOR_ID

    OPENAI_API_KEY = get_required_env("OPENAI_API_KEY")
    APIFY_TOKEN = get_required_env("APIFY_TOKEN")
    APIFY_ACTOR_ID = get_required_env("APIFY_ACTOR_ID")


def validate_config() -> None:
    """Validate that all required configuration is loaded.

    Raises:
        RuntimeError: If configuration is not properly initialized
    """
    if not all([OPENAI_API_KEY, APIFY_TOKEN, APIFY_ACTOR_ID]):
        raise RuntimeError(
            "Configuration not initialized. Call initialize_config() first."
        )


# Initialize on import (can be overridden by calling initialize_config() explicitly)
try:
    initialize_config()
except RuntimeError:
    # Allow module to be imported even if env vars aren't set yet
    # They'll be checked when actually needed
    pass