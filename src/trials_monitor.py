#!/usr/bin/env python3
"""
ClinicalTrials.gov Monitor
- Searches by indication (RA, Psoriasis, Crohn's, UC)
- Filters by tracked pharma company sponsors/collaborators
- Detects changes vs stored state: status, enrollment, title, design,
  interventions, primary outcomes, eligibility criteria, completion date
- Alerts on: new trials + any tracked field change
"""

import json, os, re, subprocess, time, hashlib
from datetime import datetime, timezone, date

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# ── Target indications → ClinicalTrials.gov condition search terms ────────────
INDICATIONS = {
    "RA":       "Rheumatoid Arthritis",
    "Psoriasis":"Plaque Psoriasis",
    "Crohns":   "Crohn's Disease",
    "UC":       "Ulcerative Colitis",
}

# ── Companies to track (sponsor or collaborator must match) ──────────────────
TRACKED_COMPANIES = [
    "abbvie", "janssen", "johnson & johnson", "j&j",
    "roche", "genentech",
    "novartis",
    "bristol-myers", "bristol myers", "bms",
    "eli lilly", "lilly",
    "sanofi", "regeneron",
    "amgen",
    "takeda",
    "gilead",
    "boehringer ingelheim",
    "ucb",
    "pfizer",
    "merck",
    "sun pharma",
    "alumis",
    "astrazeneca",
    "galaxy biotech",
]

# ── Fields to track for change detection ────────────────────────────────────
TRACKED_FIELDS = [
    "overall_status",       # recruitment status
    "enrollment_count",     # recruitment number
    "brief_title",          # title
    "interventions_hash",   # dose/intervention (hashed JSON)
    "primary_outcomes_hash",# primary outcome measures
    "eligibility_hash",     # inclusion/exclusion criteria
    "primary_completion_date",
    "study_type",
]

FIELD_LABELS = {
    "overall_status":         "Recruitment status",
    "enrollment_count":       "Enrollment target",
    "brief_title":            "Trial title",
    "interventions_hash":     "Interventions / dose",
    "primary_outcomes_hash":  "Primary outcome measures",
    "eligibility_hash":       "Eligibility criteria",
    "primary_completion_date":"Primary completion date",
    "study_type":             "Study type / design",
}

CT_API = "https://clinicaltrials.gov/api/v2/studies"

# ── HTTP helpers ─────────────────────────────────────────────────────────────
def curl_get(url):
    r = subprocess.run(
        ["curl", "-s", "--max-time", "30", url,
         "-H", "Accept: application/json"],
        capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return {}

def supa_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}&limit=5000"
    r = subprocess.run([
        "curl", "-s", "--max-time", "20", url,
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json",
    ], capture_output=True, text=True)
    try:    return json.loads(r.stdout)
    except: return []

def supa_upsert(table, data):
    payload = json.dumps(data)
    r = subprocess.run([
        "curl", "-s", "--max-time", "20", "-X", "POST",
        f"{SUPABASE_URL}/rest/v1/{table}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=merge-duplicates,return=minimal",
        "-d", payload,
    ], capture_output=True, text=True)

def supa_patch(table, nct_id, data):
    payload = json.dumps(data)
    subprocess.run([
        "curl", "-s", "--max-time", "20", "-X", "PATCH",
        f"{SUPABASE_URL}/rest/v1/{table}?nct_id=eq.{nct_id}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: return=minimal",
        "-d", payload,
    ], capture_output=True)

# ── Parse API study record ───────────────────────────────────────────────────
def parse_study(s, indication):
    ps = s.get("protocolSection", {})
    id_mod    = ps.get("identificationModule", {})
    stat_mod  = ps.get("statusModule", {})
    design_mod= ps.get("designModule", {})
    arms_mod  = ps.get("armsInterventionsModule", {})
    out_mod   = ps.get("outcomesModule", {})
    elig_mod  = ps.get("eligibilityModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})

    nct_id = id_mod.get("nctId", "")

    # Interventions — deduplicated list of name+type
    interventions = [
        {"name": iv.get("name",""), "type": iv.get("type","")}
        for iv in arms_mod.get("interventions", [])
    ]
    # Primary outcomes
    primary_outcomes = [
        {"measure": o.get("measure",""), "timeFrame": o.get("timeFrame","")}
        for o in out_mod.get("primaryOutcomes", [])
    ]
    elig_text = elig_mod.get("eligibilityCriteria", "")

    def short_hash(obj):
        return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]

    sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "")
    collaborators = [c.get("name","") for c in sponsor_mod.get("collaborators", [])]

    pc_date = (stat_mod.get("primaryCompletionDateStruct") or {}).get("date")
    fp_date = (stat_mod.get("studyFirstPostDateStruct") or {}).get("date")
    lu_date = (stat_mod.get("lastUpdatePostDateStruct") or {}).get("date")

    return {
        "nct_id":                  nct_id,
        "indication":              indication,
        "brief_title":             id_mod.get("briefTitle",""),
        "official_title":          id_mod.get("officialTitle",""),
        "sponsor":                 sponsor,
        "collaborators":           collaborators,
        "overall_status":          stat_mod.get("overallStatus",""),
        "enrollment_count":        (design_mod.get("enrollmentInfo") or {}).get("count"),
        "study_type":              design_mod.get("studyType",""),
        "interventions":           interventions,
        "interventions_hash":      short_hash(interventions),
        "primary_outcomes":        primary_outcomes,
        "primary_outcomes_hash":   short_hash(primary_outcomes),
        "eligibility_criteria":    elig_text[:3000],
        "eligibility_hash":        short_hash(elig_text),
        "primary_completion_date": pc_date,
        "first_post_date":         fp_date,
        "last_update_date":        lu_date,
    }

