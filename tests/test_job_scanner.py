"""Tests para JobScanner - radar de ofertas de empleo."""
import json
import pytest
from unittest.mock import patch
from datetime import date, datetime
from src.job_scanner import JobScanner, _extract_tech_stack


class TestExtractTechStack:
    """Tests de la deteccion de tecnologias en descripciones de ofertas."""

    def test_detects_python(self):
        stacks = _extract_tech_stack("Buscamos desarrollador con experiencia en Python y Django.")
        assert any("python" in s.lower() for s in stacks)
        assert any("django" in s.lower() for s in stacks)

    def test_detects_javascript_ecosystem(self):
        stacks = _extract_tech_stack("Necesitamos frontend con React, TypeScript y Node.js")
        assert any("react" in s.lower() for s in stacks)
        assert any("typescript" in s.lower() for s in stacks)
        assert any("node" in s.lower() for s in stacks)

    def test_detects_devops_stack(self):
        stacks = _extract_tech_stack("Experiencia con Docker, Kubernetes y AWS requerida")
        assert any("docker" in s.lower() for s in stacks)
        assert any("kubernetes" in s.lower() for s in stacks)
        assert any("aws" in s.lower() for s in stacks)

    def test_detects_databases(self):
        stacks = _extract_tech_stack("Conocimiento de PostgreSQL, Redis y MongoDB")
        assert any("postgresql" in s.lower() for s in stacks)
        assert any("redis" in s.lower() for s in stacks)
        assert any("mongodb" in s.lower() for s in stacks)

    def test_returns_empty_for_no_tech(self):
        stacks = _extract_tech_stack("Buscamos persona con buena actitud y ganas de aprender.")
        assert stacks == []

    def test_returns_empty_for_empty_input(self):
        assert _extract_tech_stack("") == []
        assert _extract_tech_stack(None) == []

    def test_case_insensitive(self):
        stacks = _extract_tech_stack("Experiencia con PYTHON, docker y FASTAPI")
        assert any("python" in s.lower() for s in stacks)
        assert any("docker" in s.lower() for s in stacks)
        assert any("fastapi" in s.lower() for s in stacks)

    def test_detects_fastapi(self):
        stacks = _extract_tech_stack("API REST con FastAPI o Flask")
        assert any("fastapi" in s.lower() for s in stacks)
        assert any("flask" in s.lower() for s in stacks)


class TestJobScannerStorage:
    """Tests de persistencia de resultados."""

    @pytest.fixture
    def tmp_scan_file(self, tmp_path):
        f = tmp_path / "job_scan_results.json"
        f.write_text("[]", encoding="utf-8")
        with patch("src.job_scanner.SCAN_RESULTS_FILE", f):
            yield f

    def test_load_empty(self, tmp_scan_file):
        results = JobScanner._load_results()
        assert results == []

    def test_save_and_load(self, tmp_scan_file):
        jobs = [
            {
                "title": "Python Developer",
                "company": "Acme Corp",
                "location": "Madrid",
                "url": "https://linkedin.com/jobs/view/123",
                "detected_stack": ["Python", "Django"],
                "scanned_at": datetime.now().isoformat(),
                "search_query": "Python"
            }
        ]
        JobScanner._save_results(jobs)
        loaded = JobScanner._load_results()
        assert len(loaded) == 1
        assert loaded[0]["company"] == "Acme Corp"

    def test_get_target_companies(self, tmp_scan_file):
        jobs = [
            {"company": "Acme Corp", "title": "Dev", "detected_stack": [], "scanned_at": "2026-10-29T10:00:00"},
            {"company": "Beta Inc", "title": "Dev", "detected_stack": [], "scanned_at": "2026-10-29T10:00:00"},
            {"company": "Acme Corp", "title": "SRE", "detected_stack": [], "scanned_at": "2026-10-29T11:00:00"},
        ]
        JobScanner._save_results(jobs)
        companies = JobScanner.get_target_companies()
        assert "Acme Corp" in companies
        assert "Beta Inc" in companies
        # Debe deduplicar
        assert len([c for c in companies if c == "Acme Corp"]) == 1

    def test_get_demanded_skills(self, tmp_scan_file):
        today = date.today().isoformat()
        jobs = [
            {"detected_stack": ["Python", "Docker"], "scanned_at": f"{today}T10:00:00"},
            {"detected_stack": ["Python", "FastAPI"], "scanned_at": f"{today}T10:00:00"},
            {"detected_stack": ["Docker", "AWS"], "scanned_at": f"{today}T10:00:00"},
        ]
        JobScanner._save_results(jobs)
        skills = JobScanner.get_demanded_skills()
        assert skills["python"] == 2
        assert skills["docker"] == 2
        assert skills["fastapi"] == 1

    def test_format_summary_empty(self):
        summary = JobScanner.format_summary([])
        assert "No se encontraron" in summary

    def test_format_summary_with_jobs(self, tmp_scan_file):
        today = date.today().isoformat()
        jobs = [
            {
                "title": "Backend Developer",
                "company": "Acme Corp",
                "location": "Madrid",
                "url": "https://linkedin.com/jobs/view/123",
                "detected_stack": ["Python", "FastAPI"],
                "scanned_at": f"{today}T10:00:00",
                "search_query": "Python"
            }
        ]
        JobScanner._save_results(jobs)
        summary = JobScanner.format_summary(jobs)
        assert "Backend Developer" in summary
        assert "Acme Corp" in summary
        assert "1 ofertas" in summary
