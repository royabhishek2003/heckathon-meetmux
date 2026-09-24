"""Application settings loaded from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import find_dotenv, load_dotenv

# Load .env configuration
load_dotenv(find_dotenv(usecwd=True))


def _parse_cors_origins(raw: str) -> List[str]:
    """Parse CORS origins from env – accepts JSON array or comma-separated."""
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable application settings read once at startup."""

    # ── Application ──────────────────────────
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-to-a-random-secret"

    # ── Backend ──────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "info"

    # ── Neo4j ────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # ── Routing ──────────────────────────────
    route_provider: str = "mock"  # osrm_self_hosted | osrm_public_demo | mock
    osrm_base_url: str = "http://localhost:5000"
    route_timeout_seconds: int = 10

    # ── Map tiles ────────────────────────────
    map_tile_provider: str = "osm"
    mapbox_access_token: str = ""
    custom_tile_url: str = ""
    custom_tile_attribution: str = ""

    # ── Prediction ───────────────────────────
    model_artifact_path: str = ""
    model_version: str = ""

    # ── Auth ─────────────────────────────────
    auth_enabled: bool = False
    auth_jwks_url: str = ""
    auth_audience: str = ""
    auth_issuer: str = ""

    # ── Rate limiting ────────────────────────
    rate_limit_per_minute: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables with sensible defaults."""

        def _env(key: str, default: str = "") -> str:
            return os.getenv(key, default)

        def _bool(key: str, default: bool = False) -> bool:
            return _env(key, str(default)).lower() in ("true", "1", "yes")

        def _int(key: str, default: int = 0) -> int:
            try:
                return int(_env(key, str(default)))
            except ValueError:
                return default

        return cls(
            app_env=_env("APP_ENV", "development"),
            debug=_bool("APP_DEBUG", False),
            secret_key=_env("APP_SECRET_KEY", "change-me-to-a-random-secret"),
            host=_env("BACKEND_HOST", "0.0.0.0"),
            port=_int("PORT", _int("BACKEND_PORT", 8000)),
            cors_origins=_parse_cors_origins(
                _env("BACKEND_CORS_ORIGINS", '["http://localhost:5173"]')
            ),
            log_level=_env("BACKEND_LOG_LEVEL", "info"),
            neo4j_uri=_env("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=_env("NEO4J_USER", "neo4j"),
            neo4j_password=_env("NEO4J_PASSWORD", ""),
            neo4j_database=_env("NEO4J_DATABASE", "neo4j"),
            route_provider=_env("ROUTE_PROVIDER", "mock"),
            osrm_base_url=_env("OSRM_BASE_URL", "http://localhost:5000"),
            route_timeout_seconds=_int("ROUTE_TIMEOUT_SECONDS", 10),
            map_tile_provider=_env("MAP_TILE_PROVIDER", "osm"),
            mapbox_access_token=_env("MAPBOX_ACCESS_TOKEN", ""),
            custom_tile_url=_env("CUSTOM_TILE_URL", ""),
            custom_tile_attribution=_env("CUSTOM_TILE_ATTRIBUTION", ""),
            model_artifact_path=_env("MODEL_ARTIFACT_PATH", ""),
            model_version=_env("MODEL_VERSION", ""),
            auth_enabled=_bool("AUTH_ENABLED", False),
            auth_jwks_url=_env("AUTH_JWKS_URL", ""),
            auth_audience=_env("AUTH_AUDIENCE", ""),
            auth_issuer=_env("AUTH_ISSUER", ""),
            rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 60),
        )


# Singleton – import and use `settings` throughout the app
settings = Settings.from_env()
