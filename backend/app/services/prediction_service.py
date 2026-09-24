"""
Prediction service – isolates model loading and inference.

Distinguishes between:
  - model_prediction: a real trained model produced the score
  - fallback_estimate: no model available, using rule-based heuristic
  - unavailable: prediction could not be produced at all

Never presents fallback scores as validated model predictions.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models.domain import (
    DelayRiskEstimate,
    PredictionStatus,
    RiskBand,
    RiskFactor,
)
from app.services.feature_builder import PredictionFeatures

logger = logging.getLogger(__name__)


# ── Abstract interface ───────────────────────────────────


class PredictionServiceBase(ABC):
    """Interface for delay-risk prediction."""

    @abstractmethod
    def predict(self, features: PredictionFeatures) -> DelayRiskEstimate:
        """Return a delay-risk estimate for the given features."""

    @abstractmethod
    def is_model_loaded(self) -> bool:
        """Return True if a trained model is available."""

    @abstractmethod
    def model_version(self) -> Optional[str]:
        """Return the loaded model version, or None."""


# ── XGBoost model implementation ─────────────────────────


class XGBoostPredictionService(PredictionServiceBase):
    """Production implementation – loads a trained XGBoost model from disk.

    Model requirements:
    - Trained with the pipeline in train_model.py
    - Serialized as .joblib via sklearn Pipeline
    - Located at MODEL_ARTIFACT_PATH env var
    - Expected features documented in docs/architecture.md
    """

    def __init__(self, model_path: str, version: str = ""):
        self._model = None
        self._version = version
        self._load_model(model_path)

    def _load_model(self, model_path: str):
        if not model_path:
            logger.info("No MODEL_ARTIFACT_PATH configured – model not loaded")
            return

        path = Path(model_path)
        if not path.exists():
            backend_path = Path(__file__).resolve().parent.parent.parent / model_path
            if backend_path.exists():
                path = backend_path
        if not path.exists():
            logger.warning("Model artifact not found at %s", model_path)
            return

        try:
            import joblib

            self._model = joblib.load(path)
            logger.info("Loaded model from %s (version: %s)", model_path, self._version)
        except Exception as exc:
            logger.error("Failed to load model from %s: %s", model_path, exc)
            self._model = None

    def predict(self, features: PredictionFeatures) -> DelayRiskEstimate:
        if self._model is None:
            return self._fallback_estimate(features)

        try:
            import numpy as np

            feature_vector = np.array(
                [
                    [
                        features.distance_km,
                        features.duration_minutes,
                        features.historical_avg_delay_minutes,
                        features.historical_delay_rate,
                        features.historical_shipment_count,
                        features.sensor_alert_count,
                        int(features.has_temperature_alert),
                        int(features.has_vibration_alert),
                        int(features.has_humidity_alert),
                        features.weight_kg,
                        features.linked_locations_with_delays,
                        features.total_linked_locations,
                    ]
                ]
            )

            probability = float(self._model.predict_proba(feature_vector)[0][1])
            risk_band = self._probability_to_band(probability)

            return DelayRiskEstimate(
                probability=round(probability, 4),
                risk_band=risk_band,
                prediction_status=PredictionStatus.MODEL_PREDICTION,
                model_version=self._version,
                factors=features.contributing_factors,
                message=f"Prediction from trained model v{self._version}",
            )
        except Exception as exc:
            logger.error("Model inference failed: %s", exc)
            return self._fallback_estimate(features)

    def is_model_loaded(self) -> bool:
        return self._model is not None

    def model_version(self) -> Optional[str]:
        return self._version if self._model else None

    @staticmethod
    def _fallback_estimate(features: PredictionFeatures) -> DelayRiskEstimate:
        """Rule-based fallback – clearly labelled as non-model estimate."""
        return FallbackPredictionService().predict(features)

    @staticmethod
    def _probability_to_band(prob: float) -> RiskBand:
        if prob < 0.25:
            return RiskBand.LOW
        elif prob < 0.50:
            return RiskBand.MEDIUM
        elif prob < 0.75:
            return RiskBand.HIGH
        return RiskBand.CRITICAL


# ── Fallback / demo implementation ──────────────────────


class FallbackPredictionService(PredictionServiceBase):
    """Rule-based fallback estimator.

    Used when no trained model is available. Produces heuristic scores
    based on route distance, historical patterns, and sensor alerts.

    IMPORTANT: Results are explicitly labelled as 'fallback_estimate'
    and must not be presented as validated model predictions.
    """

    def predict(self, features: PredictionFeatures) -> DelayRiskEstimate:
        """Compute a heuristic delay probability from available features."""
        score = 0.15  # base risk

        # Distance contribution (0 – 0.2)
        if features.distance_km > 2000:
            score += 0.20
        elif features.distance_km > 1000:
            score += 0.12
        elif features.distance_km > 500:
            score += 0.06

        # Historical delay rate (0 – 0.25)
        score += min(features.historical_delay_rate * 0.5, 0.25)

        # Sensor alerts (0 – 0.15)
        if features.sensor_alert_count > 2:
            score += 0.15
        elif features.sensor_alert_count > 0:
            score += 0.08

        # Weight factor (0 – 0.05)
        if features.weight_kg > 4000:
            score += 0.05
        elif features.weight_kg > 2000:
            score += 0.02

        # Network disruptions (0 – 0.10)
        if features.linked_locations_with_delays > 0:
            score += min(features.linked_locations_with_delays * 0.05, 0.10)

        # Season (0 – 0.08)
        if features.season == "monsoon":
            score += 0.08

        # Clamp to [0, 1]
        probability = max(0.0, min(1.0, score))
        risk_band = self._probability_to_band(probability)

        factors = list(features.contributing_factors) if features.contributing_factors else []
        if not factors:
            if features.distance_km > 500:
                factors.append(
                    RiskFactor(
                        name="Route distance",
                        description=f"{features.distance_km:.0f} km corridor increases exposure to transit variability",
                        impact="increases_risk",
                    )
                )
            if features.historical_delay_rate > 0.15:
                factors.append(
                    RiskFactor(
                        name="Historical delay patterns",
                        description=f"Corridor historical delay frequency is {features.historical_delay_rate * 100:.0f}%",
                        impact="increases_risk",
                    )
                )
            if features.sensor_alert_count > 0:
                factors.append(
                    RiskFactor(
                        name="Sensor telemetry anomalies",
                        description=f"{features.sensor_alert_count} alert(s) registered on this shipment profile",
                        impact="increases_risk",
                    )
                )
            if not factors:
                factors.append(
                    RiskFactor(
                        name="Baseline corridor metrics",
                        description="Short distance and normal operational baseline",
                        impact="decreases_risk",
                    )
                )

        return DelayRiskEstimate(
            probability=round(probability, 4),
            risk_band=risk_band,
            prediction_status=PredictionStatus.FALLBACK_ESTIMATE,
            model_version=None,
            factors=factors,
            message=(
                "This is a rule-based fallback estimate, not a trained model prediction. "
                "It uses route distance, historical delay patterns, sensor alerts, and "
                "network disruptions to approximate risk. Configure a trained model for "
                "validated predictions."
            ),
        )

    def is_model_loaded(self) -> bool:
        return False

    def model_version(self) -> Optional[str]:
        return None

    @staticmethod
    def _probability_to_band(prob: float) -> RiskBand:
        if prob < 0.25:
            return RiskBand.LOW
        elif prob < 0.50:
            return RiskBand.MEDIUM
        elif prob < 0.75:
            return RiskBand.HIGH
        return RiskBand.CRITICAL


# ── Factory ──────────────────────────────────────────────


def create_prediction_service(
    model_path: str = "", model_version: str = ""
) -> PredictionServiceBase:
    """Create the appropriate prediction service based on config."""
    if model_path:
        service = XGBoostPredictionService(model_path, model_version)
        if service.is_model_loaded():
            return service
        logger.warning("Model could not be loaded, using fallback estimator")

    return FallbackPredictionService()
