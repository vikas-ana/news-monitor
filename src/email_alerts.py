#!/usr/bin/env python3
"""
Email alerts sender for news-monitor.
Queries Supabase for unsent alerts (is_alert=true, alert_sent=false).
Sends digest email via Gmail SMTP.
Marks articles as alert_sent=true after sending.
"""

import os
import json
import subprocess
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GMAIL_USER   = os.environ["GMAIL_USER"]    # your Gmail address
GMAIL_PASS   = os.environ["GMAIL_APP_PASS"]  # Gmail App Password (16-char)
ALERT_TO     = os.environ.get("ALERT_EMAIL", GMAIL_USER)  # recipient

CATEGORY_EMOJI = {
    "clinical":    "🔬",
    "regulatory":  "📋",
    "commercial":  "💼",
}

SCORE_LABEL = {
    10: "🚨 CRITICAL",
    9:  "🔴 HIGH",
    8:  "🟠 HIGH",
    7:  "🟡 MEDIUM",
    6:  "🟢 NOTABLE",
}

def supabase_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    result = subprocess.run([
        "curl", "-s",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json",
        url
    ], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[ERROR] Parse error: {e}")
        return []

def supabase_patch(table, filter_params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filter_params}"
    payload = json.dumps(data)
    result = subprocess.run([
        "curl", "-s", "-X", "PATCH",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: return=minimal",
        url, "-d", payload
    ], capture_output=True, text=True, timeout=30)
    return result.returncode == 0

def build_html(articles):
    today = datetime.utcnow().strftime("%B %d, %Y")
    rows_html = ""
    for a in articles:
        score      = a.get("relevance_score") or 0
        cat        = a.get("category") or "unknown"
        emoji      = CATEGORY_EMOJI.get(cat, "📰")
        label      = SCORE_LABEL.get(score, f"Score {score}")
        title      = a.get("catchy_title") or a.get("raw_title") or "No title"
        summary    = a.get("summary") or ""
        alert_text = a.get("alert_text") or ""
        drug       = a.get("product_name") or ""
        company    = a.get("company") or ""
        indication = a.get("indication") or ""
        url        = a.get("url") or "#"
        date_str   = a.get("article_date") or ""

        meta_parts = [p for p in [drug, company, indication, date_str] if p]
        meta = " · ".join(meta_parts)

        rows_html += f"""
        <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;
                    padding:20px;margin-bottom:20px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <span style="font-size:18px;">{emoji}</span>
            <span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;
                         font-size:12px;font-weight:600;color:#444;">{label}</span>
            <span style="background:#e8f4fd;border-radius:4px;padding:2px 8px;
                         font-size:12px;color:#1a73e8;text-transform:uppercase;">{cat}</span>
          </div>
          <h3 style="margin:0 0 6px 0;font-size:16px;color:#1a1a1a;">
            <a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a>
          </h3>
          <p style="margin:0 0 10px 0;font-size:12px;color:#888;">{meta}</p>
          <p style="margin:0 0 12px 0;font-size:14px;color:#333;line-height:1.5;">{summary}</p>
          {"<div style='background:#fff8e1;border-left:4px solid #ffc107;padding:10px 14px;border-radius:0 4px 4px 0;font-size:13px;color:#333;'><strong>⚠️ Alert:</strong> " + alert_text + "</div>" if alert_text else ""}
        </div>
        """

    return f"""
    <!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f5;
    margin:0;padding:20px;">
      <div style="max-width:700px;margin:0 auto;">
        <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);
                    border-radius:8px 8px 0 0;padding:24px;color:#fff;">
          <h1 style="margin:0;font-size:22px;">💊 Pharma News Monitor</h1>
          <p style="margin:6px 0 0 0;opacity:0.85;font-size:14px;">
            {len(articles)} alert{"s" if len(articles)!=1 else ""} · {today}
          </p>
        </div>
        <div style="background:#f5f5f5;padding:20px;">
          {rows_html}
        </div>
        <div style="text-align:center;padding:16px;font-size:12px;color:#999;">
          Pharma News Monitor · Automated alerts for RA, Psoriasis, Crohn's, UC
        </div>
      </div>
    </body></html>
    """

def build_plain(articles):
    today = datetime.utcnow().strftime("%B %d, %Y")
    lines = [f"PHARMA NEWS MONITOR — {len(articles)} Alert(s) — {today}", "="*60]
    for i, a in enumerate(articles, 1):
        score   = a.get("relevance_score") or 0
        cat     = a.get("category") or "unknown"
        title   = a.get("catchy_title") or a.get("raw_title") or "No title"
        summary = a.get("summary") or ""
        alert   = a.get("alert_text") or ""
        url     = a.get("url") or ""
        drug    = a.get("product_name") or ""
        company = a.get("company") or ""
        lines += [
            f"\n[{i}] Score {score}/10 | {cat.upper()} | {drug} ({company})",
            f"    {title}",
            f"    {summary}",
        ]
        if alert:
            lines.append(f"    >> ALERT: {alert}")
        if url:
            lines.append(f"    {url}")
    return "\n".join(lines)

def send_email(articles):
    subject = f"[Pharma Alert] {len(articles)} new alert{'s' if len(articles)!=1 else ''} — {datetime.utcnow().strftime('%b %d')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Pharma News Monitor <{GMAIL_USER}>"
    msg["To"]      = ALERT_TO
    msg.attach(MIMEText(build_plain(articles), "plain"))
    msg.attach(MIMEText(build_html(articles),  "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, ALERT_TO, msg.as_string())
    print(f"[OK] Email sent to {ALERT_TO}: {subject}")

def main():
    print("=== Email Alerts Sender ===")
    articles = supabase_get("articles",
        "select=id,catchy_title,raw_title,product_name,company,indication,"
        "category,relevance_score,summary,alert_text,article_date,url"
        "&is_alert=eq.true&alert_sent=eq.false&order=relevance_score.desc")

    if not isinstance(articles, list):
        print(f"[ERROR] Supabase error: {articles}")
        sys.exit(1)

    print(f"Found {len(articles)} unsent alerts")
    if not articles:
        print("Nothing to send. Exiting.")
        return

    # Sort: highest score first
    articles.sort(key=lambda x: x.get("relevance_score") or 0, reverse=True)

    send_email(articles)

    # Mark as sent
    ids = [str(a["id"]) for a in articles]
    id_list = ",".join(ids)
    ok = supabase_patch("articles", f"id=in.({id_list})", {"alert_sent": True})
    if ok:
        print(f"[OK] Marked {len(ids)} articles as alert_sent=true")
    else:
        print("[WARN] Failed to mark articles as sent — will resend next run")

if __name__ == "__main__":
    main()
