async function loadGallery() {
  const res = await fetch("/api/clips");
  const clips = await res.json();
  _clipTagsByPath = {};
  await _populateGalleryTagFilterOptions();
  const list = document.getElementById("galleryList");
  list.innerHTML = "";
  if (!clips.length) {
    list.innerHTML = '<div class="empty-msg">אין עדיין קליפים ב-workspace/clips.</div>';
  } else {
    const grid = document.createElement("div");
    grid.className = "gallery-grid";
    for (const clip of clips) {
      const card = document.createElement("div");
      card.className = "gallery-card";
      card.dataset.path = clip.path;
      card.dataset.name = clip.name.toLowerCase();
      // loading="lazy" - גלריה עם עשרות קליפים לא אמורה לבקש עשרות thumbnails
      // בבת אחת; הדפדפן טוען רק את מה שבפועל בתוך/קרוב לאזור הנראה.
      const img = document.createElement("img");
      img.src = "/api/clips/thumbnail?path=" + encodeURIComponent(clip.path);
      img.loading = "lazy";
      img.alt = clip.name;
      // קליפ ש-ffmpeg נכשל לחלץ ממנו פריים (קובץ פגום וכו') - לא משאיר <img> שבור,
      // רק מסתיר אותה; השם עדיין מוצג ואפשר עדיין לבחור את הכרטיס.
      img.onerror = () => { img.style.display = "none"; };
      const name = document.createElement("div");
      name.className = "gallery-card-name";
      name.textContent = clip.name;
      const tagsBox = document.createElement("div");
      tagsBox.className = "gallery-card-tags";
      const friendTagsBox = document.createElement("div");
      friendTagsBox.className = "gallery-card-friend-tags";
      card.appendChild(img);
      card.appendChild(name);
      card.appendChild(tagsBox);
      card.appendChild(friendTagsBox);
      card.onclick = () => selectClip(clip, card);
      grid.appendChild(card);
      loadClipTags(clip, tagsBox);
      loadClipFriendTags(clip, friendTagsBox);
    }
    list.appendChild(grid);
  }
  filterGallery();
  await refreshYoutubeButtonState();
}

async function _populateGalleryTagFilterOptions() {
  // ה-dropdown ממולא ממטמון קיים בלבד (לעולם לא קורא ל-AI) - ראו
  // /api/clips/all_tags. שומר על הבחירה הנוכחית אם היא עדיין קיימת ברשימה
  // המחודשת, כדי שרענון גלריה לא יאפס סינון פעיל בלי סיבה.
  const select = document.getElementById("galleryFilterTag");
  const previousValue = select.value;
  const res = await fetch("/api/clips/all_tags");
  const data = await res.json();
  select.innerHTML = '<option value="">🏷️ כל התגיות</option>';
  for (const tag of data.tags) {
    const opt = document.createElement("option");
    opt.value = tag;
    opt.textContent = tag;
    select.appendChild(opt);
  }
  if (data.tags.includes(previousValue)) select.value = previousValue;
}

async function loadClipTags(clip, tagsBox) {
  // רק קורא מטמון קיים (זול) - קריאת AI אמיתית קורית רק בלחיצה מפורשת על
  // כפתור "🏷️ תייג" (item: content-based auto-tagging), לא אוטומטית כאן.
  const res = await fetch("/api/clips/tags?path=" + encodeURIComponent(clip.path));
  const data = await res.json();
  _clipTagsByPath[clip.path] = data.tags || [];
  _renderClipTags(tagsBox, clip, data.tags);
  filterGallery();
}

async function loadClipFriendTags(clip, friendTagsBox) {
  // item: friend detection via Discord voice channel presence - נכתב על-ידי
  // cogs/approval_cog.py (תהליך הבוט) בזמן סריקה; כאן רק קורא את המטמון,
  // בלי שום פעולה יזומה מהמשתמש (בניגוד לתיוג-AI, שדורש לחיצה מפורשת).
  const res = await fetch("/api/clips/friend_tags?path=" + encodeURIComponent(clip.path));
  const data = await res.json();
  friendTagsBox.innerHTML = "";
  if (!data.friends || !data.friends.length) return;
  const label = document.createElement("span");
  label.className = "gallery-friend-badge";
  label.textContent = "👥 " + data.friends.join(", ");
  friendTagsBox.appendChild(label);
}

