#!/usr/bin/env python3
"""
ClinicalTrials.gov Monitor v3

Flow:
  1. Fetch only trials updated TODAY matching our 4 indications + industry sponsor
  2. For each trial, pull version history from CT.gov API
  3. Fetch last 2 versions and diff the key competitive fields
  4. LLM judges: is this change alert-worthy?
  5. Upsert to Supabase with change_summary; is_alert=True only if LLM confirms
  6. Cleanup: delete rows with no meaningful data (leftover from old monitor)

Old behaviour (v2): fetched ALL trials, flagged every hash change as alert.
New behaviour (v3): today-only, versioned diff, LLM-filtered.
"""

import json, os, subprocess, time, hashlib
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GROQ_KEY     = os.environ.get("GROQ_KEY", "")

INDICATIONS = {
    "RA":       "Rheumatoid Arthritis",
    "Psoriasis":"Plaque Psoriasis",
    "Crohns":   "Crohn's Disease",
    "UC":       "Ulcerative Colitis",
}

# Fields that matter for competitive intelligence (used in diff + LLM prompt)
ALERT_FIELDS = {
    "overall_status":          "Recruitment status",
    "enrollment_count":        "Enrollment target",
    "phase":                   "Trial phase",
    "primary_completion_date": "Primary completion date",
    "interventions_hash":      "Drug/intervention arms",
    "primary_outcomes_hash":   "Primary endpoints",
}

CT_API = "https://clinicaltrials.gov/api/v2"

# ── Helpers ───────────────────────────────────────────────────────────────────

def curl_get(url, timeout=30):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), url,
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

def supa_delete(table, filter_str):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "DELETE",
        f"{SUPABASE_URL}/rest/v1/{table}?{filter_str}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Prefer: return=minimal"],
        capture_output=True)

def short_hash(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]

