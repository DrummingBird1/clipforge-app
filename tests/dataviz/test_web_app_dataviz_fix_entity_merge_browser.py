# tests/dataviz/test_web_app_dataviz_fix_entity_merge_browser.py
#
# 23.10.2026, ק4: ישות שמופיעה בשני מקורות שחופפים בזמן מוצגת כישות לכל מקור - ו"✅ לפני רינדור" אומר את זה, עם שם
# הישות ושני המקורות (עד היום שני הקווים פשוט חוברו לסכום, בלי שום סימן).
# xdist-group: workspace
import os

import pytest
import yaml

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    folder = data / "dataviz_episodes" / "shared"
    folder.mkdir(parents=True)
    workspace.mkdir()
    (folder / "a.csv").write_text("t,e,v\n2020-01-01,A,20\n2020-01-02,A,21\n2020-01-03,B,5\n", encoding="utf-8")
    (folder / "b.csv").write_text("t,e,v\n2020-01-02,A,30\n2020-01-03,A,31\n", encoding="utf-8")
    sources = [{"path": name, "time": {"column": "t"}, "value": {"column": "v"}, "entity": {"column": "e"}, "kind": "level"}
               for name in ("a.csv", "b.csv")]
    sources[1]["legend"] = "מדידה שנייה"
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "שני מקורות", "sources": sources}, f, allow_unicode=True, sort_keys=False)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return folder


def test_prerender_lists_an_entity_split_between_overlapping_sources(editor_page, screen):
    page = editor_page
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected === 'shared'")
    page.evaluate("() => dvzOpenPrerender()")
    row = page.wait_for_selector("#dvzPreData .dvz-finding.is-warn:has-text('מופיעה במקורות')", timeout=15000)   # קודם: אין שורה כזו
    text = row.inner_text()
    assert all(part in text for part in ('"A"', "a, מדידה שנייה", "A (a)", "A (מדידה שנייה)")), text
