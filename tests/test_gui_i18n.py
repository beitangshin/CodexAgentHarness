from codex_agent_harness import gui


def test_slave_language_preference_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "LANGUAGE_PATH", tmp_path / "ui-language.txt")
    assert gui._load_language() == "zh"
    gui._save_language("en")
    assert gui._load_language() == "en"
    gui.LANGUAGE_PATH.write_text("unexpected", encoding="utf-8")
    assert gui._load_language() == "zh"


def test_slave_languages_cover_status_and_permission_choices():
    assert gui.LABELS.keys() == gui.LABELS_EN.keys()
    assert gui.MODE_LABELS.keys() == gui.MODE_LABELS_EN.keys()
    assert gui.MODE_HELP.keys() == gui.MODE_HELP_EN.keys()