function filterGallery() {
  const nameQuery = (document.getElementById("galleryFilterName").value || "").trim().toLowerCase();
  const tagFilter = document.getElementById("galleryFilterTag").value;
  const cards = document.querySelectorAll("#galleryList .gallery-card");
  let visibleCount = 0;
  for (const card of cards) {
    const nameMatches = !nameQuery || card.dataset.name.includes(nameQuery);
    const tags = _clipTagsByPath[card.dataset.path] || [];
    const tagMatches = !tagFilter || tags.includes(tagFilter);
    const visible = nameMatches && tagMatches;
    card.style.display = visible ? "" : "none";
    if (visible) visibleCount++;
  }
  const hint = document.getElementById("galleryFilterHint");
  if ((nameQuery || tagFilter) && cards.length) {
    hint.style.display = "block";
    hint.textContent = `מציג ${visibleCount} מתוך ${cards.length} קליפים`;
  } else {
    hint.style.display = "none";
  }
}

function _renderClipTags(tagsBox, clip, tags) {
  tagsBox.innerHTML = "";
  if (tags === null) {
    const btn = document.createElement("button");
    btn.className = "gallery-tag-btn";
    btn.textContent = "🏷️ תייג";
    btn.onclick = (e) => { e.stopPropagation(); generateClipTags(clip, tagsBox, btn); };
    tagsBox.appendChild(btn);
    return;
  }
  if (!tags.length) {
    tagsBox.textContent = "";
    return;
  }
  for (const tag of tags) {
    const badge = document.createElement("span");
    badge.className = "gallery-tag-badge";
    badge.textContent = tag;
    tagsBox.appendChild(badge);
  }
}

async function generateClipTags(clip, tagsBox, btn) {
  btn.disabled = true;
  btn.textContent = "⏳ מתייג...";
  try {
    const res = await fetch("/api/clips/generate_tags", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: clip.path }),
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      btn.disabled = false;
      btn.textContent = "🏷️ תייג";
    } else {
      _renderClipTags(tagsBox, clip, data.tags);
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "🏷️ תייג";
  }
}

function selectClip(clip, cardEl) {
  _selectedClipPath = clip.path;
  document.getElementById("galleryStatus").textContent = "נבחר: " + clip.name;
  document.getElementById("galleryTiktokBtn").disabled = false;
  document.getElementById("galleryYoutubeBtn").disabled = false;
  const preview = document.getElementById("galleryPreview");
  preview.src = "/api/clips/stream?path=" + encodeURIComponent(clip.path);
  preview.hidden = false;
  for (const el of document.querySelectorAll(".gallery-card.selected")) el.classList.remove("selected");
  if (cardEl) cardEl.classList.add("selected");
}

async function refreshYoutubeButtonState() {
  try {
    const res = await fetch("/api/clips/youtube_status");
    const data = await res.json();
    document.getElementById("galleryYoutubeHint").textContent = data.configured
      ? "🔗 העלאה אוטומטית פעילה"
      : "🔗 פותח דפדפן (הגדר client_secret.json להעלאה אוטומטית)";
  } catch (e) {
    // רמז מידע-בלבד - כשל רשת פשוט לא מציג אותו, בלי alert.
  }
}

