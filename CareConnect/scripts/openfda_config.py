"""
OpenFDA Pipeline Configuration
================================
Central config for all OpenFDA ingestion settings.
"""

# ── OpenFDA ────────────────────────────────────────────────────────────────────
OPENFDA_BASE = "https://api.fda.gov"

# How many records to fetch per endpoint (max 1000 per call without an API key)
OPENFDA_LIMITS = {
    "label":       100,   # /drug/label       — uses, warnings, dosage
    "ndc":         200,   # /drug/ndc         — brand name, manufacturer, packaging
    "drugsfda":    100,   # /drug/drugsfda    — approval status, application number
    "event":       200,   # /drug/event       — adverse events (20M+ total)
    "enforcement": 100,   # /drug/enforcement — recalls, safety issues
    "shortages":    50,   # /drug/shortages   — supply issues
}

# Endpoints
OPENFDA_ENDPOINTS = {
    "label":       "/drug/label.json",
    "ndc":         "/drug/ndc.json",
    "drugsfda":    "/drug/drugsfda.json",
    "event":       "/drug/event.json",
    "enforcement": "/drug/enforcement.json",
    "shortages":   "/drug/shortages.json",
}

# ── MongoDB ─────────────────────────────────────────────────────────────────────
import os
MONGO_URI   = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB    = "pharma_db"
MONGO_COLL  = "drugs"

# ── Output (JSON fallback if MongoDB is unavailable) ────────────────────────────
import pathlib
BASE_DIR         = pathlib.Path(__file__).parent.parent
OPENFDA_OUT_PATH = BASE_DIR / "static" / "data" / "openfda_drugs.json"

# ── Merge key ──────────────────────────────────────────────────────────────────
# We try to link records across endpoints using these field names (in order of
# preference).  The first non-empty value found is used as the canonical key.
MERGE_KEYS = ["generic_name", "substance_name", "brand_name"]
