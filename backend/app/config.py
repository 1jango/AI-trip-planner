"""Konfiguracja aplikacji wczytywana ze zmiennych środowiskowych i pliku .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env leży w katalogu głównym repo (obok .env.example), a nie w backend/.
# Ścieżka liczona od tego pliku działa niezależnie od katalogu, z którego uruchamiasz serwer.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # nieznane zmienne w .env (np. dla frontendu) nie powodują błędu
    )

    app_name: str = "AI Trip Planner"
    app_version: str = "0.1.0"

    # SecretStr ukrywa wartość w logach i repr(): print(settings) pokaże '**********'.
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"

    transitous_base_url: str = "https://api.transitous.org"
    app_contact: str = ""

    database_url: str = f"sqlite:///{REPO_ROOT / 'trip_planner.db'}"

    # Zwykły string rozdzielany przecinkami. Pole typu list[str] wymagałoby w .env
    # formatu JSON (["http://..."]) — łatwo o to potknąć się przy ręcznej edycji.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def ai_available(self) -> bool:
        return self.groq_api_key is not None and self.groq_api_key.get_secret_value().strip() != ""


@lru_cache
def get_settings() -> Settings:
    """Zwraca jedną, współdzieloną instancję ustawień (plik .env czytany tylko raz)."""
    return Settings()
