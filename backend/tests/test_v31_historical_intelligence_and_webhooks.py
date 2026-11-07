"""
TechDebt AI v3.1.0 — Test Suite for Historical Intelligence,
Commit-Linked 10D Comparison, and Webhook Delivery Idempotency (GAP-HIST-01).
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter
from app.models.all_models import Assessment, CodeFinding, RiskFinding, WebhookDeliveryEvent, RepositoryConnection
from app.api.v1.repositories import _record_webhook_delivery_idempotent


def test_historical_delta_comparison_with_10d_and_methodology_change():
    async def _test():
        adapter = HistoricalAssessmentMemoryAdapter()
        mock_db = MagicMock()

        # Mock current assessment (v3.1.0)
        curr = MagicMock(spec=Assessment)
        curr.id = "asmt-current"
        curr.project_id = "proj-1"
        curr.created_at = datetime(2026, 11, 7, 12, 0, 0)
        curr.overall_health_score = 88.0
        curr.risk_classification = "Good"
        curr.commit_sha = "abc1234"
        curr.analyzer_version = "v3.1.0"
        curr.scoring_version = "v3.1.0"
        curr.code_maintainability_score = 85.0
        curr.architecture_score = 90.0
        curr.dependency_score = 82.0
        curr.security_score = 95.0
        curr.test_quality_score = 80.0
        curr.documentation_score = 85.0
        curr.reliability_score = 88.0
        curr.performance_score = 90.0
        curr.complexity_score = 85.0
        curr.upgrade_risk_score = 80.0
        curr.scores = []

        # Mock prior assessment (v2.0.0)
        prior = MagicMock(spec=Assessment)
        prior.id = "asmt-prior"
        prior.project_id = "proj-1"
        prior.created_at = datetime(2026, 11, 1, 12, 0, 0)
        prior.overall_health_score = 80.0
        prior.risk_classification = "Moderate"
        prior.commit_sha = "xyz9876"
        prior.analyzer_version = "v2.0.0"
        prior.scoring_version = "v2.0.0"
        prior.code_maintainability_score = 75.0
        prior.architecture_score = 80.0
        prior.dependency_score = 80.0
        prior.security_score = 85.0
        prior.test_quality_score = 70.0
        prior.documentation_score = 80.0
        prior.reliability_score = 80.0
        prior.performance_score = 85.0
        prior.complexity_score = 75.0
        prior.upgrade_risk_score = 75.0
        prior.scores = []

        # Configure DB mock queries
        query_mock = MagicMock()
        mock_db.query.return_value = query_mock
        query_mock.join.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock

        # First query: Assessment by id -> curr
        # Second query: HistoricalAssessment -> None
        # Third query: prior assessment -> prior
        # Fourth, fifth: RiskFindings -> []
        # Sixth, seventh: CodeFindings -> []
        query_mock.first.side_effect = [curr, None, prior]
        query_mock.all.side_effect = [[], [], [], []]

        comparison = await adapter.generate_delta_comparison(mock_db, "asmt-current")

        assert comparison["has_prior_assessment"] is True
        assert comparison["current_health_score"] == 88.0
        assert comparison["prior_health_score"] == 80.0
        assert comparison["score_change"] == 8.0
        assert comparison["commit_sha"] == "abc1234"
        assert comparison["prior_commit_sha"] == "xyz9876"
        assert comparison["methodology_changed"] is True
        assert "methodology_notice" in comparison and len(comparison["methodology_notice"]) > 0

        # Check 10 dimensions changes
        dim_changes = {d["dimension"]: d for d in comparison["dimensional_changes"]}
        assert len(dim_changes) == 10
        assert dim_changes["code_maintainability"]["delta"] == 10.0
        assert dim_changes["security"]["delta"] == 10.0

    asyncio.run(_test())


def test_webhook_delivery_idempotency_records_and_rejects_duplicates():
    mock_db = MagicMock()
    mock_conn = MagicMock(spec=RepositoryConnection)
    mock_conn.id = "conn-1"
    mock_conn.org_id = "org-1"
    mock_conn.project_id = "proj-1"

    query_mock = MagicMock()
    mock_db.query.return_value = query_mock
    query_mock.filter.return_value = query_mock

    # First delivery: no existing event found
    query_mock.first.return_value = None
    res1 = _record_webhook_delivery_idempotent(
        mock_db,
        provider="github",
        delivery_id="deliv-abc-123",
        event_type="push",
        conn=mock_conn,
        raw_body=b'{"ref": "refs/heads/main"}'
    )
    assert res1 is True
    assert mock_db.add.called
    assert mock_db.flush.called

    # Second delivery: duplicate delivery found
    query_mock.first.return_value = MagicMock(spec=WebhookDeliveryEvent)
    res2 = _record_webhook_delivery_idempotent(
        mock_db,
        provider="github",
        delivery_id="deliv-abc-123",
        event_type="push",
        conn=mock_conn,
        raw_body=b'{"ref": "refs/heads/main"}'
    )
    assert res2 is False
