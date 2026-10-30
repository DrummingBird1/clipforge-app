# tests/web/test_web_frontend_safety.py
#
# גל 22 (יציבות ובטיחות) - בדיקות סטטיות על קוד הפרונט של ממשק הדפדפן:
#  - שום נתון לא נכנס ל-innerHTML בלי uiEscape (שמות קבצים מגיעים גם מכותרות קליפים
#    ב-Twitch, פרטי שגיאות מגיעים משירותים חיצוניים, פרופילים מקישורי שיתוף).
#  - שום handler (onclick="...") לא נבנה מנתונים.
#  - בלי prompt()/confirm() של הדפדפן - vePrompt/veConfirm בתוך הדף.
#  - מסלולי fetch-ורינדור עוברים דרך uiLatest ("רק הבקשה האחרונה קובעת").
#  - זרימת התור עוברת דרך veFlow, ומספר העטיפות של פונקציות רק יורד (uiBus במקומן).
import re


from entrypoints.web import frontend_assembly as fa


def _js_parts():
    return [(part, fa.read_part(part)) for part in fa.page_parts() if part.endswith(".js")]


def _strip_comments(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))


def _statement(source, start, stop_at_semicolon=True):
    """הביטוי שמתחיל ב-start ועד ה-; / הסוגר שסוגר אותו - מדלג על מחרוזות ותבניות."""
    stack = []
    i = start
    while i < len(source):
        ch = source[i]
        top = stack[-1] if stack else None
        if top in ("'", '"'):
            if ch == "\\":
                i += 2
                continue
            if ch == top:
                stack.pop()
        elif top == "`":
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                stack.pop()
            elif source.startswith("${", i):
                stack.append("{")
                i += 2
                continue
        else:
            if ch in "'\"`":
                stack.append(ch)
            elif ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                if not stack:
                    return source[start:i]
                stack.pop()
            elif ch == ";" and not stack and stop_at_semicolon:
                return source[start:i]
        i += 1
    return source[start:]


def _without_calls(expression, name):
    """מחליף כל קריאה ל-name(...) ב-"" (סוגריים מאוזנים, מודע למחרוזות)."""
    out = expression
    while True:
        index = out.find(name + "(")
        if index < 0:
            return out
        body = _statement(out, index + len(name) + 1)
        out = out[:index] + '""' + out[index + len(name) + 1 + len(body) + 1:]


_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"' + r"|'(?:[^'\\]|\\.)*'" + r"|`[^`$]*`", re.S)


def _is_safe_html(expression):
    expression = expression.strip()
    if re.fullmatch(r"[\w.]+\.innerHTML", expression):  # העתקה של DOM שכבר בדף
        return True
    reduced = _without_calls(expression, "uiEscape").replace('${""}', "")
    reduced = _STRING_LITERAL.sub("", reduced)
    return re.fullmatch(r"[\s+()]*", reduced) is not None


def _html_sinks():
    for part, source in _js_parts():
        code = _strip_comments(source)
        for match in re.finditer(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)", code):
            yield part, code[:match.start()].count("\n") + 1, _statement(code, match.end())
        for match in re.finditer(r"insertAdjacentHTML\(", code):
            args = _statement(code, match.end())
            first_comma = args.find(",")
            yield part, code[:match.start()].count("\n") + 1, args[first_comma + 1:]


def test_every_value_in_html_goes_through_ui_escape():
    unsafe = [f"{part}:{line}: {expr.strip()[:120]}" for part, line, expr in _html_sinks() if not _is_safe_html(expr)]
    assert unsafe == [], "נתון נכנס ל-HTML בלי uiEscape (או בנה DOM עם textContent):\n" + "\n".join(unsafe)


def test_the_lint_itself_catches_unescaped_values():
    assert _is_safe_html('"<b>static</b>"')
    assert _is_safe_html("`<span>${uiEscape(name)}</span>`")
    assert _is_safe_html('"<i>" + uiEscape(a + b) + "</i>"')
    assert _is_safe_html("other.innerHTML")
    assert not _is_safe_html("`<span>${name}</span>`")
    assert not _is_safe_html('"<b>" + name + "</b>"')
    assert not _is_safe_html("names.map(n => `<option>${n}</option>`).join('')")
    assert not _is_safe_html("html")


