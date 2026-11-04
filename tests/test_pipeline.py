"""Tests para JobSeekerPipeline - flujo completo del pipeline."""
import pytest
from unittest.mock import patch, MagicMock
from src.pipeline import JobSeekerPipeline


SAMPLE_PARAMS = {
    "project_name": "TestProject",
    "headline_title": "Test de Pipeline",
    "problem_context": "Problema de test.",
    "implementation_details": "Solucion de test.",
    "technical_findings": "Hallazgos de test.",
    "objectives_achieved": ["Obj1", "Obj2"],
    "tech_stack": ["Python", "Docker"],
}


class TestPipelineDryRun:
    """Tests del pipeline en modo dry-run (no toca LinkedIn ni Telegram)."""

    def test_dry_run_returns_true(self):
        pipeline = JobSeekerPipeline(dry_run=True, review_mode=False)
        result = pipeline.run_post(**SAMPLE_PARAMS)
        assert result is True

    def test_dry_run_with_code_snippet(self):
        pipeline = JobSeekerPipeline(dry_run=True, review_mode=False)
        result = pipeline.run_post(
            **SAMPLE_PARAMS,
            code_snippet="print('hello')"
        )
        assert result is True

    def test_dry_run_with_custom_image(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake png")
        pipeline = JobSeekerPipeline(dry_run=True, review_mode=False)
        result = pipeline.run_post(
            **SAMPLE_PARAMS,
            custom_image=img
        )
        assert result is True


class TestPipelineReviewMode:
    """Tests del modo de revision (Telegram desactivado = publica directo)."""

    @patch("src.pipeline.TelegramReviewer.is_configured", return_value=False)
    def test_falls_through_to_publish_when_telegram_not_configured(self, mock_tg):
        pipeline = JobSeekerPipeline(dry_run=True, review_mode=True)
        result = pipeline.run_post(**SAMPLE_PARAMS)
        assert result is True

    @patch("src.pipeline.TelegramReviewer.is_configured", return_value=True)
    @patch("src.pipeline.TelegramReviewer.send_draft", return_value=None)
    def test_returns_false_when_telegram_send_fails(self, mock_send, mock_cfg):
        pipeline = JobSeekerPipeline(dry_run=False, review_mode=True)
        result = pipeline.run_post(**SAMPLE_PARAMS)
        assert result is False
