# tests/web/test_web_app_scripts_catalog_browser.py
#
# Scripts catalog in the web sidebar: collapsible categories with counts (video, stream, tools, steam order), search,
# favorites / archive kept in this browser's localStorage (no server write), and archived scripts listed in the archive tab.
# Set SHOT_DIR to also save real-Edge screenshots.
import os


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def catalog_page(editor_server, edge_browser):
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
    page = context.new_page()
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/api/scripts/favorite" in r.url else None)
    page.favorite_posts = posts
    try:
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
        page.evaluate("() => { localStorage.removeItem('clipforgeFavScripts'); localStorage.removeItem('clipforgeArchivedScripts'); localStorage.removeItem('clipforgeCollapsedCategories'); state.showAllCategories = true; renderScripts(); }")
    except Exception:
        context.close()
        raise
    yield page
    context.close()


def _shot(page, name):
    folder = os.environ.get("SHOT_DIR")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, name))


def _reload(page):
    page.reload()
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)


def _first_visible(page):
    return page.evaluate("() => state.scripts.filter(s => !s.archived)[0]")


def _row(page, script):
    return page.locator("#scriptList .script-row", has=page.locator(".script-btn", has_text=script["name"])).first


def test_scripts_are_grouped_by_category_in_the_fixed_order_with_counts(catalog_page):
    page = catalog_page
    keys = page.evaluate("() => [...document.querySelectorAll('#scriptList .category-toggle')].map(e => e.dataset.category)")
    assert keys and len(keys) == len(set(keys))
    order = ["video", "stream", "tools", "steam"]
    ranks = [order.index(k) if k in order else len(order) for k in keys]
    assert ranks == sorted(ranks)
    first = page.locator("#scriptList .category-toggle").first.inner_text()
    assert "(" in first and first.rstrip().endswith(")")
    assert page.locator("#scriptList .category-toggle").first.get_attribute("aria-expanded") == "true"
    _shot(page, "1_catalog_grouped.png")


def test_category_collapse_is_remembered_in_the_browser(catalog_page):
    page = catalog_page
    head = page.locator("#scriptList .category-toggle").first
    key = head.get_attribute("data-category")
    rows_before = page.locator("#scriptList .script-row").count()
    head.click()
    assert page.locator(f'#scriptList .category-toggle[data-category="{key}"]').get_attribute("aria-expanded") == "false"
    assert page.locator("#scriptList .script-row").count() < rows_before
    _shot(page, "2_catalog_collapsed.png")
    _reload(page)
    page.evaluate("() => { state.showAllCategories = true; renderScripts(); }")
    assert page.locator(f'#scriptList .category-toggle[data-category="{key}"]').get_attribute("aria-expanded") == "false"
    page.locator(f'#scriptList .category-toggle[data-category="{key}"]').click()
    assert page.locator("#scriptList .script-row").count() == rows_before


def test_search_filters_all_categories_even_collapsed_and_shows_an_empty_state(catalog_page):
    page = catalog_page
    page.locator("#scriptList .category-toggle").first.click()      # collapsed...
    script = _first_visible(page)
    page.fill("#search", script["id"].split("/")[-1].replace(".py", "")[:6])
    assert _row(page, script).is_visible()                          # ...but a search still shows every match
    _shot(page, "3_catalog_search.png")
    page.fill("#search", "zzzz-no-such-script-zzzz")
    assert page.locator("#scriptList .script-row").count() == 0
    assert page.locator("#scriptList .hint").is_visible()
    page.fill("#search", "")
    assert page.locator("#scriptList .script-row").count() > 0


def test_favorites_live_in_local_storage_only_and_survive_a_reload(catalog_page):
    page = catalog_page
    script = _first_visible(page)
    _row(page, script).locator(".star-btn:not(.archive-btn)").click()
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('clipforgeFavScripts'))")
    assert script["id"] in stored
    assert page.favorite_posts == []                                # nothing is written to the server
    _reload(page)
    page.evaluate("() => { state.showAllCategories = false; renderScripts(); }")
    # (the first star click also seeds the server's favorites into this browser, so check the favorites section as a whole)
    assert page.evaluate("""(name) => { const kids = [...document.getElementById('scriptList').children];
        const head = kids.findIndex(e => e.classList.contains('category-toggle') || e.classList.contains('collapse-toggle-btn'));
        return kids.slice(0, head).some(e => e.classList.contains('script-row') && e.textContent.includes(name)); }""", script["name"])
    _shot(page, "4_catalog_favorites.png")
    page.evaluate("() => { state.showAllCategories = true; renderScripts(); }")
    pressed = page.locator("#scriptList .script-row", has=page.locator(".script-btn", has_text=script["name"])).first.locator(".star-btn:not(.archive-btn)").get_attribute("aria-pressed")
    assert pressed == "true"


def test_archiving_a_script_moves_it_to_the_archive_tab_and_back(catalog_page):
    page = catalog_page
    script = _first_visible(page)
    visible_before = page.locator("#scriptList .script-row").count()
    _row(page, script).locator(".archive-btn").click()
    assert page.locator("#scriptList .script-row").count() == visible_before - 1
    assert script["id"] in page.evaluate("() => JSON.parse(localStorage.getItem('clipforgeArchivedScripts'))")
    _reload(page)
    assert page.locator("#scriptList .script-row", has=page.locator(".script-btn", has_text=script["name"])).count() == 0
    page.evaluate("() => switchTab('archive')")
    entry = page.locator("#archiveList .script-row", has=page.locator(".script-btn", has_text=script["name"]))
    assert entry.count() == 1
    _shot(page, "5_catalog_archive_tab.png")
    entry.locator(".archive-btn").click()
    assert page.locator("#archiveList .script-row", has=page.locator(".script-btn", has_text=script["name"])).count() == 0
    page.evaluate("() => switchTab('scripts')")
    assert page.locator("#scriptList .script-row", has=page.locator(".script-btn", has_text=script["name"])).count() == 1


def test_server_archived_scripts_stay_in_the_archive_tab_without_a_restore_button(catalog_page):
    page = catalog_page
    page.evaluate("() => switchTab('archive')")
    names = page.evaluate("() => state.scripts.filter(s => s.archived).map(s => s.name)")
    assert names
    assert page.locator("#archiveList .script-row").count() == len(names)
    assert page.locator("#archiveList .archive-btn").count() == 0