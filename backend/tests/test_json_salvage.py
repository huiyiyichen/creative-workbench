from app.utils.json_salvage import salvage_truncated_json


def test_salvage_keeps_complete_cards():
    raw = '{"cards":[{"title":"甲","angle":"x"},{"title":"乙","angle":"写到一'
    assert salvage_truncated_json(raw) == {"cards": [{"title": "甲", "angle": "x"}]}


def test_salvage_complete_json_and_garbage():
    assert salvage_truncated_json('前言 {"a": [1, 2]} 后记') == {"a": [1, 2]}
    assert salvage_truncated_json("没有 JSON") is None
    assert salvage_truncated_json('{"a": "未闭合') is None


def test_salvage_braces_inside_strings():
    raw = '{"cards":[{"title":"含 } 和 ] 的标题"},{"title":"截'
    assert salvage_truncated_json(raw) == {"cards": [{"title": "含 } 和 ] 的标题"}]}
