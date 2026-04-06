#!/usr/bin/env python3
"""
Email alerts — sends digests for both news articles and clinical trial changes.
Usage:
  python email_alerts.py           # news alerts only
  python email_alerts.py --source trials   # trial alerts only
  python email_alerts.py --source all      # both in one email
"""

import os, json, subprocess, smtplib, sys, argparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GMAIL_USER   = os.environ["GMAIL_USER"]
GMAIL_PASS   = os.environ["GMAIL_APP_PASS"]
ALERT_TO     = os.environ.get("ALERT_EMAIL", os.environ["GMAIL_USER"])

CATEGORY_EMOJI = {"clinical": "🔬", "regulatory": "📋", "commercial": "💼"}
SCORE_LABEL    = {10:"🚨 CRITICAL", 9:"🔴 HIGH", 8:"🟠 HIGH", 7:"🟡 MEDIUM", 6:"🟢 NOTABLE"}
STATUS_EMOJI   = {"Recruiting":"🟢", "Active, not recruiting":"🔵", "Completed":"✅",
                  "Terminated":"🔴", "Withdrawn":"⚫", "Not yet recruiting":"⚪"}

def supa_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = subprocess.run(["curl","-s","-H",f"apikey: {SUPABASE_KEY}",
        "-H",f"Authorization: Bearer {SUPABASE_KEY}","-H","Accept: application/json",url],
        capture_output=True, text=True, timeout=30)
    try:    return json.loads(r.stdout)
    except: return []

def supa_patch(table, filt, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filt}"
    subprocess.run(["curl","-s","-X","PATCH","-H",f"apikey: {SUPABASE_KEY}",
        "-H",f"Authorization: Bearer {SUPABASE_KEY}",
        "-H","Content-Type: application/json","-H","Prefer: return=minimal",
        url,"-d",json.dumps(data)], capture_output=True, timeout=30)

# ── HTML builders ─────────────────────────────────────────────────────────────
def news_card(a):
    score   = a.get("relevance_score") or 0
    cat     = a.get("category") or "unknown"
    emoji   = CATEGORY_EMOJI.get(cat, "📰")
    label   = SCORE_LABEL.get(score, f"Score {score}")
    title   = a.get("catchy_title") or a.get("raw_title") or "No title"
    summary = a.get("summary") or ""
    alert_t = a.get("alert_text") or ""
    drug    = a.get("product_name") or ""
    company = a.get("company") or ""
    ind     = a.get("indication") or ""
    url     = a.get("url") or "#"
    date_s  = a.get("article_date") or ""
    meta    = " · ".join(p for p in [drug, company, ind, date_s] if p)
    return f"""
    <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:16px;">
      <div style="margin-bottom:8px;">
        <span style="font-size:16px;">{emoji}</span>
        <span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;color:#444;margin-left:6px;">{label}</span>
        <span style="background:#e8f4fd;border-radius:4px;padding:2px 8px;font-size:12px;color:#1a73e8;margin-left:4px;text-transform:uppercase;">{cat}</span>
      </div>
      <h3 style="margin:0 0 4px 0;font-size:15px;"><a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a></h3>
      <p style="margin:0 0 10px 0;font-size:12px;color:#888;">{meta}</p>
      <p style="margin:0 0 10px 0;font-size:14px;color:#333;line-height:1.5;">{summary}</p>
      {"<div style='background:#fff8e1;border-left:4px solid #ffc107;padding:10px 14px;border-radius:0 4px 4px 0;font-size:13px;'><strong>⚠️ Alert:</strong> " + alert_t + "</div>" if alert_t else ""}
    </div>"""

def trial_card(t):
    is_new     = t.get("is_new", False)
    nct        = t.get("nct_id","")
    title      = t.get("brief_title","")
    sponsor    = t.get("sponsor","")
    status     = t.get("overall_status","")
    enrollment = t.get("enrollment_count")
    ind        = t.get("indication","")
    changes    = t.get("change_summary","")
    fp_date    = t.get("first_post_date","")
    lu_date    = t.get("last_update_date","")
    url        = f"https://clinicaltrials.gov/study/{nct}"
    badge      = "✨ NEW TRIAL" if is_new else "🔄 UPDATED"
    badge_color= "#27ae60" if is_new else "#e67e22"
    st_emoji   = STATUS_EMOJI.get(status, "🔘")
    return f"""
    <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:16px;">
      <div style="margin-bottom:8px;">
        <span style="background:{badge_color};color:#fff;border-radius:4px;padding:2px 10px;font-size:12px;font-weight:600;">{badge}</span>
        <span style="background:#f3e5f5;border-radius:4px;padding:2px 8px;font-size:12px;color:#7b1fa2;margin-left:6px;">{ind}</span>
      </div>
      <h3 style="margin:0 0 4px 0;font-size:15px;"><a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a></h3>
      <p style="margin:0 0 8px 0;font-size:12px;color:#888;">{nct} · {sponsor}</p>
      <p style="margin:0 0 8px 0;font-size:13px;color:#333;">
        {st_emoji} <strong>{status}</strong>
        {"  ·  Enrollment: <strong>" + str(enrollment) + "</strong>" if enrollment else ""}
        {"  ·  First posted: " + fp_date if fp_date and is_new else ""}
        {"  ·  Last updated: " + lu_date if lu_date and not is_new else ""}
      </p>
      {"<div style='background:#e3f2fd;border-left:4px solid #1a73e8;padding:8px 12px;border-radius:0 4px 4px 0;font-size:13px;color:#333;'><strong>What changed:</strong> " + changes + "</div>" if changes and not is_new else ""}
    </div>"""

