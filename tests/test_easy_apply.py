"""Tests para EasyApplyEngine y el selector/generador de CV adaptado."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.easy_apply import EasyApplyEngine, CV_PROFILES


class TestSelectBestCvProfile:

    def test_selects_qa_sdet_for_qa_testing_jobs(self):
        job = {
            "title": "QA Automation Engineer Junior (Playwright / Python)",
            "company": "SDOS",
            "description_preview": "Buscamos perfil QA tester para pruebas E2E con Playwright, Pytest y Selenium.",
            "detected_stack": ["Python", "Playwright"]
        }
        res = EasyApplyEngine.select_best_cv_profile(job)
        assert res["cv_profile_key"] == "qa_sdet"
        assert res["cv_score"] > 0

    def test_selects_sys_cyber_for_linux_security_jobs(self):
        job = {
            "title": "Técnico de Sistemas Linux y Ciberseguridad Junior",
            "company": "Ayesa Digital",
            "description_preview": "Administración de servidores Linux, redes, firewall, SIEM, Docker y soporte IT.",
            "detected_stack": ["Linux", "Docker", "Bash"]
        }
        res = EasyApplyEngine.select_best_cv_profile(job)
        assert res["cv_profile_key"] == "sys_cyber"
        assert "Sistemas Linux" in res["cv_label"]

    def test_selects_ai_python_for_backend_ai_jobs(self):
        job = {
            "title": "Python Backend & AI Developer",
            "company": "Babel",
            "description_preview": "Desarrollo de APIs con FastAPI, integración de LLMs, RAG y automatización en Python.",
            "detected_stack": ["Python", "Fastapi", "SQL"]
        }
        res = EasyApplyEngine.select_best_cv_profile(job)
        assert res["cv_profile_key"] == "ai_python"
        assert "IA" in res["cv_linkedin_name"] or "AI" in res["cv_linkedin_name"]

    def test_selects_ios_dam_for_mobile_multiplatform_jobs(self):
        job = {
            "title": "Desarrollador Junior DAM / iOS SwiftUI",
            "company": "Tier1 Technology",
            "description_preview": "Graduado DAM para desarrollo de aplicaciones móviles iOS con Swift, SwiftUI y frontend web.",
            "detected_stack": ["Swift", "Javascript"]
        }
        res = EasyApplyEngine.select_best_cv_profile(job)
        assert res["cv_profile_key"] == "ios_dam"
        assert "iOS" in res["cv_linkedin_name"]


class TestExistingOfficialCvSelection:

    def test_reutiliza_cv_existente(self, tmp_path):
        with patch("src.easy_apply.ASSETS_CVS_DIR", tmp_path):
            sample_pdf = tmp_path / "GTV_CV_Sys_ES2026.pdf"
            sample_pdf.write_bytes(b"%PDF-1.4 dummy")
            job = {
                "title": "Ingeniero Junior Ciberseguridad & Linux",
                "company": "Admiral Europe Tech",
                "location": "Sevilla",
                "detected_stack": ["Linux", "Python", "Docker"]
            }
            pdf_path = EasyApplyEngine.get_existing_official_cv(job)
            assert pdf_path.exists()
            assert pdf_path.name == "GTV_CV_Sys_ES2026.pdf"
            assert job["cv_pdf_path"] == str(pdf_path)


class TestAnswerAdditionalQuestions:

    @patch("src.easy_apply.GEMINI_API_KEY", "")
    def test_numeric_questions(self):
        job = {"title": "Python Dev", "company": "Acme"}
        assert EasyApplyEngine._answer_additional_question("¿Cuántos años de experiencia tienes con Python?", job, is_numeric=True) == "2"
        assert EasyApplyEngine._answer_additional_question("Expectativa salarial bruta anual", job, is_numeric=True) == "20000"

    @patch("src.easy_apply.GEMINI_API_KEY", "")
    def test_text_questions(self):
        job = {"title": "Python Dev", "company": "Acme"}
        assert "Sevilla" in EasyApplyEngine._answer_additional_question("¿En qué ciudad resides actualmente?", job)
        assert "Inmediata" in EasyApplyEngine._answer_additional_question("Disponibilidad de incorporación", job)
        assert "B2" in EasyApplyEngine._answer_additional_question("Nivel de inglés", job)


class TestTelegramFormattingAndHistory:

    def test_builds_telegram_message_with_adapted_cv_and_links(self):
        jobs = [
            {
                "title": "Python QA Engineer",
                "company": "SDOS",
                "location": "Sevilla",
                "url": "https://www.linkedin.com/jobs/view/123456/",
                "cv_label": "QA Automation, SDET & Testing con Playwright/Python",
                "cv_pdf_path": "/tmp/GTV_CV_2026_qa_sdet_SDOS.pdf",
                "cv_reason": "Encaja por keywords (qa, python)",
                "enabled": True
            }
        ]
        text, kb = EasyApplyEngine._build_telegram_message_and_keyboard(jobs)
        assert "Python QA Engineer" in text
        assert "QA Automation" in text
        assert "https://www.linkedin.com/jobs/view/123456/" in text
        assert len(kb["inline_keyboard"]) == 2

    def test_records_application_history(self, tmp_path):
        hist_file = tmp_path / "easy_apply_history.json"
        with patch("src.easy_apply.EASY_APPLY_HISTORY_FILE", hist_file):
            job = {
                "title": "Junior Linux Admin",
                "company": "Guadaltel",
                "url": "https://www.linkedin.com/jobs/view/999/",
                "cv_profile_key": "sys_cyber",
                "cv_label": "Sistemas Linux"
            }
            EasyApplyEngine.record_application(job, status="success")
            applied = EasyApplyEngine.get_already_applied_urls()
            assert "https://www.linkedin.com/jobs/view/999" in applied
