"""
Historical Assessment Memory Adapter Compatibility Module.
DEPRECATION NOTICE: This module is retained as an internal backwards-compatibility alias.
It is scheduled for deprecation in v1.1.0. All new code must directly import:
`from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter`
PostgreSQL serves as the authoritative multi-tenant longitudinal memory store.
"""
from app.services.historical_memory_adapter import (
    HistoricalAssessmentMemoryAdapter,
    MementoMemoryAdapter
)

__all__ = ["HistoricalAssessmentMemoryAdapter", "MementoMemoryAdapter"]
