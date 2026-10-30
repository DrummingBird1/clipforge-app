// --- חבילות פרסום של סרטוני נתונים (dataviz): תמונה, כותרת/SEO ואישור - בלי העלאה אוטומטית ---
const DATAVIZ_STATUS_LABELS = { pending_approval: "⏳ ממתין לאישור", approved: "✅ אושר", rejected: "❌ נדחה" };

function _datavizPackageUrl(pkg, suffix) {
  return `/api/dataviz/packages/${encodeURIComponent(pkg.orientation)}/${encodeURIComponent(pkg.name)}${suffix || ""}`;
}

async function loadDatavizPackages() {
  const list = document.getElementById("datavizPackagesList");
  if (!list) return;
  uiSkeleton(list, 2, "row");
  try {
    const res = await fetch("/api/dataviz/packages");
    const packages = await res.json();
    list.innerHTML = "";
    if (!packages.length) {
      list.innerHTML = '<div class="empty-msg">אין חבילות פרסום של סרטוני נתונים. הפעל publish בהגדרות הפרק, או הרץ עם --publish.</div>';
      return;
    }
    for (const pkg of packages) list.appendChild(_datavizCard(pkg));
  } catch (e) {
    list.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת חבילות הפרסום.</div>';
  }
}

function _datavizCard(pkg) {
  const card = document.createElement("div");
  card.className = "approval-card dataviz-card";
  card.dataset.packageId = pkg.id;
  card.dataset.status = pkg.status;

  if (pkg.has_thumbnail) {
    const img = document.createElement("img");
    img.src = _datavizPackageUrl(pkg, "/thumbnail");
    img.loading = "lazy";
    img.alt = pkg.title || pkg.name;
    img.onerror = () => { img.hidden = true; };
    card.appendChild(img);
  }

  const info = document.createElement("div");
  info.className = "approval-card-info";
  const name = document.createElement("div");
  name.className = "approval-card-name";
  name.textContent = pkg.youtube_title || pkg.title || pkg.name;
  const meta = document.createElement("div");
  meta.className = "approval-card-meta";
  meta.textContent = `${DATAVIZ_STATUS_LABELS[pkg.status] || pkg.status} · ${pkg.video} · ${pkg.created_at}`;
  info.appendChild(name);
  info.appendChild(meta);
  // גל 41: קישור לסרטון שהועלה, וזמן הפרסום המתוזמן
  const youtube = (pkg.sent_info || {}).youtube;
  if (youtube && youtube.video_id) {
    const line = document.createElement("div");
    line.className = "approval-card-meta";
    const link = document.createElement("a");
    link.href = `https://youtu.be/${encodeURIComponent(youtube.video_id)}`;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "▶ הסרטון ביוטיוב";
    line.appendChild(link);
    if (youtube.publish_at) line.append(" · " + "יפורסם ב-" + new Date(youtube.publish_at).toLocaleString("he-IL"));
    _dvzStatsLine(pkg, line);   // גל 44: צפיות, לייקים ותגובות
    info.appendChild(line);
  }
  const failed = Object.entries(pkg.steps || {}).filter(([, state]) => String(state).startsWith("failed"));
  if (failed.length) {
    const warn = document.createElement("div");
    warn.className = "approval-card-meta bad";
    warn.textContent = "⚠️ שלבים שנכשלו: " + failed.map(([step, state]) => `${step} (${state})`).join(", ");
    info.appendChild(warn);
  }
  if (!pkg.video_exists) {
    const missing = document.createElement("div");
    missing.className = "approval-card-meta bad";
    missing.textContent = "⚠️ קובץ הסרטון לא נמצא ליד החבילה";
    info.appendChild(missing);
  }
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "דף SEO";
  const sheet = document.createElement("div");
  sheet.className = "hint u-block dataviz-sheet";
  sheet.textContent = [pkg.tiktok_caption, pkg.youtube_title, pkg.description, (pkg.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  details.appendChild(summary);
  details.appendChild(sheet);
  info.appendChild(details);
  card.appendChild(info);

  if (pkg.status === "pending_approval") {
    const actions = document.createElement("div");
    actions.className = "approval-card-actions";
    const approveBtn = document.createElement("button");
    approveBtn.className = "approval-approve-btn";
    approveBtn.textContent = "✅ אשר";
    approveBtn.onclick = () => decideDatavizPackage(pkg, "approved", card);
    const rejectBtn = document.createElement("button");
    rejectBtn.className = "approval-reject-btn";
    rejectBtn.textContent = "❌ דחה";
    rejectBtn.onclick = () => decideDatavizPackage(pkg, "rejected", card);
    actions.appendChild(approveBtn);
    actions.appendChild(rejectBtn);
    card.appendChild(actions);
  }
  if (pkg.status === "approved" && pkg.video_exists) card.appendChild(_datavizSendActions(pkg));
  return card;
}

// שליחה של חבילה שאושרה: בדיקה יבשה (לא עושה כלום), העתקה לתיקיית Rocket Shorts, או העלאה פרטית ליוטיוב - רק אחרי אישור מפורש
function _datavizSendActions(pkg) {
  const wrap = document.createElement("div");
  wrap.className = "approval-card-actions dataviz-send";
  const sent = pkg.sent || [];
  const add = (target, label, title) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.sendTarget = target;
    btn.textContent = sent.includes(target) ? label + " ✓" : label;
    btn.title = title;
    btn.disabled = sent.includes(target);
    btn.onclick = () => sendDatavizPackage(pkg, target, btn.closest(".dataviz-card"));
    wrap.appendChild(btn);
  };
  add("dry_run", "בדיקה בלי שליחה", "מראה מה היה נשלח - לא משנה ולא שולח כלום");
  add("rocket", "העתק ל-Shorts", "מעתיק את הסרטון לתיקיית הקלט של Shorts (לא מוחק ולא דורס)");
  add("youtube", "העלה ל-YouTube (פרטי)", "מעלה כסרטון פרטי דרך החשבון שהוגדר");
  return wrap;
}

// נ10: הכרטיס שנלחץ - אותה חבילה מופיעה גם במסך האישורים וגם במסך עורך הגרפים, וחיפוש לפי data-package-id נעל את הכפתורים
// של הכרטיס הראשון בדף (לפעמים במסך השני), והכרטיס שנלחץ נשאר פתוח ללחיצה נוספת
async function sendDatavizPackage(pkg, target, card) {
  card = card || document.querySelector(`.dataviz-card[data-package-id="${CSS.escape(pkg.id)}"]`);
  const buttons = card ? [...card.querySelectorAll("button")] : [];
  if (target !== "dry_run") {
    const question = target === "rocket" ? "לשלוח את הסרטון לתיקיית הקלט של Shorts?" : "להעלות את הסרטון ל-YouTube כסרטון פרטי?";
    if (!(await veConfirm(question))) return;
  }
  for (const btn of buttons) btn.disabled = true;
  try {
    const resp = await fetch(_datavizPackageUrl(pkg, "/send"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target, confirm: target !== "dry_run" }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || "השליחה נכשלה");
    if (data.dry_run) {
      alert("בדיקה בלבד - לא נשלח כלום." + "\n" + data.plan.title + "\n" + data.plan.video);
    } else {
      uiToast(target === "rocket" ? "הסרטון הועתק ל-Shorts." : "ההעלאה ל-YouTube התחילה (פרטי).");
    }
    await loadDatavizPackages();
    dvzLoadPackages();
  } catch (e) {
    alert("שגיאה: " + e.message);
    for (const btn of buttons) btn.disabled = false;
  }
}

async function decideDatavizPackage(pkg, decision, card) {
  card = card || document.querySelector(`.dataviz-card[data-package-id="${CSS.escape(pkg.id)}"]`);
  const buttons = card ? [...card.querySelectorAll("button")] : [];
  for (const btn of buttons) btn.disabled = true;
  try {
    const resp = await fetch(_datavizPackageUrl(pkg, "/decide"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || "הפעולה נכשלה");
    await loadDatavizPackages();
    dvzLoadPackages();
  } catch (e) {
    alert("שגיאה: " + e.message);
    for (const btn of buttons) btn.disabled = false;
  }
}