async function exportToTiktok() {
  if (!_selectedClipPath) return;
  try {
    const resp = await fetch("/api/clips/tiktok_export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: _selectedClipPath }) });
    if (!resp.ok) throw new Error((await resp.json()).error || "הפעולה נכשלה");
    const data = await resp.json();
    // גל 32: הכיתוב (מ-Gemini כשיש מפתח) מוכן להדבקה - מעתיקים לפני שהטאב החדש לוקח את הפוקוס
    if (data.caption) {
      try {
        await navigator.clipboard.writeText(data.caption);
        uiToast(data.seo_source === "ai" ? "🤖 הכיתוב מ-Gemini הועתק - הדבק אותו ב-TikTok" : "📋 הכיתוב הועתק - הדבק אותו ב-TikTok", "ok");
      } catch (e) {
        uiToast(data.caption, "", { timeout: 20000 });
      }
    }
    window.open(data.tiktok_url, "_blank");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

async function exportToYoutube() {
  if (!_selectedClipPath) return;
  const btn = document.getElementById("galleryYoutubeBtn");
  try {
    const resp = await fetch("/api/clips/youtube_export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: _selectedClipPath }) });
    if (!resp.ok) throw new Error((await resp.json()).error || "הפעולה נכשלה");
    const data = await resp.json();
    if (!data.configured) {
      window.open(data.fallback_url, "_blank");
      return;
    }
    btn.disabled = true;
    _pollYoutubeUploadStatus();
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

function _pollYoutubeUploadStatus() {
  const btn = document.getElementById("galleryYoutubeBtn");
  if (_youtubeStatusPoll) clearInterval(_youtubeStatusPoll);
  _youtubeStatusPoll = setInterval(async () => {
    const res = await fetch("/api/clips/youtube_status");
    const data = await res.json();
    if (data.in_progress) {
      btn.textContent = `⏳ מעלה... ${data.percent}%`;
      return;
    }
    clearInterval(_youtubeStatusPoll);
    _youtubeStatusPoll = null;
    btn.disabled = false;
    btn.textContent = "📺 YouTube Export Pro";
    if (data.success) {
      document.getElementById("galleryStatus").textContent = `✅ הועלה ל-YouTube! ID: ${data.video_id}`;
    } else if (data.success === false) {
      document.getElementById("galleryStatus").textContent = `❌ העלאה נכשלה: ${data.error}`;
    }
  }, 1000);
}

// --- אישור קליפים (item: mobile-friendly clip-approval view) ---
async function loadApprovals() {
  const list = document.getElementById("approvalsList");
  uiSkeleton(list, 4, "row");
  try {
    const res = await fetch("/api/approvals");
    const clips = await res.json();
    list.innerHTML = "";
    if (!clips.length) {
      list.innerHTML = '<div class="empty-msg">אין קליפים שממתינים לאישור כרגע.</div>';
      return;
    }
    for (const clip of clips) {
      const card = document.createElement("div");
      card.className = "approval-card";
      card.id = "approvalCard" + clip.id;

      const img = document.createElement("img");
      img.src = "/api/clips/thumbnail?path=" + encodeURIComponent(clip.path);
      img.loading = "lazy";
      img.alt = clip.name;
      img.onerror = () => { img.style.display = "none"; };

      const info = document.createElement("div");
      info.className = "approval-card-info";
      const name = document.createElement("div");
      name.className = "approval-card-name";
      name.textContent = clip.name;
      const meta = document.createElement("div");
      meta.className = "approval-card-meta";
      meta.textContent = `🎮 ${clip.game} · ${clip.created_at}`;
      info.appendChild(name);
      info.appendChild(meta);

      const actions = document.createElement("div");
      actions.className = "approval-card-actions";
      const approveBtn = document.createElement("button");
      approveBtn.className = "approval-approve-btn";
      approveBtn.textContent = "✅ אשר לרינדור";
      approveBtn.onclick = () => decideApproval(clip.id, true);
      const rejectBtn = document.createElement("button");
      rejectBtn.className = "approval-reject-btn";
      rejectBtn.textContent = "❌ דחה";
      rejectBtn.onclick = () => decideApproval(clip.id, false);
      actions.appendChild(approveBtn);
      actions.appendChild(rejectBtn);

      card.appendChild(img);
      card.appendChild(info);
      card.appendChild(actions);
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת קליפים לאישור.</div>';
  }
}

async function decideApproval(pendingId, approved) {
  const card = document.getElementById("approvalCard" + pendingId);
  for (const btn of card.querySelectorAll("button")) btn.disabled = true;
  try {
    const resp = await fetch(`/api/approvals/${pendingId}/decide`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || "הפעולה נכשלה");
    card.remove();
  } catch (e) {
    alert("שגיאה: " + e.message);
    for (const btn of card.querySelectorAll("button")) btn.disabled = false;
  }
}

// --- אנליטיקס YouTube (item: YouTube Analytics feedback loop) ---
async function loadYoutubeAnalytics() {
  const list = document.getElementById("youtubeAnalyticsList");
  uiSkeleton(list, 4, "row");
  try {
    const res = await fetch("/api/youtube_analytics");
    const rows = await res.json();
    if (!rows.length) {
      list.innerHTML = '<div class="empty-msg">עוד לא הועלו סרטונים דרך "📺 YouTube Export Pro".</div>';
      return;
    }
    list.innerHTML = "";
    for (const row of rows) {
      const card = document.createElement("div");
      card.className = "yt-analytics-card";

      const topRow = document.createElement("div");
      topRow.className = "stats-row";
      const nameSpan = document.createElement("span");
      nameSpan.className = "script";
      nameSpan.textContent = row.title || row.clip_filename;
      const metaSpan = document.createElement("span");
      metaSpan.className = "meta";
      let metaText = row.views === null ? "עוד לא רוענן" : `👁 ${row.views} · 👍 ${row.likes} · 💬 ${row.comments}`;
      if (row.thumbnail_switch && row.thumbnail_switch.views_gained_since_switch !== null) {
        metaText += ` · 🖼️ +${row.thumbnail_switch.views_gained_since_switch} מאז ההחלפה`;
      }
      metaSpan.textContent = metaText;
      topRow.appendChild(nameSpan);
      topRow.appendChild(metaSpan);

      const candidatesBox = document.createElement("div");
      candidatesBox.className = "yt-thumb-candidates";
      candidatesBox.hidden = true;

      const thumbBtn = document.createElement("button");
      thumbBtn.className = "yt-thumb-toggle-btn";
      thumbBtn.textContent = "🖼️ תמונות ממוזערות";
      thumbBtn.onclick = () => toggleThumbnailCandidates(row.video_id, candidatesBox);

      card.appendChild(topRow);
      card.appendChild(thumbBtn);
      card.appendChild(candidatesBox);
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת נתוני אנליטיקס.</div>';
  }
}

// --- A/B thumbnail testing (item: A/B thumbnail testing) ---
async function toggleThumbnailCandidates(videoId, box) {
  if (!box.hidden) { box.hidden = true; return; }
  box.hidden = false;
  uiSkeleton(box, 3, "card");
  try {
    const res = await fetch(`/api/youtube_analytics/${videoId}/thumbnail_candidates`);
    const candidates = await res.json();
    if (!candidates.length) {
      box.innerHTML = '<div class="hint" style="display:block">אין תמונות מועמדות לסרטון הזה (רק סרטונים שהועלו לאחר תוספת התכונה).</div>';
      return;
    }
    box.innerHTML = "";
    for (const c of candidates) {
      const wrap = document.createElement("div");
      wrap.className = "yt-thumb-candidate";
      const img = document.createElement("img");
      img.src = `/api/youtube_analytics/${videoId}/thumbnail_candidates/${c.index}/image`;
      img.loading = "lazy";
      const btn = document.createElement("button");
      btn.textContent = "✅ הגדר כתמונה ראשית";
      btn.onclick = () => setVideoThumbnail(videoId, c.index, btn);
      wrap.appendChild(img);
      wrap.appendChild(btn);
      box.appendChild(wrap);
    }
  } catch (e) {
    box.innerHTML = '<div class="empty-msg bad">שגיאה בטעינת תמונות מועמדות.</div>';
  }
}

async function setVideoThumbnail(videoId, candidateIndex, btn) {
  btn.disabled = true;
  btn.textContent = "⏳ מגדיר...";
  try {
    const resp = await fetch(`/api/youtube_analytics/${videoId}/set_thumbnail`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ candidate_index: candidateIndex }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || "הפעולה נכשלה");
    await loadYoutubeAnalytics();
  } catch (e) {
    alert("שגיאה: " + e.message);
    btn.disabled = false;
    btn.textContent = "✅ הגדר כתמונה ראשית";
  }
}

async function refreshYoutubeAnalytics() {
  const btn = document.getElementById("youtubeAnalyticsRefreshBtn");
  btn.disabled = true;
  btn.textContent = "⏳ מרענן...";
  try {
    const resp = await fetch("/api/youtube_analytics/refresh", { method: "POST" });
    if (!resp.ok) throw new Error((await resp.json()).error || "הרענון נכשל");
    _pollYoutubeAnalyticsRefreshStatus();
  } catch (e) {
    alert("שגיאה: " + e.message);
    btn.disabled = false;
    btn.textContent = "🔄 רענן";
  }
}

function _pollYoutubeAnalyticsRefreshStatus() {
  const btn = document.getElementById("youtubeAnalyticsRefreshBtn");
  const poll = setInterval(async () => {
    const res = await fetch("/api/youtube_analytics/refresh_status");
    const data = await res.json();
    if (data.in_progress) return;
    clearInterval(poll);
    btn.disabled = false;
    btn.textContent = "🔄 רענן";
    await loadYoutubeAnalytics();
    if (data.errors && data.errors.length) {
      alert(`רוענן בהצלחה (${data.updated}), אבל עם ${data.errors.length} שגיאות - ראה קונסולת הדפדפן.`);
      console.error(data.errors);
    }
  }, 1000);
}

async function loadWaveform(path, filename) {
  document.getElementById("waveformSection").hidden = false;
  document.getElementById("waveformFileName").textContent = "🌊 " + filename;
  const canvas = document.getElementById("waveformCanvas");
  const statusEl = document.getElementById("waveformStatus");
  canvas.hidden = true;
  statusEl.textContent = "טוען נתוני שמע...";
  try {
    const res = await fetch("/api/waveform?path=" + encodeURIComponent(path));
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const midY = canvas.height / 2;
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#4ade80";
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1;
    const maxPeak = data.max_peak || 1;
    data.peaks.slice(0, canvas.width).forEach((peak, x) => {
      const h = (peak / maxPeak) * (canvas.height / 2 - 5);
      ctx.beginPath();
      ctx.moveTo(x, midY - h);
      ctx.lineTo(x, midY + h);
      ctx.stroke();
    });
    canvas.hidden = false;
    statusEl.textContent = "📁 " + filename;
  } catch (e) {
    statusEl.textContent = "שגיאה בטעינת השמע: " + e.message;
  }
}

async function saveRocketSettings() {
  const payload = {
    input_dir: document.getElementById("rsInputDir").value,
    output_dir: document.getElementById("rsOutputDir").value,
    watermark_image_path: document.getElementById("rsOverlayPath").value,
    preset: document.getElementById("rsPreset").value,
    counter: parseInt(document.getElementById("rsCounter").value || "1", 10),
    title_prefix: document.getElementById("rsTitlePrefix").value,
    game_name: document.getElementById("rsGameName").value,
    output_resolution: document.getElementById("rsOutputResolution").value,
    enable_weekly_recap: document.getElementById("rsRecapEnabled").checked,
    weekly_recap_period: document.getElementById("rsRecapPeriod").value,
    weekly_recap_day: parseInt(document.getElementById("rsRecapDay").value, 10),
    enable_captions: document.getElementById("rsCaptionsEnabled").checked,
    enable_captions_translate: document.getElementById("rsCaptionsTranslateEnabled").checked,
    clip_hotkey: document.getElementById("rsClipHotkey").value,
    capture_voice_channel_id: document.getElementById("rsCaptureVoiceChannelId").value,
    capture_watch_dir: document.getElementById("rsCaptureWatchDir").value,
    max_concurrent_renders: parseInt(document.getElementById("rsMaxConcurrentRenders").value || "1", 10),
    auto_chain: document.getElementById("rsAutoChain").value,
    auto_chain_profile: document.getElementById("rsAutoChainProfile").value,
    auto_chain_dry_run: document.getElementById("rsAutoChainDryRun").checked,
    seo_ai: document.getElementById("rsSeoAi").checked,
  };
  if (payload.auto_chain.startsWith("edit") && !payload.auto_chain_profile) {
    alert("בחר סגנון לעריכה האוטומטית (או \"רק להעתיק ל-Import\").");
    return;
  }
  try {
    const resp = await fetch("/api/rocket_settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!resp.ok) throw new Error((await resp.json()).error || "שמירה נכשלה");
    alert("הגדרות Shorts נשמרו.");
  } catch (e) {
    alert("שגיאה: " + e.message);
  }
}

