from nova.config import BOLT, SUPER, ULTRA, Settings
from nova.gateway import Capability, Gateway
from nova.store import Store


def test_missing_models_fall_back_to_the_strongest_listed(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "r.db", planner_model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
                        reasoning_model="deepseek-ai/deepseek-v4-flash")
    gateway = Gateway(settings, Store(settings.database_path))
    catalogue = [BOLT, SUPER, ULTRA]
    # Retired IDs (HTTP 410) no longer drop planning to the smallest model.
    assert gateway.resolve(Capability.PLANNING, catalogue) == ULTRA
    assert gateway.resolve(Capability.REASONING, catalogue) == SUPER
    assert gateway.resolve(Capability.PLANNING, [BOLT]) == BOLT
    assert gateway.resolve(Capability.PLANNING, []) is None
    settings.planner_model = SUPER
    assert gateway.resolve(Capability.PLANNING, catalogue) == SUPER  # an available configured model always wins


async def test_visual_review_disables_thinking_for_non_omni_critics(tmp_path):
    import json

    import httpx

    sent = {}

    def provider(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": SUPER}]})
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OVERALL: 7"}}], "usage": {}})

    settings = Settings(_env_file=None, nvidia_api_key="test", database_path=tmp_path / "v.db")
    gateway = Gateway(settings, Store(settings.database_path), httpx.MockTransport(provider))
    result = await gateway.visual_review(b"\x89PNG\r\n\x1a\n" + b"0" * 64, "test")
    assert result["model"] == SUPER and sent["chat_template_kwargs"] == {"enable_thinking": False}
    await gateway.close()
