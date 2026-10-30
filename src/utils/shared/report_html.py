# utils/shared/report_html.py
#
# עמוד HTML קליל אחד לסיכום סריקת דיסק (disk_scanner.py) - להבדיל מ-
# report_excel.py (גיליונות מלאים לעיון/מיון), זה מיועד לשיתוף/הצצה מהירה:
# פותח בכל דפדפן, בלי Excel, ובלי לפרט כל שורה (רשימות חתוכות ל-Top N,
# עם הפניה ל-JSON/Excel לרשימה המלאה) כדי שהקובץ יישאר קטן ומהיר לפתוח.
import html
import os

MAX_DUPLICATE_GROUPS_SHOWN = 20
MAX_JUNK_FILES_SHOWN = 50

_STYLE = """
body { background:#0c0c0e; color:#e6e6ea; font-family: 'Segoe UI', Arial, sans-serif; direction: rtl; padding: 24px; }
h1 { color:#00e676; }
.summary { display:flex; flex-wrap:wrap; gap:16px; margin: 20px 0; }
.card { background:#141418; border:1px solid #22222b; border-radius:10px; padding:14px 20px; min-width:160px; }
.card .value { font-size:22px; font-weight:bold; color:#00e676; }
.card .label { color:#8e8e9a; font-size:12px; }
table { width:100%; border-collapse: collapse; margin: 12px 0 28px; }
th, td { text-align:right; padding:6px 10px; border-bottom:1px solid #22222b; font-size:13px; }
th { color:#8e8e9a; font-weight:normal; }
.note { color:#8e8e9a; font-size:12px; margin-top: -18px; margin-bottom: 24px; }
"""


def _fmt_gb(num_bytes):
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def _esc(value):
    return html.escape(str(value))


def write_html_report(report, output_path):
    total_files = report.get("total_files_scanned", 0)
    total_size = report.get("total_size_bytes", 0)
    duplicate_groups = report.get("duplicates", [])
    junk_files = report.get("junk_files", [])
    media_count = report.get("media_files_analyzed", 0)
    wasted_bytes = report.get("duplicate_wasted_bytes", 0)

    duplicate_rows = "".join(
        f"<tr><td>{_esc(g.get('count', 0))}</td><td>{_esc(_fmt_gb(g.get('size_bytes', 0)))}</td>"
        f"<td>{_esc(g['files'][0]) if g.get('files') else ''}</td></tr>"
        for g in duplicate_groups[:MAX_DUPLICATE_GROUPS_SHOWN]
    )
    junk_rows = "".join(
        f"<tr><td>{_esc(_fmt_gb(j.get('size_bytes', 0)))}</td><td>{_esc(j.get('reason', ''))}</td><td>{_esc(j.get('path', ''))}</td></tr>"
        for j in junk_files[:MAX_JUNK_FILES_SHOWN]
    )

    more_dup_note = (
        f"<p class='note'>ועוד {len(duplicate_groups) - MAX_DUPLICATE_GROUPS_SHOWN} קבוצות - הרשימה המלאה ב-report.json/report.xlsx.</p>"
        if len(duplicate_groups) > MAX_DUPLICATE_GROUPS_SHOWN else ""
    )
    more_junk_note = (
        f"<p class='note'>ועוד {len(junk_files) - MAX_JUNK_FILES_SHOWN} קבצים - הרשימה המלאה ב-report.json/report.xlsx.</p>"
        if len(junk_files) > MAX_JUNK_FILES_SHOWN else ""
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>סיכום סריקת דיסק</title><style>{_STYLE}</style></head>
<body>
<h1>💽 סיכום סריקת דיסק</h1>
<p class="note">{_esc(report.get('target_directory', ''))} - נסרק ב-{_esc(report.get('scan_finished_at', ''))}</p>

<div class="summary">
  <div class="card"><div class="value">{total_files:,}</div><div class="label">קבצים נסרקו</div></div>
  <div class="card"><div class="value">{_fmt_gb(total_size)}</div><div class="label">נפח כולל</div></div>
  <div class="card"><div class="value">{len(duplicate_groups)}</div><div class="label">קבוצות כפילויות</div></div>
  <div class="card"><div class="value">{_fmt_gb(wasted_bytes)}</div><div class="label">ניתן לשחרר</div></div>
  <div class="card"><div class="value">{len(junk_files)}</div><div class="label">קבצי זבל</div></div>
  <div class="card"><div class="value">{media_count}</div><div class="label">קבצי מדיה נותחו</div></div>
</div>

<h2>🔁 קבוצות כפילויות (הכי כבדות)</h2>
<table><tr><th>עותקים</th><th>גודל</th><th>דוגמת נתיב</th></tr>{duplicate_rows}</table>
{more_dup_note}

<h2>🗑️ קבצי זבל</h2>
<table><tr><th>גודל</th><th>סיבה</th><th>נתיב</th></tr>{junk_rows}</table>
{more_junk_note}
</body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
