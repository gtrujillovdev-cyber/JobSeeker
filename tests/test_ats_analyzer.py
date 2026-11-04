"""
Tests unitarios para el motor ATSAnalyzer (HR Tech).
"""

import pytest
from src.ats_analyzer import ATSAnalyzer, TECH_TAXONOMY, CV_PROFILES_METADATA


def test_taxonomy_extraction():
    title = "Python Backend Developer with FastAPI & Docker"
    desc = "Buscamos un desarrollador con experiencia en Linux, PostgreSQL, Git y metodologías Scrum."
    
    extracted = ATSAnalyzer.extract_job_keywords(title, desc)
    assert "languages" in extracted
    assert "python" in extracted["languages"]
    assert "fastapi" in extracted.get("frameworks_backend", [])
    assert "docker" in extracted.get("devops_cloud_sys", [])
    assert "git" in extracted.get("methodologies_tools", [])


def test_ats_match_qa():
    title = "Middle QA Automation Engineer (Playwright & Python)"
    desc = "Automatización de pruebas E2E, testing funcional con Playwright y Pytest."
    
    analysis = ATSAnalyzer.analyze_match(title, desc)
    assert analysis["best_cv"] == "GTV_CV_ES2026.pdf"
    assert analysis["best_profile_key"] == "qa_sdet"
    assert analysis["ats_score"] >= 80
    assert "ALTO MATCH" in analysis["tier_badge"]
    assert "playwright" in analysis["matched_keywords"]


def test_ats_match_ciberseguridad():
    title = "Técnico Junior Ciberseguridad OT / Sistemas"
    desc = "Administración de sistemas Linux, seguridad perimetral, ISO 27001, redes TCP/IP."
    
    analysis = ATSAnalyzer.analyze_match(title, desc)
    assert analysis["best_cv"] == "GTV_CV_Sys_ES2026.pdf"
    assert analysis["best_profile_key"] == "sys_cyber"
    assert analysis["ats_score"] >= 85
    assert "linux" in analysis["matched_keywords"]
    assert "ciberseguridad" in analysis["matched_keywords"]


def test_ats_match_mobile_dam():
    title = "Desarrollador Multiplataforma DAM / SwiftUI"
    desc = "Desarrollo de apps móviles con Swift, SwiftUI y JavaScript/TypeScript."
    
    analysis = ATSAnalyzer.analyze_match(title, desc)
    assert analysis["best_cv"] == "GTV_CV_iOS_ES2026.pdf"
    assert analysis["best_profile_key"] == "ios_dam"
    assert analysis["ats_score"] >= 75


def test_ats_format_hr_report():
    analysis = ATSAnalyzer.analyze_match("Python Backend Engineer", "Desarrollo con FastAPI y bases de datos")
    report = ATSAnalyzer.format_hr_report(analysis, "Python Backend Engineer", "OpenAI Partner")
    assert "EVALUACIÓN ATS DE RECURSOS HUMANOS" in report
    assert "Score ATS:" in report
    assert "CV Oficial Seleccionado:" in report
