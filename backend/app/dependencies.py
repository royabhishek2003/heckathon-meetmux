"""
Dependency injection – creates and provides service instances.

Services are initialized once at startup and shared across requests.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.services.feature_builder import FeatureBuilder
from app.services.graph_service import (
    GraphServiceBase,
    InMemoryGraphService,
    Neo4jGraphService,
)
from app.services.prediction_service import (
    PredictionServiceBase,
    create_prediction_service,
)
from app.services.route_service import (
    RouteProviderBase,
    create_route_provider,
)

logger = logging.getLogger(__name__)


# ── Singleton holders ────────────────────────────────────

_graph_service: Optional[GraphServiceBase] = None
_route_provider: Optional[RouteProviderBase] = None
_prediction_service: Optional[PredictionServiceBase] = None
_feature_builder: Optional[FeatureBuilder] = None
_neo4j_driver = None


def ensure_services():
    """Ensure in-memory and default services are initialized synchronously if accessed before lifespan."""
    global _graph_service, _route_provider, _prediction_service, _feature_builder
    if _graph_service is None:
        _graph_service = InMemoryGraphService()
    if _route_provider is None:
        _route_provider = create_route_provider(
            settings.route_provider,
            settings.osrm_base_url,
            settings.route_timeout_seconds,
        )
    if _prediction_service is None:
        _prediction_service = create_prediction_service(
            settings.model_artifact_path,
            settings.model_version,
        )
    if _feature_builder is None:
        _feature_builder = FeatureBuilder()


async def init_services():
    """Initialize all services at application startup."""
    global _graph_service, _route_provider, _prediction_service, _feature_builder, _neo4j_driver

    # ── Graph service ────────────────────────
    try:
        if settings.neo4j_password and settings.neo4j_uri:
            from neo4j import AsyncGraphDatabase

            _neo4j_driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                connection_timeout=2.0,
            )
            # Verify connectivity
            async with _neo4j_driver.session(database=settings.neo4j_database) as session:
                await session.run("RETURN 1")

            _graph_service = Neo4jGraphService(_neo4j_driver, settings.neo4j_database)
            logger.info("Connected to Neo4j at %s", settings.neo4j_uri)
        else:
            _graph_service = InMemoryGraphService()
    except Exception as exc:
        logger.warning("Neo4j unavailable (%s) – using in-memory demo data", exc)
        _graph_service = InMemoryGraphService()

    # ── Ensure all providers are active ──────
    ensure_services()


async def shutdown_services():
    """Cleanup on application shutdown."""
    global _neo4j_driver, _route_provider

    if _neo4j_driver:
        await _neo4j_driver.close()
        logger.info("Neo4j driver closed")

    if hasattr(_route_provider, "close"):
        await _route_provider.close()


# ── Dependency getters ───────────────────────────────────


def get_graph_service() -> GraphServiceBase:
    if _graph_service is None:
        ensure_services()
    return _graph_service


def get_route_provider() -> RouteProviderBase:
    if _route_provider is None:
        ensure_services()
    return _route_provider


def get_prediction_service() -> PredictionServiceBase:
    if _prediction_service is None:
        ensure_services()
    return _prediction_service


def get_feature_builder() -> FeatureBuilder:
    if _feature_builder is None:
        ensure_services()
    return _feature_builder

