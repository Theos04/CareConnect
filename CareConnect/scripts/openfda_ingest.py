"""
OpenFDA Multi-Dataset Ingestion Pipeline
=========================================
Fetches from 5 OpenFDA endpoints, merges on generic_name, normalises to the
unified CareConnect schema, and writes output to:
  1. MongoDB  (preferred)  – pharma_db.drugs
  2. JSON file (fallback)  – static/data/openfda_drugs.json

Usage:
    py scripts/openfda_ingest.py
"""

import json
import sys
import time
import logging
import requests
from pathlib import Path

# ── Allow running directly from project root ───────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.openfda_config import (
    OPENFDA_BASE, OPENFDA_ENDPOINTS, OPENFDA_LIMITS,
    MERGE_KEYS, MONGO_URI, MONGO_DB, MONGO_COLL, OPENFDA_OUT_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("openfda_ingest")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get(endpoint: str, limit: int, skip: int = 0) -> list:
    """Fetch one page from OpenFDA.  Returns results list or []."""
    url = f"{OPENFDA_BASE}{endpoint}?limit={limit}&skip={skip}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as exc:
        log.warning("OpenFDA fetch failed (%s): %s", endpoint, exc)
        return []


def _canonical_name(record: dict, source: str) -> str:
    """Extract the best merge key from a record."""
    openfda = record.get("openfda", {})

    # label / event / enforcement store names in openfda sub-object as lists
    for key in MERGE_KEYS:
        val = openfda.get(key) or record.get(key)
        if isinstance(val, list) and val:
            return val[0].lower().strip()
        if isinstance(val, str) and val:
            return val.lower().strip()

    # ndc stores brand/generic at top level
    for key in ["generic_name", "brand_name", "nonproprietary_name"]:
        val = record.get(key, "")
        if val:
            return val.lower().strip()

    return ""


# ── Dataset fetchers ───────────────────────────────────────────────────────────

def fetch_labels(limit: int) -> dict:
    """Returns {canonical_name: {...}} from /drug/label."""
    log.info("Fetching /drug/label (limit=%d)…", limit)
    results = _get(OPENFDA_ENDPOINTS["label"], limit)
    out = {}
    for r in results:
        name = _canonical_name(r, "label")
        if not name:
            continue
        openfda = r.get("openfda", {})
        out[name] = {
            "drug_name":    name,
            "brand_names":  openfda.get("brand_name", []),
            "uses":         r.get("indications_and_usage", [""])[:1],
            "dosage":       r.get("dosage_and_administration", [""])[:1],
            "warnings":     r.get("warnings", [""])[:1],
            "side_effects": r.get("adverse_reactions", [""])[:1],
            "overdosage":   r.get("overdosage", [""])[:1],
            "contraindications": r.get("contraindications", [""])[:1],
            "source_ids":   {"label": openfda.get("application_number", [""])[0] if openfda.get("application_number") else ""},
        }
    log.info("  → %d label records", len(out))
    return out


def fetch_ndc(limit: int) -> dict:
    """Returns {canonical_name: {...}} from /drug/ndc."""
    log.info("Fetching /drug/ndc (limit=%d)…", limit)
    results = _get(OPENFDA_ENDPOINTS["ndc"], limit)
    out = {}
    for r in results:
        name = _canonical_name(r, "ndc")
        if not name:
            continue
        out[name] = {
            "manufacturer": r.get("labeler_name", ""),
            "dosage_form":  r.get("dosage_form", ""),
            "route":        r.get("route", []),
            "packaging":    [p.get("description", "") for p in r.get("packaging", [])[:3]],
            "brand_names":  [r.get("brand_name", "")],
            "source_ids":   {"ndc": r.get("product_ndc", "")},
        }
    log.info("  → %d NDC records", len(out))
    return out


