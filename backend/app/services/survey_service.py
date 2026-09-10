"""Backward-compatible shim.  Real implementation lives in app.services.survey."""
from app.services.survey import SurveyService, survey_service  # noqa: F401

__all__ = ["survey_service"]
