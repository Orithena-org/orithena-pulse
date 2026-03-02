"""Configuration for Orithena Pulse content intelligence pipeline."""

import os
from pathlib import Path
from urllib.parse import urlparse

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
ARCHIVE_DIR = DATA_DIR / "archive"
REPORTS_DIR = DATA_DIR / "reports"
OUTPUT_DIR = PROJECT_ROOT / "output"
SITE_DIR = OUTPUT_DIR / "site"
DOMAINS_DIR = PROJECT_ROOT / "domains"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

# Ensure directories exist
for d in [DATA_DIR, RAW_DIR, ARCHIVE_DIR, REPORTS_DIR, OUTPUT_DIR, SITE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# HTTP settings
REQUEST_TIMEOUT = 30
USER_AGENT = "OrithenaPulse/1.0 (content intelligence pipeline)"

# Site settings
SITE_TITLE = "Orithena Pulse"
SITE_URL = os.getenv("SITE_URL", "https://orithena-org.github.io/orithena-pulse")
DEFAULT_DOMAIN = os.getenv("PULSE_DOMAIN", "agentic")

# Base path for GitHub Pages (e.g., "/orithena-pulse" from the SITE_URL)
_parsed_url = urlparse(SITE_URL)
BASE_PATH = _parsed_url.path.rstrip("/") or ""