def fetch_drugsfda(limit: int) -> dict:
    """Returns {canonical_name: {...}} from /drug/drugsfda."""
    log.info("Fetching /drug/drugsfda (limit=%d)…", limit)
    results = _get(OPENFDA_ENDPOINTS["drugsfda"], limit)
    out = {}
    for r in results:
        openfda = r.get("openfda", {})
        name = _canonical_name(r, "drugsfda")
        if not name:
            continue
        # Pull approval info from submissions list
        submissions = r.get("submissions", [])
        latest = submissions[0] if submissions else {}
        out[name] = {
            "approval_status":       latest.get("submission_status", ""),
            "approval_date":         latest.get("submission_status_date", ""),
            "application_number":    r.get("application_number", ""),
            "sponsor_name":          r.get("sponsor_name", ""),
            "source_ids":            {"fda": r.get("application_number", "")},
        }
    log.info("  → %d FDA approval records", len(out))
    return out


def fetch_adverse_events(limit: int) -> dict:
    """Returns {canonical_name: [events...]} from /drug/event."""
    log.info("Fetching /drug/event (limit=%d)…", limit)
    results = _get(OPENFDA_ENDPOINTS["event"], limit)
    out = {}
    for r in results:
        drugs = r.get("patient", {}).get("drug", [])
        reactions = [rx.get("reactionmeddrapt", "") for rx in r.get("patient", {}).get("reaction", [])]
        serious = r.get("serious", 1)
        for d in drugs:
            name = _canonical_name(d, "event")
            if not name:
                continue
            event_entry = {
                "reactions":  reactions[:5],
                "serious":    bool(serious),
                "outcome":    r.get("patient", {}).get("patientdeath", 0),
                "reported":   r.get("receiptdate", ""),
            }
            out.setdefault(name, []).append(event_entry)
    # Summarise: keep only top 5 events per drug, deduplicate reactions
    summary = {}
    for name, events in out.items():
        all_reactions = []
        for e in events:
            all_reactions.extend(e["reactions"])
        # Most frequent reactions
        freq = {}
        for rx in all_reactions:
            if rx:
                freq[rx] = freq.get(rx, 0) + 1
        top = sorted(freq, key=freq.get, reverse=True)[:10]

        serious_count = sum(1 for e in events if e["serious"])
        summary[name] = {
            "adverse_events":      top,
            "adverse_event_count": len(events),
            "serious_count":       serious_count,
        }
    log.info("  → %d adverse event drug profiles", len(summary))
    return summary


def fetch_recalls(limit: int) -> dict:
    """Returns {canonical_name: [recalls...]} from /drug/enforcement."""
    log.info("Fetching /drug/enforcement (limit=%d)…", limit)
    results = _get(OPENFDA_ENDPOINTS["enforcement"], limit)
    out = {}
    for r in results:
        name = _canonical_name(r, "enforcement")
        if not name:
            # try product_description
            desc = r.get("product_description", "").lower().split()[0] if r.get("product_description") else ""
            name = desc
        if not name:
            continue
        recall = {
            "recall_number":  r.get("recall_number", ""),
            "reason":         r.get("reason_for_recall", ""),
            "status":         r.get("status", ""),
            "classification": r.get("classification", ""),   # Class I / II / III
            "date":           r.get("recall_initiation_date", ""),
        }
        out.setdefault(name, []).append(recall)
    log.info("  → %d recall drug profiles", len(out))
    return out


# ── Merge ──────────────────────────────────────────────────────────────────────