def is_tracked_company(study_record):
    all_orgs = [study_record["sponsor"]] + study_record["collaborators"]
    all_orgs_lower = " ".join(o.lower() for o in all_orgs if o)
    return any(co in all_orgs_lower for co in TRACKED_COMPANIES)

# ── Fetch all trials for one indication ─────────────────────────────────────
def fetch_indication(indication_key, condition_str):
    results = []
    page_token = None
    page = 0
    while True:
        params = f"query.cond={condition_str.replace(' ','+')}&pageSize=200"
        if page_token:
            params += f"&pageToken={page_token}"
        url = f"{CT_API}?{params}"
        data = curl_get(url)
        studies = data.get("studies", [])
        for s in studies:
            rec = parse_study(s, indication_key)
            if rec["nct_id"] and is_tracked_company(rec):
                results.append(rec)
        page_token = data.get("nextPageToken")
        page += 1
        if not page_token or page > 20:  # safety: max 20 pages = 4000 studies
            break
        time.sleep(0.5)  # polite rate limiting
    return results

# ── Compare vs stored state ──────────────────────────────────────────────────
def detect_changes(new_rec, stored_rec):
    changed = []
    details = []
    for field in TRACKED_FIELDS:
        new_val = new_rec.get(field)
        old_val = stored_rec.get(field)
        if new_val is None and old_val is None:
            continue
        if str(new_val) != str(old_val):
            label = FIELD_LABELS.get(field, field)
            changed.append(field)
            if "hash" not in field:
                details.append(f"{label}: '{old_val}' → '{new_val}'")
            else:
                details.append(f"{label}: updated")
    return changed, details

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== ClinicalTrials.gov Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Tracking {len(TRACKED_COMPANIES)} companies across {len(INDICATIONS)} indications")
    print("=" * 60)

    # Load existing stored trials into lookup dict
    stored_rows = supa_get("clinical_trials", "select=*")
    stored = {r["nct_id"]: r for r in stored_rows if isinstance(stored_rows, list)}
    print(f"Stored trials: {len(stored)}")

    now = datetime.now(timezone.utc).isoformat()
    total_new = total_changed = total_unchanged = 0

    for ind_key, condition_str in INDICATIONS.items():
        print(f"\n── {ind_key}: {condition_str} ──")
        studies = fetch_indication(ind_key, condition_str)
        print(f"  Found {len(studies)} relevant trials")

        for rec in studies:
            nct = rec["nct_id"]
            rec["last_checked_at"] = now

            if nct not in stored:
                # NEW trial
                rec["is_new"]      = True
                rec["has_changes"] = False
                rec["change_fields"]  = []
                rec["change_summary"] = "New trial — first seen"
                rec["is_alert"]    = True
                rec["alert_sent"]  = False
                rec["first_seen_at"] = now
                # Store interventions+outcomes as JSON strings for Supabase
                rec["interventions_json"]    = json.dumps(rec.pop("interventions"))
                rec["primary_outcomes_json"] = json.dumps(rec.pop("primary_outcomes"))
                rec["collaborators_arr"]     = rec.pop("collaborators")
                supa_upsert("clinical_trials", rec)
                total_new += 1
                print(f"  ✨ NEW: {nct} | {rec['brief_title'][:60]}")

            else:
                # EXISTING — check for changes
                prev = stored[nct]
                changed_fields, change_details = detect_changes(rec, prev)

                if changed_fields:
                    change_summary = "; ".join(change_details)
                    update = {
                        "overall_status":          rec["overall_status"],
                        "enrollment_count":        rec["enrollment_count"],
                        "brief_title":             rec["brief_title"],
                        "official_title":          rec["official_title"],
                        "interventions_hash":      rec["interventions_hash"],
                        "interventions_json":      json.dumps(rec["interventions"]),
                        "primary_outcomes_hash":   rec["primary_outcomes_hash"],
                        "primary_outcomes_json":   json.dumps(rec["primary_outcomes"]),
                        "eligibility_hash":        rec["eligibility_hash"],
                        "eligibility_criteria":    rec["eligibility_criteria"],
                        "primary_completion_date": rec["primary_completion_date"],
                        "last_update_date":        rec["last_update_date"],
                        "study_type":              rec["study_type"],
                        "last_checked_at":         now,
                        "is_new":                  False,
                        "has_changes":             True,
                        "change_fields":           changed_fields,
                        "change_summary":          change_summary,
                        "is_alert":                True,
                        "alert_sent":              False,
                    }
                    supa_patch("clinical_trials", nct, update)
                    total_changed += 1
                    print(f"  🔄 CHANGED: {nct} | {', '.join(changed_fields)}")
                else:
                    supa_patch("clinical_trials", nct, {"last_checked_at": now})
                    total_unchanged += 1

    print(f"\n=== Summary ===")
    print(f"  New trials:      {total_new}")
    print(f"  Changed trials:  {total_changed}")
    print(f"  Unchanged:       {total_unchanged}")
    print(f"  Total alerts:    {total_new + total_changed}")

if __name__ == "__main__":
    main()
