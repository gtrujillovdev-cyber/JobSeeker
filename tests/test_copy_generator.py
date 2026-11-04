"""Tests para CopyGenerator - generacion de posts para LinkedIn."""
import pytest
from unittest.mock import patch
from src.copy_generator import CopyGenerator


# Datos de prueba reutilizables
SAMPLE_PARAMS = {
    "project_name": "TestProject",
    "headline_title": "Optimizacion de latencia en pipelines de datos",
    "problem_context": "El sistema sufria picos de latencia superiores a 500ms en horas punta.",
    "implementation_details": "Se implemento un buffer circular con flush periodico y compresion LZ4.",
    "technical_findings": "El 42% de los picos se debian a contention en el lock del escritor.",
    "objectives_achieved": [
        "Reduccion de latencia p99 de 500ms a 45ms",
        "Throughput sostenido de 120k eventos/seg"
    ],
    "tech_stack": ["Python", "Redis", "Docker", "FastAPI"]
}


class TestCopyGeneratorFallback:
    """Tests del template de respaldo (sin Gemini)."""

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_generates_non_empty_post(self):
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert len(post) > 100, "El post debe tener contenido sustancial"

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_includes_headline(self):
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert SAMPLE_PARAMS["headline_title"] in post

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_includes_problem_context(self):
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert SAMPLE_PARAMS["problem_context"] in post

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_includes_objectives(self):
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        for obj in SAMPLE_PARAMS["objectives_achieved"]:
            assert obj in post

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_includes_hashtags(self):
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert "#Python" in post
        assert "#SoftwareEngineering" in post

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_includes_engagement_question(self):
        """El post debe incluir una pregunta abierta para generar interaccion."""
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert "?" in post, "El post debe contener una pregunta abierta"

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_no_adjunto_captura_mention(self):
        """El post NO debe mencionar 'adjunto captura' (LinkedIn muestra la imagen sola)."""
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        assert "adjunto" not in post.lower()
        assert "captura" not in post.lower()

    @patch("src.copy_generator.GEMINI_API_KEY", "")
    def test_stack_in_question(self):
        """La pregunta de engagement debe incluir parte del stack."""
        post = CopyGenerator.generate_post(**SAMPLE_PARAMS)
        # La pregunta del fallback incluye stack_str
        assert "Python" in post or "Redis" in post

    def test_anti_apelotonamiento_blank_line_between_bullets_and_max_length(self):
        """Directriz Anti-Apelotonamiento: nunca permitir viñetas pegadas ni viñetas de >125 chars."""
        from src.dev_diary import DevDiaryGenerator
        crowded_input = (
            "Diario de Desarrollo #1 — Servidor local\n\n"
            "Qué he implementado:\n"
            "  • Interfaz y flujo en vivo: panel de control y estado operativo del servicio.\n"
            "  • Núcleo en stream_manager.py: Implementé autodescubrimiento de dispositivos Google Cast en la LAN, "
            "un chequeo de salud previo para verificar que el socket responde antes de iniciar la transmisión, "
            "un mando virtual web y soporte tanto en Docker como en paquete DMG para macOS.\n"
            "  • Arquitectura pensada para funcionar en red local sin configuraciones manuales.\n"
            "Stack: Python · Docker\n"
            "#Python #Docker"
        )
        formatted = DevDiaryGenerator._format_clean_post(crowded_input)
        lines = formatted.splitlines()
        bullet_indices = [i for i, l in enumerate(lines) if l.startswith("• ")]
        assert len(bullet_indices) == 3
        # Verificar que entre cada viñeta hay al menos 1 línea en blanco (diferencia de índice >= 2)
        for idx_a, idx_b in zip(bullet_indices, bullet_indices[1:]):
            assert idx_b - idx_a >= 2, "Las viñetas no pueden estar en líneas consecutivas (apelotonadas)"
        # Verificar que ninguna viñeta supere los 125 caracteres
        for idx in bullet_indices:
            assert len(lines[idx]) <= 125, f"Viñeta demasiado larga ({len(lines[idx])} chars): {lines[idx]}"