def merge_all(labels, ndc, approvals, adverse, recalls) -> list:
    """Merge all dataset dicts into one list of unified drug documents."""
    # Start from labels as the base (most complete text info)
    all_names = set(labels) | set(ndc) | set(approvals) | set(adverse) | set(recalls)
    docs = []
    for name in all_names:
        doc = {
            "drug_name":         name,
            "brand_names":       [],
            "manufacturer":      "",
            "dosage_form":       "",
            "route":             [],
            "packaging":         [],
            "uses":              [],
            "dosage":            [],
            "warnings":          [],
            "side_effects":      [],
            "contraindications": [],
            "overdosage":        [],
            "adverse_events":    [],
            "adverse_event_count": 0,
            "serious_count":     0,
            "recalls":           [],
            "approval_status":   "",
            "approval_date":     "",
            "application_number":"",
            "sponsor_name":      "",
            "source_ids":        {},
            "data_sources":      [],
        }

        if name in labels:
            l = labels[name]
            doc.update({k: v for k, v in l.items() if v})
            doc["data_sources"].append("label")

        if name in ndc:
            n = ndc[name]
            if not doc["manufacturer"]: doc["manufacturer"] = n.get("manufacturer", "")
            if not doc["dosage_form"]:  doc["dosage_form"]  = n.get("dosage_form", "")
            doc["route"]     = n.get("route", [])
            doc["packaging"] = n.get("packaging", [])
            bn = n.get("brand_names", [])
            doc["brand_names"] = list(set(doc["brand_names"] + bn))
            doc["source_ids"].update(n.get("source_ids", {}))
            doc["data_sources"].append("ndc")

        if name in approvals:
            a = approvals[name]
            doc["approval_status"]    = a.get("approval_status", "")
            doc["approval_date"]      = a.get("approval_date", "")
            doc["application_number"] = a.get("application_number", "")
            doc["sponsor_name"]       = a.get("sponsor_name", "")
            doc["source_ids"].update(a.get("source_ids", {}))
            doc["data_sources"].append("drugsfda")

        if name in adverse:
            av = adverse[name]
            doc["adverse_events"]      = av.get("adverse_events", [])
            doc["adverse_event_count"] = av.get("adverse_event_count", 0)
            doc["serious_count"]       = av.get("serious_count", 0)
            doc["data_sources"].append("event")

        if name in recalls:
            doc["recalls"] = recalls[name]
            doc["data_sources"].append("enforcement")

        docs.append(doc)

    log.info("Merged → %d unified drug documents", len(docs))
    return docs


# ── Storage ────────────────────────────────────────────────────────────────────

def save_to_mongo(docs: list) -> bool:
    """Upsert documents into MongoDB.  Returns True on success."""
    try:
        from pymongo import MongoClient, UpdateOne
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.server_info()                          # ping
        coll = client[MONGO_DB][MONGO_COLL]
        ops = [
            UpdateOne(
                {"drug_name": d["drug_name"]},
                {"$set": d},
                upsert=True,
            )
            for d in docs
        ]
        result = coll.bulk_write(ops)
        log.info("MongoDB: %d upserted, %d modified",
                 result.upserted_count, result.modified_count)
        # Ensure text index for fast search
        coll.create_index([("drug_name", "text"), ("brand_names", "text")])
        return True
    except Exception as exc:
        log.warning("MongoDB unavailable (%s) — using JSON fallback.", exc)
        return False


def save_to_json(docs: list):
    """Write docs to the JSON fallback file."""
    OPENFDA_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENFDA_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info("JSON fallback written → %s  (%d docs)", OPENFDA_OUT_PATH, len(docs))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("═══════════════════════════════════════")
    log.info("  CareConnect · OpenFDA Ingest Pipeline ")
    log.info("═══════════════════════════════════════")
    t0 = time.time()

    labels   = fetch_labels(OPENFDA_LIMITS["label"])
    ndc      = fetch_ndc(OPENFDA_LIMITS["ndc"])
    approvals= fetch_drugsfda(OPENFDA_LIMITS["drugsfda"])
    adverse  = fetch_adverse_events(OPENFDA_LIMITS["event"])
    recalls  = fetch_recalls(OPENFDA_LIMITS["enforcement"])

    docs = merge_all(labels, ndc, approvals, adverse, recalls)

    # Try MongoDB first, fall back to JSON
    if not save_to_mongo(docs):
        save_to_json(docs)

    elapsed = time.time() - t0
    log.info("Pipeline complete in %.1fs  —  %d drug profiles ready.", elapsed, len(docs))
    return docs


if __name__ == "__main__":
    main()
