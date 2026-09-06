from apps.api import app as api_app


def test_neatlogs_initializes_from_environment(monkeypatch):
    calls = []
    monkeypatch.setenv("NEATLOGS_API_KEY", "test-project-key")
    monkeypatch.setenv("NEATLOGS_ENDPOINT", "test-endpoint")
    monkeypatch.setattr(api_app.neatlogs, "init", lambda **kwargs: calls.append(kwargs))

    api_app._configure_neatlogs()

    assert calls == [
        {
            "api_key": "test-project-key",
            "endpoint": "test-endpoint",
            "workflow_name": "finance-reconciliation-investigation",
            "instrumentations": ["openai"],
        }
    ]


def test_neatlogs_stays_disabled_without_api_key(monkeypatch):
    calls = []
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.setattr(api_app.neatlogs, "init", lambda **kwargs: calls.append(kwargs))

    api_app._configure_neatlogs()

    assert calls == []
