#!/usr/bin/env python3
"""
ClinicalTrials.gov Monitor v2
- Searches by indication (RA, Psoriasis, Crohn's, UC)
- Filters where sponsor OR collaborator class = INDUSTRY (catches all pharma/biotech)
- Detects changes vs stored state in 8 tracked fields
- record_type = 'New Trial' | 'Trial Update'
"""

import json, os, subprocess, time, hashlib
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

INDICATIONS = {
    "RA":       "Rheumatoid Arthritis",
    "Psoriasis":"Plaque Psoriasis",
    "Crohns":   "Crohn's Disease",
    "UC":       "Ulcerative Colitis",
}

TRACKED_FIELDS = [
    "overall_status", "enrollment_count", "brief_title",
    "interventions_hash", "primary_outcomes_hash",
    "eligibility_hash", "primary_completion_date", "study_type",
]

FIELD_LABELS = {
    "overall_status":          "Recruitment status",
    "enrollment_count":        "Enrollment target",
    "brief_title":             "Trial title",
    "interventions_hash":      "Interventions / dose",
    "primary_outcomes_hash":   "Primary outcome measures",
    "eligibility_hash":        "Eligibility criteria",
    "primary_completion_date": "Primary completion date",
    "study_type":              "Study type",
}

CT_API = "https://clinicaltrials.gov/api/v2/studies"

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def curl_get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "30", url,
        "-H", "Accept: application/json"], capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return {}

def supa_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}&limit=5000"
    r = subprocess.run(["curl", "-s", "--max-time", "20", url,
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json"],
        capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return []

def supa_upsert(table, data):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "POST",
        f"{SUPABASE_URL}/rest/v1/{table}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=merge-duplicates,return=minimal",
        "-d", json.dumps(data)], capture_output=True)

def supa_patch(table, nct_id, data):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "PATCH",
        f"{SUPABASE_URL}/rest/v1/{table}?nct_id=eq.{nct_id}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: return=minimal",
        "-d", json.dumps(data)], capture_output=True)

# ── Parse study from API ──────────────────────────────────────────────────────
def short_hash(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]

