"""test_history.py - checks that history entries carry the fields the merged Downloads panel
needs (preset_id, content, section, job_id) and that list_entries()/count_entries() page
correctly. No test_history.py was among the files given for this change, so this is a fresh
file - if the project already has one elsewhere, merge these cases into it instead of keeping
both.
"""

import importlib


def _fresh_history(tmp_path, monkeypatch):
    """Points history.py at a throwaway data folder and returns a freshly-imported module."""
    import app.history as history
    importlib.reload(history)
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.json")
    return history


def test_add_entry_stores_new_fields(tmp_path, monkeypatch):
    history = _fresh_history(tmp_path, monkeypatch)
    section = {"start": 5.0, "end": 10.0, "padded_start": 3.0, "padded_end": 12.0}

    history.add_entry(
        title="My Clip", url="https://youtu.be/abc123", platform_name="youtube",
        preset_summary="Premiere ready", path=str(tmp_path / "clip.mp4"),
        preset_id="premiere", content="video_audio", section=section, job_id="job-1",
    )

    [entry] = history.list_entries()
    assert entry["preset_id"] == "premiere"
    assert entry["content"] == "video_audio"
    assert entry["section"] == section
    assert entry["job_id"] == "job-1"
    assert entry["file_exists"] is False   # nothing was actually written to clip.mp4


def test_add_entry_defaults_new_fields_to_none(tmp_path, monkeypatch):
    """Older call sites (or a future caller that skips the new keyword args) still work."""
    history = _fresh_history(tmp_path, monkeypatch)

    history.add_entry(title="Old style", url="https://youtu.be/xyz", platform_name="youtube",
                      preset_summary="Custom", path=str(tmp_path / "old.mp4"))

    [entry] = history.list_entries()
    assert entry["preset_id"] is None
    assert entry["content"] is None
    assert entry["section"] is None
    assert entry["job_id"] is None


def test_list_entries_pagination_and_count(tmp_path, monkeypatch):
    history = _fresh_history(tmp_path, monkeypatch)
    for index in range(5):
        history.add_entry(title=f"Clip {index}", url=f"https://youtu.be/{index}",
                          platform_name="youtube", preset_summary="Premiere ready",
                          path=str(tmp_path / f"clip{index}.mp4"))

    assert history.count_entries() == 5
    first_page = history.list_entries(limit=2, offset=0)
    second_page = history.list_entries(limit=2, offset=2)
    assert [entry["title"] for entry in first_page] == ["Clip 4", "Clip 3"]
    assert [entry["title"] for entry in second_page] == ["Clip 2", "Clip 1"]
    # Backward compatible: no limit/offset still returns everything, newest first.
    assert len(history.list_entries()) == 5