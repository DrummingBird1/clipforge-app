// 34-notification-center.js - מרכז ההתראות (23.10.2026): הרשימה (GET /api/notifications, utils/shared/notification_log.py).
// נטען בלחיצה על 📥 (toggleNotificationCenter ב-20-app-shell.js, וה-HTML ב-lazy-html:notifications). פתיחה מסמנת "נקרא" עד
// ההתראה האחרונה שהוצגה, ולחיצה על התראה עוברת למסך שלה.
function toggleNotificationPanel(open) {
  const panel = document.getElementById("notifCenter");
  const btn = document.getElementById("notifCenterBtn");
  const show = open === undefined ? panel.hidden : !!open;
  panel.hidden = !show;
  btn.setAttribute("aria-expanded", String(show));
  if (show) {
    // מתחת לכפתור, כמו תפריט ההעדפות (במובייל שורת הכפתורים נשברת לשורה שנייה)
    panel.style.setProperty("--prefs-top", `${Math.round(btn.getBoundingClientRect().bottom + 6)}px`);
    loadNotifications();
  }
}

async function loadNotifications() {
  const list = document.getElementById("notifList");
  try {
    const res = await fetch("/api/notifications");
    if (!res.ok) throw new Error("טעינת ההתראות נכשלה");
    const data = await res.json();
    _renderNotifications(list, data.items);
    if (data.items.length && data.unread) {
      await fetch("/api/notifications/read", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({up_to: data.items[0].id})});
      refreshNotificationBadge();
    }
  } catch (e) {
    _notificationsMessage(list, e.message);
  }
}

function _notificationsMessage(list, text) {
  const message = document.createElement("div");
  message.className = "empty-msg";
  message.textContent = text;
  list.replaceChildren(message);
}

function _renderNotifications(list, items) {
  if (!items.length) {
    _notificationsMessage(list, "אין התראות. ריצה שתסתיים, תיעצר או תיכשל תופיע כאן.");
    return;
  }
  list.replaceChildren(...items.map((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "notif-item notif-" + item.level;
    row.classList.toggle("unread", !item.read);
    const title = document.createElement("span");
    title.className = "notif-title";
    title.textContent = item.title;
    const meta = document.createElement("span");
    meta.className = "notif-meta hint";
    meta.textContent = [item.body, uiRelativeTime(new Date(item.created_at * 1000))].filter(Boolean).join(" · ");
    row.append(title, meta);
    row.onclick = () => openNotificationTarget(item.target);
    return row;
  }));
}

function openNotificationTarget(target) {
  toggleNotificationPanel(false);
  if (target && document.querySelector(`[data-tab-panel="${CSS.escape(target)}"]`)) switchTab(target);
  else openScripts();   // הלוג של הריצה, וגם יעד שאין לו מסך בגרסה הזו
}

document.addEventListener("click", (event) => {
  const panel = document.getElementById("notifCenter");
  if (!panel || panel.hidden || event.target.closest("#notifCenter, #notifCenterBtn")) return;
  toggleNotificationPanel(false);
});

document.addEventListener("keydown", (event) => {
  const panel = document.getElementById("notifCenter");
  if (event.key !== "Escape" || !panel || panel.hidden) return;
  toggleNotificationPanel(false);
  document.getElementById("notifCenterBtn").focus();
});
