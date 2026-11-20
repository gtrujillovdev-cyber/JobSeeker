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


def test_ats_match_unified_2027():
    title = "Desarrollador Junior Python, Linux & Testing"
    desc = "Buscamos desarrollador con Python, Docker, Linux y pruebas automáticas con Pytest/Playwright."
    
    analysis = ATSAnalyzer.analyze_match(title, desc)
    assert analysis["best_cv"] == "GTVCV_2027.pdf"
    assert analysis["best_profile_key"] == "unified_2027"
    assert analysis["ats_score"] >= 80
    assert "ALTO MATCH" in analysis["tier_badge"]
    assert "python" in analysis["matched_keywords"]


def test_ats_format_hr_report():
    analysis = ATSAnalyzer.analyze_match("Python Backend Engineer", "Desarrollo con FastAPI y bases de datos")
    report = ATSAnalyzer.format_hr_report(analysis, "Python Backend Engineer", "OpenAI Partner")
    assert "EVALUACIÓN ATS DE RECURSOS HUMANOS" in report
    assert "Score ATS:" in report
    assert "CV Oficial Seleccionado:" in report
