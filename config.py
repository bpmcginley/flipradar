"""FlipRadar configuration."""

# Buyer profile
BUDGET_MAX = 2000  # max asking price in USD
BUYER_LANGUAGES = ["python", "c#", "javascript", "typescript", "rust"]
MAX_HOURS_PER_WEEK = 5

# Adapter sources to run on `scan`. Each name maps to adapters/<name>.py
# exposing class <Name>Adapter (e.g. "acquire" -> AcquireAdapter).
TARGET_SOURCES = [
    "reddit",
    # "acquire",
    "flippa",
    "microns",
    # "tinyacquisitions",  # disabled 2026-08: domain no longer resolves; site appears defunct
    "sideprojectors",
]

USER_AGENT = "FlipRadar/0.1 (personal deal research)"
REQUEST_DELAY_SECONDS = 2
CACHE_TTL_HOURS = 12