def groq_call(prompt, max_tokens=120):
    if not GROQ_KEY: return ""
    payload = json.dumps({"model": "llama-3.1-8b-instant", "max_tokens": max_tokens,
        "temperature": 0, "messages": [{"role": "user", "content": prompt}]})
    r = subprocess.run(["curl", "-s", "--max-time", "30",
        "https://api.groq.com/openai/v1/chat/completions",
        "-H", f"Authorization: Bearer {GROQ_KEY}",
        "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        if "choices" in d: return d["choices"][0]["message"]["content"].strip()
    except: pass
    return ""

# ── Parse study JSON → flat record ────────────────────────────────────────────

def parse_study(s, indication=""):
    ps          = s.get("protocolSection", {})
    id_mod      = ps.get("identificationModule", {})
    stat_mod    = ps.get("statusModule", {})
    design_mod  = ps.get("designModule", {})
    arms_mod    = ps.get("armsInterventionsModule", {})
    out_mod     = ps.get("outcomesModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})

    lead    = sponsor_mod.get("leadSponsor", {})
    collabs = sponsor_mod.get("collaborators", [])

    interventions = [
        {"name": iv.get("name", ""), "type": iv.get("type", "")}
        for iv in arms_mod.get("interventions", [])
    ]
    primary_outcomes = [
        {"measure": o.get("measure", ""), "timeFrame": o.get("timeFrame", "")}
        for o in out_mod.get("primaryOutcomes", [])
    ]
    phases = design_mod.get("phases", [])

    return {
        "nct_id":                  id_mod.get("nctId", ""),
        "indication":              indication,
        "sponsor":                 lead.get("name", ""),
        "sponsor_class":           lead.get("class", ""),
        "collaborators":           [c.get("name", "") for c in collabs],
        "collaborator_classes":    [c.get("class", "") for c in collabs],
        "brief_title":             id_mod.get("briefTitle", ""),
        "official_title":          id_mod.get("officialTitle", ""),
        "overall_status":          stat_mod.get("overallStatus", ""),
        "enrollment_count":        (design_mod.get("enrollmentInfo") or {}).get("count"),
        "study_type":              design_mod.get("studyType", ""),
        "phase":                   ", ".join(phases),
        "interventions":           interventions,
        "interventions_hash":      short_hash(interventions),
        "primary_outcomes":        primary_outcomes,
        "primary_outcomes_hash":   short_hash(primary_outcomes),
        "primary_completion_date": (stat_mod.get("primaryCompletionDateStruct") or {}).get("date"),
        "first_post_date":         (stat_mod.get("studyFirstPostDateStruct") or {}).get("date"),
        "last_update_date":        (stat_mod.get("lastUpdatePostDateStruct") or {}).get("date"),
    }

def is_industry(rec):
    if rec.get("sponsor_class", "").upper() == "INDUSTRY":
        return True
    return "INDUSTRY" in [c.upper() for c in rec.get("collaborator_classes", [])]

# ── CT.gov API: today's updates ───────────────────────────────────────────────

def fetch_updated_today(ind_key, condition_str):
    """
    Query CT.gov for trials matching this indication that were updated
    in the last 2 days (yesterday → today, to handle timezone lag).
    """
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    results, page_token, page = [], None, 0

    while True:
        url = (f"{CT_API}/studies"
               f"?query.cond={condition_str.replace(' ', '+')}"
               f"&filter.advanced=AREA[LastUpdatePostDate]RANGE[{yesterday},MAX]"
               f"&pageSize=100")
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
        if not page_token or page > 5:
            break
        time.sleep(0.3)

    return results

# ── CT.gov API: version history + versioned fetch ─────────────────────────────

def get_version_history(nct_id):
    """
    Returns list of version dicts from CT.gov history API.
    Each item has at least a version number and date.
    CT.gov returns: [{"version": N, "date": "YYYY-MM-DD", ...}, ...]
    """
    url  = f"{CT_API}/studies/{nct_id}/history"
    data = curl_get(url, timeout=20)

    # API returns different shapes — normalise to list
    if isinstance(data, list):
        history = data
    else:
        # try common envelope keys
        for key in ("studies", "changes", "versions", "history"):
            if key in data and isinstance(data[key], list):
                history = data[key]
                break
        else:
            history = []

    # Normalise version number field name
    normalised = []
    for item in history:
        vnum = item.get("version") or item.get("versionNumber") or item.get("ver")
        vdate = item.get("date") or item.get("postDate") or ""
        if vnum is not None:
            normalised.append({"version": int(vnum), "date": vdate})

    return sorted(normalised, key=lambda x: x["version"])

def fetch_version(nct_id, version_number):
    """Fetch a specific historical version of a trial from CT.gov."""
    # CT.gov v2 API supports ?historicVersion=N
    url  = f"{CT_API}/studies/{nct_id}?historicVersion={version_number}"
    data = curl_get(url, timeout=20)
    if data.get("protocolSection"):
        return data
    # Fallback: try the plain endpoint (returns current)
    return None

# ── Diff two parsed versions ──────────────────────────────────────────────────

def diff_versions(old_rec, new_rec):
    """
    Compare alert-relevant fields between two parsed study records.
    Returns list of human-readable change strings.
    """
    changes = []
    for field, label in ALERT_FIELDS.items():
        old_val = str(old_rec.get(field) or "")
        new_val = str(new_rec.get(field) or "")
        if old_val != new_val:
            if "hash" in field:
                changes.append(f"{label}: content changed")
            else:
                changes.append(f"{label}: '{old_val}' → '{new_val}'")
    return changes

# ── LLM: is this diff alert-worthy? ──────────────────────────────────────────

def llm_judge(nct_id, sponsor, brief_title, indication, changes):
    """
    Ask Groq whether the observed changes are competitive-intelligence-worthy.
    Returns (is_alert: bool, summary: str)
    """
    if not changes:
        return False, ""

    changes_text = "\n".join(f"  - {c}" for c in changes)

    prompt = f"""You are a pharma competitive intelligence analyst reviewing a clinical trial update.

Trial: {nct_id}
Title: {brief_title[:120]}
Sponsor: {sponsor}
Indication: {indication}

Changes detected between last 2 versions:
{changes_text}

ALERT-WORTHY (answer ALERT):
- Status changed to Completed, Terminated, Active not recruiting, Suspended
- Primary endpoint measures changed (not just time frames)
- New drug arm or intervention added/removed
- Enrollment target changed by >20%
- Phase changed
- Primary completion date moved significantly (>6 months)

NOT alert-worthy (answer SKIP):
- Administrative text edits or typo fixes
- Minor wording in eligibility criteria
- Contact/location updates
- Date format corrections
- No change to actual drug, endpoint, status, or enrollment

Reply with exactly:
ALERT: [one sentence — what changed and why it matters for pharma competitive intelligence]
or
SKIP: [brief reason]"""

    resp = groq_call(prompt, max_tokens=100)
    if resp:
        upper = resp.upper()
        if upper.startswith("ALERT:"):
            return True, resp[6:].strip()
        if upper.startswith("ALERT"):
            # model sometimes skips the colon
            return True, resp[5:].strip()
    return False, ""

# ── Cleanup: remove stale/meaningless records ─────────────────────────────────

def cleanup_stale():
    """
    Remove Trial Update rows that have no change_summary and haven't been sent.
    These are leftovers from the old v2 monitor that flagged every hash change.
    Also remove New Trial rows for trials posted before 2024 (pre-monitor era).
    """
    # 1. Trial Updates with no real change summary, unsent
    stale_updates = supa_get("clinical_trials",
        "select=nct_id,change_summary"
        "&record_type=eq.Trial Update&alert_sent=eq.false")
    deleted = 0
    if isinstance(stale_updates, list):
        for r in stale_updates:
            if not (r.get("change_summary") or "").strip():
                supa_delete("clinical_trials",
                    f"nct_id=eq.{r['nct_id']}&alert_sent=eq.false")
                deleted += 1

    # 2. New Trial rows for old trials (first_post_date before 2024)
    old_trials = supa_get("clinical_trials",
        "select=nct_id,first_post_date"
        "&record_type=eq.New Trial&alert_sent=eq.false"
        "&first_post_date=lt.2024-01-01")
    if isinstance(old_trials, list):
        for r in old_trials:
            supa_delete("clinical_trials",
                f"nct_id=eq.{r['nct_id']}&alert_sent=eq.false")
            deleted += 1

    if deleted:
        print(f"🧹 Cleaned up {deleted} stale/old records")
    else:
        print("🧹 No stale records to clean")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n=== ClinicalTrials.gov Monitor v3 — {now_str} ===")
    print("Mode: today's updates only · version-diff · LLM-judged")
    print("=" * 60)

    # Step 0: clean up stale records first
    cleanup_stale()

    now = datetime.now(timezone.utc).isoformat()
    new_alert_count = upd_alert_count = skip_count = 0

    # 60-day cutoff for "genuinely new" trials
    new_cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")

    for ind_key, condition_str in INDICATIONS.items():
        print(f"\n── {ind_key} ({condition_str}) ──")
        studies = fetch_updated_today(ind_key, condition_str)
        print(f"  Updated today (industry): {len(studies)}")

        # Load existing stored record for these NCT IDs (to detect new vs update)
        nct_ids = [r["nct_id"] for r in studies if r["nct_id"]]
        if not nct_ids:
            continue

        # Fetch stored rows for this batch
        id_filter = ",".join(f'"{n}"' for n in nct_ids)
        stored_rows = supa_get("clinical_trials",
            f"select=nct_id,overall_status,enrollment_count,phase,"
            f"interventions_hash,primary_outcomes_hash,primary_completion_date"
            f"&nct_id=in.({id_filter})")
        stored = {r["nct_id"]: r for r in stored_rows if isinstance(stored_rows, list)}

        for rec in studies:
            nct = rec["nct_id"]
            is_new = nct not in stored

            # Base Supabase row
            row = {
                "nct_id":                  nct,
                "indication":              ind_key,
                "sponsor":                 rec["sponsor"],
                "brief_title":             rec["brief_title"],
                "official_title":          (rec.get("official_title") or "")[:500],
                "collaborators_arr":       rec["collaborators"],
                "overall_status":          rec["overall_status"],
                "enrollment_count":        rec["enrollment_count"],
                "study_type":              rec["study_type"],
                "interventions_json":      json.dumps(rec["interventions"]),
                "interventions_hash":      rec["interventions_hash"],
                "primary_outcomes_json":   json.dumps(rec["primary_outcomes"]),
                "primary_outcomes_hash":   rec["primary_outcomes_hash"],
                "eligibility_hash":        "",
                "primary_completion_date": rec["primary_completion_date"],
                "first_post_date":         rec["first_post_date"],
                "last_update_date":        rec["last_update_date"],
                "last_checked_at":         now,
            }

            if is_new:
                # ── NEW TRIAL ──────────────────────────────────────────────
                first_post = rec.get("first_post_date") or ""
                is_recent  = first_post >= new_cutoff

                row.update({
                    "record_type":   "New Trial",
                    "has_changes":   False,
                    "change_fields": [],
                    "first_seen_at": now,
                })

                if is_recent:
                    row.update({
                        "is_alert":       True,
                        "alert_sent":     False,
                        "change_summary": (f"New {ind_key} trial by {rec['sponsor']} "
                                           f"({rec['overall_status']})"),
                    })
                    supa_upsert("clinical_trials", row)
                    new_alert_count += 1
                    print(f"  ✨ NEW (alerting): {nct} | {rec['sponsor'][:28]} "
                          f"| {rec['brief_title'][:45]}")
                else:
                    # Old trial — store silently so we track future updates
                    row.update({
                        "is_alert":       False,
                        "alert_sent":     True,   # suppress email
                        "change_summary": "",
                    })
                    supa_upsert("clinical_trials", row)
                    print(f"  📋 STORED (old, no alert): {nct} | first posted {first_post}")

            else:
                # ── UPDATED TRIAL ──────────────────────────────────────────
                # Step 1: get version history from CT.gov
                history = get_version_history(nct)
                time.sleep(0.3)

                changes = []

                if len(history) >= 2:
                    v_prev = history[-2]["version"]
                    v_curr = history[-1]["version"]
                    print(f"  🔍 {nct}: versions {v_prev} → {v_curr} "
                          f"(updated {rec['last_update_date']})")

                    old_data = fetch_version(nct, v_prev)
                    time.sleep(0.3)
                    new_data = fetch_version(nct, v_curr)
                    time.sleep(0.3)

                    if old_data and new_data:
                        old_parsed = parse_study(old_data, ind_key)
                        new_parsed = parse_study(new_data, ind_key)
                        changes    = diff_versions(old_parsed, new_parsed)
                        print(f"       Version diff: {len(changes)} field(s) changed")
                    else:
                        # Versioned fetch failed — fall back to comparing against DB
                        print(f"       Version fetch failed — using DB diff")
                        for field, label in ALERT_FIELDS.items():
                            ov = str(stored[nct].get(field) or "")
                            nv = str(rec.get(field) or "")
                            if ov != nv:
                                changes.append(f"{label}: '{ov}' → '{nv}'")
                else:
                    # No history available (e.g. single-version trial)
                    for field, label in ALERT_FIELDS.items():
                        ov = str(stored[nct].get(field) or "")
                        nv = str(rec.get(field) or "")
                        if ov != nv:
                            changes.append(f"{label}: '{ov}' → '{nv}'")
                    if changes:
                        print(f"  🔍 {nct}: no history API — DB diff shows "
                              f"{len(changes)} change(s)")

                if not changes:
                    # Nothing changed in alert fields (e.g. only text/contact update)
                    skip_count += 1
                    print(f"  ⬜ {nct}: no alert-field changes — skipping")
                    continue

                # Step 2: LLM judges the diff
                is_alert, summary = llm_judge(
                    nct, rec["sponsor"], rec["brief_title"], ind_key, changes)
                time.sleep(0.5)

                row.update({
                    "record_type":   "Trial Update",
                    "has_changes":   True,
                    "change_fields": [c.split(":")[0] for c in changes],
                    "change_summary": summary if is_alert else "; ".join(changes[:3]),
                    "is_alert":      is_alert,
                    "alert_sent":    not is_alert,
                })
                supa_upsert("clinical_trials", row)

                if is_alert:
                    upd_alert_count += 1
                    print(f"  🔔 ALERT: {nct} — {summary[:70]}")
                else:
                    skip_count += 1
                    print(f"  ⬜ SKIP:  {nct} — {changes[0][:60]}")

    print(f"\n{'='*60}")
    print(f"New trial alerts:    {new_alert_count}")
    print(f"Update alerts:       {upd_alert_count}")
    print(f"Skipped (trivial):   {skip_count}")
    print(f"Total alerts queued: {new_alert_count + upd_alert_count}")

if __name__ == "__main__":
    main()