def parse_study(s, indication):
    ps          = s.get("protocolSection", {})
    id_mod      = ps.get("identificationModule", {})
    stat_mod    = ps.get("statusModule", {})
    design_mod  = ps.get("designModule", {})
    arms_mod    = ps.get("armsInterventionsModule", {})
    out_mod     = ps.get("outcomesModule", {})
    elig_mod    = ps.get("eligibilityModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})

    lead        = sponsor_mod.get("leadSponsor", {})
    collabs     = sponsor_mod.get("collaborators", [])

    interventions = [
        {"name": iv.get("name",""), "type": iv.get("type","")}
        for iv in arms_mod.get("interventions", [])
    ]
    primary_outcomes = [
        {"measure": o.get("measure",""), "timeFrame": o.get("timeFrame","")}
        for o in out_mod.get("primaryOutcomes", [])
    ]
    elig_text = elig_mod.get("eligibilityCriteria", "")

    return {
        # identifiers
        "nct_id":                  id_mod.get("nctId",""),
        "indication":              indication,
        "sponsor":                 lead.get("name",""),
        "sponsor_class":           lead.get("class",""),          # INDUSTRY | NIH | OTHER
        "collaborators":           [c.get("name","") for c in collabs],
        "collaborator_classes":    [c.get("class","") for c in collabs],
        # trial info
        "brief_title":             id_mod.get("briefTitle",""),
        "official_title":          id_mod.get("officialTitle",""),
        "overall_status":          stat_mod.get("overallStatus",""),
        "enrollment_count":        (design_mod.get("enrollmentInfo") or {}).get("count"),
        "study_type":              design_mod.get("studyType",""),
        # content
        "interventions":           interventions,
        "interventions_hash":      short_hash(interventions),
        "primary_outcomes":        primary_outcomes,
        "primary_outcomes_hash":   short_hash(primary_outcomes),
        "eligibility_criteria":    elig_text[:3000],
        "eligibility_hash":        short_hash(elig_text),
        # dates
        "primary_completion_date": (stat_mod.get("primaryCompletionDateStruct") or {}).get("date"),
        "first_post_date":         (stat_mod.get("studyFirstPostDateStruct") or {}).get("date"),
        "last_update_date":        (stat_mod.get("lastUpdatePostDateStruct") or {}).get("date"),
    }

def is_industry(rec):
    """True if lead sponsor OR any collaborator is INDUSTRY class."""
    if rec.get("sponsor_class","").upper() == "INDUSTRY":
        return True
    return "INDUSTRY" in [c.upper() for c in rec.get("collaborator_classes", [])]

# ── Fetch all trials for one indication ──────────────────────────────────────
def fetch_indication(ind_key, condition_str):
    results, page_token, page = [], None, 0
    while True:
        url = f"{CT_API}?query.cond={condition_str.replace(' ','+')}&pageSize=200"
        if page_token:
            url += f"&pageToken={page_token}"
        data    = curl_get(url)
        studies = data.get("studies", [])
        for s in studies:
            rec = parse_study(s, ind_key)
            if rec["nct_id"] and is_industry(rec):
                results.append(rec)
        page_token = data.get("nextPageToken")
        page += 1
        if not page_token or page > 20:
            break
        time.sleep(0.5)
    return results

# ── Change detection ──────────────────────────────────────────────────────────
def detect_changes(new_rec, stored):
    changed, details = [], []
    for field in TRACKED_FIELDS:
        nv = str(new_rec.get(field) or "")
        ov = str(stored.get(field) or "")
        if nv != ov:
            changed.append(field)
            if "hash" not in field:
                details.append(f"{FIELD_LABELS[field]}: '{ov}' → '{nv}'")
            else:
                details.append(f"{FIELD_LABELS[field]}: updated")
    return changed, details

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== ClinicalTrials.gov Monitor v2 — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Filter: sponsor or collaborator class = INDUSTRY")
    print("=" * 60)

    stored_rows = supa_get("clinical_trials", "select=*")
    stored = {r["nct_id"]: r for r in stored_rows if isinstance(stored_rows, list)}
    print(f"Stored trials in DB: {len(stored)}")

    now = datetime.now(timezone.utc).isoformat()
    new_count = changed_count = unchanged_count = 0

    for ind_key, condition_str in INDICATIONS.items():
        print(f"\n── {ind_key}: {condition_str} ──")
        studies = fetch_indication(ind_key, condition_str)
        print(f"  Industry-sponsored trials found: {len(studies)}")

        for rec in studies:
            nct = rec["nct_id"]
            if not nct:
                continue

            # Prepare Supabase-safe record (no extra keys)
            row = {
                "nct_id":                  nct,
                "indication":              rec["indication"],
                "sponsor":                 rec["sponsor"],
                "brief_title":             rec["brief_title"],
                "official_title":          rec["official_title"],
                "collaborators_arr":       rec["collaborators"],
                "overall_status":          rec["overall_status"],
                "enrollment_count":        rec["enrollment_count"],
                "study_type":              rec["study_type"],
                "interventions_json":      json.dumps(rec["interventions"]),
                "interventions_hash":      rec["interventions_hash"],
                "primary_outcomes_json":   json.dumps(rec["primary_outcomes"]),
                "primary_outcomes_hash":   rec["primary_outcomes_hash"],
                "eligibility_criteria":    rec["eligibility_criteria"],
                "eligibility_hash":        rec["eligibility_hash"],
                "primary_completion_date": rec["primary_completion_date"],
                "first_post_date":         rec["first_post_date"],
                "last_update_date":        rec["last_update_date"],
                "last_checked_at":         now,
            }

            if nct not in stored:
                # NEW TRIAL
                row["record_type"]    = "New Trial"
                row["has_changes"]    = False
                row["change_fields"]  = []
                row["change_summary"] = ""
                row["is_alert"]       = True
                row["alert_sent"]     = False
                row["first_seen_at"]  = now
                supa_upsert("clinical_trials", row)
                new_count += 1
                print(f"  ✨ NEW: {nct} | {rec['sponsor'][:30]} | {rec['brief_title'][:50]}")

            else:
                changed_fields, change_details = detect_changes(rec, stored[nct])
                if changed_fields:
                    row["record_type"]    = "Trial Update"
                    row["has_changes"]    = True
                    row["change_fields"]  = changed_fields
                    row["change_summary"] = "; ".join(change_details)
                    row["is_alert"]       = True
                    row["alert_sent"]     = False
                    supa_upsert("clinical_trials", row)
                    changed_count += 1
                    print(f"  🔄 UPDATE: {nct} | {', '.join(changed_fields)}")
                else:
                    supa_patch("clinical_trials", nct, {"last_checked_at": now})
                    unchanged_count += 1

    print(f"\n{'='*60}")
    print(f"New trials:     {new_count}")
    print(f"Updated trials: {changed_count}")
    print(f"Unchanged:      {unchanged_count}")
    print(f"Total alerts:   {new_count + changed_count}")

if __name__ == "__main__":
    main()
