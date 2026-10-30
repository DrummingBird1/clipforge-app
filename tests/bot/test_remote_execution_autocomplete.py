# tests/bot/test_remote_execution_autocomplete.py
#
# בודק את השלמה-אוטומטית של --script_name בפקודת /run_script (item 23) -
# רק פונקציית הסינון עצמה (glob + סינון לפי current), בלי צורך בחיבור
# דיסקורד/בוט אמיתי - _script_name_autocomplete לא נוגע ב-self.bot בכלל.
import asyncio


from cogs.remote_execution import RemoteExecution


def _make_cog(scripts_dir):
    cog = RemoteExecution(bot=None)
    cog.scripts_dir = str(scripts_dir)
    return cog


def _run(coro):
    return asyncio.run(coro)


def test_autocomplete_lists_all_scripts_when_current_is_empty(tmp_path):
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "story_cutter.py").write_text("", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "disk_scanner.py").write_text("", encoding="utf-8")
    cog = _make_cog(tmp_path)

    choices = _run(cog._script_name_autocomplete(None, ""))

    names = sorted(c.value for c in choices)
    assert names == ["disk_scanner.py", "story_cutter.py"]


def test_autocomplete_filters_case_insensitively_by_substring(tmp_path):
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "story_cutter.py").write_text("", encoding="utf-8")
    (tmp_path / "video" / "video_editor.py").write_text("", encoding="utf-8")
    cog = _make_cog(tmp_path)

    choices = _run(cog._script_name_autocomplete(None, "STORY"))

    assert [c.value for c in choices] == ["story_cutter.py"]


def test_autocomplete_returns_empty_for_no_match(tmp_path):
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "story_cutter.py").write_text("", encoding="utf-8")
    cog = _make_cog(tmp_path)

    choices = _run(cog._script_name_autocomplete(None, "nonexistent_script"))

    assert choices == []


def test_autocomplete_caps_at_25_choices(tmp_path):
    (tmp_path / "video").mkdir()
    for i in range(30):
        (tmp_path / "video" / f"script_{i:02d}.py").write_text("", encoding="utf-8")
    cog = _make_cog(tmp_path)

    choices = _run(cog._script_name_autocomplete(None, ""))

    assert len(choices) == 25


def test_autocomplete_choice_name_and_value_are_both_the_filename(tmp_path):
    # app_commands.Choice(name=..., value=...) - שניהם צריכים להיות שם הקובץ
    # עצמו, כדי שהערך שנשלח בפועל ל-run_script יהיה שם קובץ תקין.
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "story_cutter.py").write_text("", encoding="utf-8")
    cog = _make_cog(tmp_path)

    choices = _run(cog._script_name_autocomplete(None, ""))

    assert len(choices) == 1
    assert choices[0].name == "story_cutter.py"
    assert choices[0].value == "story_cutter.py"
