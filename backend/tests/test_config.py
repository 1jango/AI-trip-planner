from app.config import Settings


def test_cors_origin_list_splits_and_trims_commas() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins=" http://localhost:5173 , http://127.0.0.1:5173 ,",
    )

    assert settings.cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_api_key_is_hidden_in_repr() -> None:
    settings = Settings(_env_file=None, groq_api_key="super-secret")

    assert "super-secret" not in repr(settings)