def test_no_inline_handlers_built_from_data():
    offenders = []
    for part, source in _js_parts():
        code = _strip_comments(source)
        for match in re.finditer(r"""\bon[a-z]+=\\?["'][^"'`]*\$\{""", code):
            offenders.append(f"{part}:{code[:match.start()].count(chr(10)) + 1}")
    assert offenders == [], f"onclick=\"...${{...}}\" - escape של HTML לא מגן בתוך JS, השתמש ב-addEventListener: {offenders}"


def test_no_native_prompt_or_confirm():
    offenders = []
    for part, source in _js_parts():
        code = _strip_comments(source)
        for match in re.finditer(r"(?<![\w.$])(?:window\.)?(prompt|confirm)\(", code):
            offenders.append(f"{part}:{code[:match.start()].count(chr(10)) + 1}: {match.group(0)}")
    assert offenders == [], f"prompt()/confirm() של הדפדפן - השתמש ב-vePrompt/veConfirm: {offenders}"
    page = fa.assemble_inline_page()
    for marker in ('id="vePromptModalBg"', 'id="vePromptInput"', "function vePrompt("):
        assert marker in page, marker


def _function_bodies(source, name):
    """כל ההגדרות של name לפי הסדר (קובץ מאוחר יותר מחליף או עוטף את הקודם)."""
    pattern = r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(|\b" + re.escape(name) + r"\s*=\s*(?:async\s+)?function\s*\("
    bodies = []
    for match in re.finditer(pattern, source):
        open_brace = source.index("{", match.end())
        bodies.append(_statement(source, open_brace + 1, stop_at_semicolon=False))
    assert bodies, name
    return bodies


def test_fetch_and_render_paths_use_latest_request_wins():
    source = "\n".join(content for _part, content in _js_parts())
    for name in ("runVeValidation", "runVeEstimate", "loadVeTimeline", "_veLoadTimelineStrip", "loadVeLoudness",
                 "_loadAndShowProfileMeta", "_runProfileComparison", "refreshVeJobs", "_veLoadQueueMeta",
                 "_veLoadQueueLastRun", "updateVeEtaDisplay"):
        # ההגדרה האחרונה שבאמת שולחת fetch (עטיפה מאוחרת בלי fetch קוראת לה) היא זו שחייבת uiLatest
        fetching = next(body for body in reversed(_function_bodies(source, name)) if "fetch(" in body)
        assert "uiLatest(" in fetching, f"{name} לא עובר דרך uiLatest"


def test_queue_flow_is_owned_by_ve_flow():
    source = "\n".join(content for _part, content in _js_parts())
    for legacy in ("_vePendingQueueRestore", "_veQueueRefreshSeq"):
        assert legacy not in source, f"{legacy} - מצב התור עבר ל-veFlow (07-ui-flow.js)"
    assert source.count('veFlow.requestQueueRestore(') == 2  # פרופיל + פרויקט
    assert 'uiBus.on("ve:folder-changed"' in source


def test_wrapper_count_only_goes_down():
    """גל 22: עטיפה חדשה של פונקציה קיימת (const _xBeforeY = x; x = function...) היא הדרך
    שבה הבאג של התור נוצר. במקום - uiBus.on(...) או uiPaletteProviders. המספר רק יורד."""
    source = "\n".join(content for _part, content in _js_parts())
    wrappers = re.findall(r"const _[A-Za-z0-9]+Before[A-Za-z0-9]+ =", source)
    assert len(wrappers) <= 57, f"{len(wrappers)} עטיפות - השתמש ב-uiBus.on/uiPaletteProviders במקום עטיפה חדשה"
    for event in ("ve:folder-changed", "ve:fields-applied", "ve:derived-refresh", "ve:results-shown"):
        assert f'uiBus.emit("{event}"' in source, event


def test_top_level_names_are_declared_once_across_the_bundle():
    """גל 28: כל ה-JS הוא סקריפט אחד - שם שמוגדר פעמיים ברמה העליונה (const/let/function/class)
    מפיל את כל הבאנדל ב-SyntaxError ("Identifier ... has already been declared"), והדף לא עולה."""
    seen = {}
    duplicates = []
    pattern = re.compile(r"^(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", re.M)
    for part, content in _js_parts():
        for name in pattern.findall(_strip_comments(content)):
            if name in seen:
                duplicates.append((name, seen[name], part))
            else:
                seen[name] = part
    assert duplicates == [], duplicates
    assert len(seen) > 500
