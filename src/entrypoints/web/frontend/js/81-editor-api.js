// ============================================================================
// גל 37: API פנימי לכל אזור בעורך-העל. הקוד בדפדפן הוא סקריפט אחד גלובלי (parts.txt), כך
// שכל קובץ יכול לקרוא לכל פונקציה של אזור אחר - וקשה לדעת מה "ציבורי". כאן מוגדר מה כל אזור
// מציע לאחרים; קוד חדש שעובר בין אזורים קורא דרך veApi (או אירועי uiBus), לא לפונקציות
// הפנימיות. השיוך של כל קובץ לאזור ב-web/frontend_areas.json, ו-tests/test_web_frontend_areas.py בודק
// שכל קובץ משויך ושכל פונקציה כאן קיימת. הפונקציות נקראות דרך עטיפה (ולא כהפניה) כי
// גלים מאוחרים מחליפים חלק מהן בעטיפות משלהם.
// ============================================================================

const veApi = Object.freeze({
  queue: Object.freeze({
    refresh: () => refreshVeQueue(),
    sort: (key) => sortVeQueue(key),
    tag: (color) => setVeQueueTag(color),
    stepFile: (delta) => stepVePreviewFile(delta),
    showOutput: (name) => showVeQueueOutput(name),
  }),
  timeline: Object.freeze({
    load: () => loadVeTimeline(),
    zoom: (zoom) => setVeTimelineZoom(zoom),
    moveCursor: (seconds) => _veMoveTimelineCursor(seconds),
    addMarker: () => addVeMarker(),
    redraw: () => _veRenderTimelineOverlays(),
  }),
  inspector: Object.freeze({
    revealField: (key) => veScrollToField(key),
    setMode: (mode) => setVeMode(mode),
    activateTab: (key) => _veActivateTab(key),
    refreshTools: () => _veRefreshInspectorTools(),
    openDocs: (key, term) => openVeFieldDocs(key, term),
  }),
  layers: Object.freeze({
    list: () => _veLayersValue(),
    write: (layers) => { _veWriteLayers(layers); _veRenderLayersEditor(true); },
    add: (kind) => addVeLayer(kind),
    align: (where) => alignVeLayer(where),
    distribute: () => distributeVeLayers(),
  }),
  library: Object.freeze({
    open: (tab) => openVeLibrary(tab),
    close: () => closeVeLibrary(),
  }),
  player: Object.freeze({
    fullscreen: () => toggleVeFullscreen(),
    lookAB: () => toggleVeLookAB(),
    guides: () => toggleVeGuides(),
  }),
  runs: Object.freeze({
    run: () => requestVeRun(),
    history: () => loadVeRuns(),
    hub: () => refreshVeRunsHub(),
    latestResults: () => openVeLatestResults(),
    schedule: () => openVeScheduleDialog(),
  }),
});