def build_email_html(news_articles, trials, today):
    sections = ""
    if news_articles:
        sections += f"<h2 style='color:#1a1a1a;font-size:18px;margin:20px 0 12px 0;'>📰 News Alerts ({len(news_articles)})</h2>"
        sections += "".join(news_card(a) for a in news_articles)
    if trials:
        sections += f"<h2 style='color:#1a1a1a;font-size:18px;margin:20px 0 12px 0;'>🧪 Clinical Trial Updates ({len(trials)})</h2>"
        sections += "".join(trial_card(t) for t in trials)
    total = len(news_articles) + len(trials)
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
    <div style="max-width:720px;margin:0 auto;">
      <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);border-radius:8px 8px 0 0;padding:24px;color:#fff;">
        <h1 style="margin:0;font-size:22px;">💊 Pharma Intelligence Monitor</h1>
        <p style="margin:6px 0 0 0;opacity:0.85;font-size:14px;">{total} alert{"s" if total!=1 else ""} · RA · Psoriasis · Crohn's · UC · {today}</p>
      </div>
      <div style="background:#f5f5f5;padding:20px;">{sections}</div>
      <div style="text-align:center;padding:16px;font-size:12px;color:#999;">Automated monitoring · Pauses when nothing new</div>
    </div></body></html>"""

def build_email_plain(news_articles, trials, today):
    lines = [f"PHARMA INTELLIGENCE MONITOR — {today}", "="*60]
    if news_articles:
        lines.append(f"\nNEWS ALERTS ({len(news_articles)})")
        for i, a in enumerate(news_articles, 1):
            lines += [
                f"\n[{i}] Score {a.get('relevance_score')}/10 | {(a.get('category') or '').upper()} | {a.get('product_name','')} ({a.get('company','')})",
                f"    {a.get('catchy_title') or a.get('raw_title','')}",
                f"    {a.get('summary','')[:200]}",
                f"    {a.get('url','')}",
            ]
    if trials:
        lines.append(f"\nCLINICAL TRIAL UPDATES ({len(trials)})")
        for i, t in enumerate(trials, 1):
            badge = "NEW" if t.get("is_new") else "UPDATED"
            lines += [
                f"\n[{i}] {badge} | {t.get('indication','')} | {t.get('sponsor','')}",
                f"    {t.get('brief_title','')}",
                f"    Status: {t.get('overall_status','')} | Enrollment: {t.get('enrollment_count','')}",
                f"    https://clinicaltrials.gov/study/{t.get('nct_id','')}",
            ]
            if not t.get("is_new") and t.get("change_summary"):
                lines.append(f"    Changes: {t.get('change_summary','')}")
    return "\n".join(lines)

def send_email(news_articles, trials):
    total = len(news_articles) + len(trials)
    today = datetime.utcnow().strftime("%B %d, %Y")
    parts = []
    if news_articles: parts.append(f"{len(news_articles)} news")
    if trials:        parts.append(f"{len(trials)} trial update{'s' if len(trials)!=1 else ''}")
    subject = f"[Pharma Alert] {' + '.join(parts)} — {datetime.utcnow().strftime('%b %d')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Pharma Monitor <{GMAIL_USER}>"
    msg["To"]      = ALERT_TO
    msg.attach(MIMEText(build_email_plain(news_articles, trials, today), "plain"))
    msg.attach(MIMEText(build_email_html(news_articles, trials, today),  "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS)
        srv.sendmail(GMAIL_USER, ALERT_TO, msg.as_string())
    print(f"[OK] Email sent → {ALERT_TO} | {subject}")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="news", choices=["news","trials","all"])
    args = parser.parse_args()

    print(f"=== Email Alerts ({args.source}) ===")
    news_articles, trials = [], []

    if args.source in ("news", "all"):
        news_articles = supa_get("articles",
            "select=id,catchy_title,raw_title,product_name,company,indication,"
            "category,relevance_score,summary,alert_text,article_date,url"
            "&is_alert=eq.true&alert_sent=eq.false&order=relevance_score.desc")
        if not isinstance(news_articles, list): news_articles = []
        news_articles.sort(key=lambda x: x.get("relevance_score") or 0, reverse=True)
        print(f"News alerts:  {len(news_articles)}")

    if args.source in ("trials", "all"):
        trials = supa_get("clinical_trials",
            "select=nct_id,indication,brief_title,sponsor,overall_status,"
            "enrollment_count,is_new,change_summary,first_post_date,last_update_date"
            "&is_alert=eq.true&alert_sent=eq.false&order=first_seen_at.desc")
        if not isinstance(trials, list): trials = []
        # New trials first, then changes
        trials.sort(key=lambda x: (0 if x.get("is_new") else 1))
        print(f"Trial alerts: {len(trials)}")

    if not news_articles and not trials:
        print("Nothing to send.")
        return

    if send_email(news_articles, trials):
        if news_articles:
            ids = ",".join(str(a["id"]) for a in news_articles)
            supa_patch("articles", f"id=in.({ids})", {"alert_sent": True})
            print(f"[OK] Marked {len(news_articles)} articles as sent")
        if trials:
            ncts = ",".join(f'"{t["nct_id"]}"' for t in trials)
            supa_patch("clinical_trials", f"nct_id=in.({ncts})", {"alert_sent": True})
            print(f"[OK] Marked {len(trials)} trials as sent")

if __name__ == "__main__":
    main()
