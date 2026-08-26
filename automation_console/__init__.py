"""Compatibility import for tests and operators using the legacy package name."""

from console import server
from console import sellersprite_api_pipeline
from console import sellersprite_browser_export_pipeline

__all__ = ["server", "sellersprite_api_pipeline", "sellersprite_browser_export_pipeline"]
