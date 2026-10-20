from app.services.discovery import platform_group


def test_platform_group():
    assert platform_group("Hacker News") == "hn"
    assert platform_group("B站") == "bilibili"
    assert platform_group("GitHub") == "github"
    assert platform_group("NVIDIA") == "web"
    assert platform_group(None) == "web"
