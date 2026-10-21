import httpx
import pytest

from app.services.llm import remote_models as rm


def test_parse_openai_gemini_and_list():
    assert [m["id"] for m in rm.parse_models({"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]})] == ["a", "b"]
    assert rm.parse_models({"models": [{"name": "models/gemini-2.5-pro"}]})[0]["id"] == "gemini-2.5-pro"
    assert rm.parse_models(["x"])[0]["id"] == "x"
    assert rm.parse_models("oops") == []


def test_resolve_base():
    assert rm.resolve_base("https://relay.example.com/v1/", None, "openai") == "https://relay.example.com/v1"
    assert rm.resolve_base(None, "deepseek", "openai") == "https://api.deepseek.com/v1"
    with pytest.raises(rm.RemoteModelsError):
        rm.resolve_base(None, "openai_compatible_unknown", "openai")


@pytest.mark.asyncio
async def test_list_remote_models_errors_and_success(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        if "bad" in str(request.url):
            return httpx.Response(401, json={"error": "no"})
        return httpx.Response(200, json={"data": [{"id": "deepseek-chat", "owned_by": "relay"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(rm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    out = await rm.list_remote_models(api_base="https://relay.example.com/v1", api_key="k", provider=None)
    assert out["models"][0]["id"] == "deepseek-chat" and seen["auth"] == "Bearer k"
    with pytest.raises(rm.RemoteModelsError, match="Key"):
        await rm.list_remote_models(api_base="https://bad.example.com/v1", api_key="k", provider=None)
