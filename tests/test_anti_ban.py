"""Tests para AntiBanValidator - control de limites de publicacion y engagement."""
import json
import pytest
from unittest.mock import patch
from pathlib import Path
from src.anti_ban import AntiBanValidator


@pytest.fixture
def tmp_processed_file(tmp_path):
    """Crea un archivo temporal para historial de publicaciones."""
    f = tmp_path / "published_history.json"
    f.write_text("[]", encoding="utf-8")
    with patch("src.anti_ban.PROCESSED_FILE", f):
        yield f


@pytest.fixture
def tmp_engagement_file(tmp_path):
    """Crea un archivo temporal para historial de engagement."""
    f = tmp_path / "engagement_history.json"
    f.write_text("[]", encoding="utf-8")
    with patch("src.anti_ban.ENGAGEMENT_FILE", f):
        yield f


class TestPublicationLimits:

    def test_allows_first_post(self, tmp_processed_file):
        assert AntiBanValidator.check_daily_limit() is True

    def test_blocks_when_limit_reached(self, tmp_processed_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "status": "success", "project_name": f"test{i}"}
            for i in range(5)
        ]
        tmp_processed_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_POSTS", 2):
            assert AntiBanValidator.check_daily_limit() is False

    def test_ignores_failed_posts(self, tmp_processed_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "status": "failed", "project_name": "test1"},
            {"date": today, "status": "failed", "project_name": "test2"},
        ]
        tmp_processed_file.write_text(json.dumps(records), encoding="utf-8")
        assert AntiBanValidator.check_daily_limit() is True

    def test_record_publication(self, tmp_processed_file):
        AntiBanValidator.record_publication("TestProject", "Texto de prueba largo", "/img.png", status="success")
        records = json.loads(tmp_processed_file.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["project_name"] == "TestProject"
        assert records[0]["status"] == "success"
        assert len(records[0]["caption_preview"]) <= 100
        assert "content_hash" in records[0]


class TestNoDuplicatePublications:

    def test_blocks_identical_text_even_with_different_entry_number(self, tmp_processed_file):
        text_v1 = "Diario #3: Evitar falsos positivos entre Java y JavaScript\n\nCuerpo del post técnico completo."
        AntiBanValidator.record_publication("JobSeeker", text_v1, "/img.png", status="success", pill_id="jobseeker_ats_weighting")

        text_v2 = "Diario #4: Evitar falsos positivos entre Java y JavaScript\n\nCuerpo del post técnico completo."
        is_dup, reason = AntiBanValidator.is_duplicate_publication(text_v2, pill_id="otro_id")
        assert is_dup is True
        assert reason != ""

    def test_blocks_same_pill_id(self, tmp_processed_file):
        AntiBanValidator.record_publication("JobSeeker", "Diario #3: Titulo A\n\nContenido A", "/img.png", status="success", pill_id="jobseeker_ats_weighting")
        is_dup, reason = AntiBanValidator.is_duplicate_publication("Diario #7: Titulo Completamente Distinto\n\nOtro cuerpo", pill_id="jobseeker_ats_weighting")
        assert is_dup is True
        assert "jobseeker_ats_weighting" in reason

    def test_blocks_duplicate_in_dev_diary_history(self, tmp_processed_file):
        diary_hist = tmp_processed_file.parent / "dev_diary_history.json"
        diary_hist.write_text(json.dumps([{
            "entry_number": 2,
            "pill_id": "interactivecv_data_driven_ui",
            "post_preview": "Diario #2: Desacoplar los datos del DOM en InteractiveCV",
            "status": "published"
        }]), encoding="utf-8")

        is_dup, _ = AntiBanValidator.is_duplicate_publication("Diario #9: Otro titulo\n\nTexto", pill_id="interactivecv_data_driven_ui")
        assert is_dup is True

    def test_allows_brand_new_pill_and_content(self, tmp_processed_file):
        AntiBanValidator.record_publication("JobSeeker", "Diario #3: Post antiguo uno\n\nDetalle antiguo uno", "/img.png", status="success", pill_id="pill_uno")
        is_dup, _ = AntiBanValidator.is_duplicate_publication("Diario #4: Reconexion WebSockets en AsyncIO\n\nContenido nuevo unico", pill_id="pill_dos")
        assert is_dup is False

    def test_publisher_aborts_on_duplicate(self, tmp_processed_file):
        from src.linkedin_publisher import LinkedInPublisher
        AntiBanValidator.record_publication("JobSeeker", "Diario #3: Post ya publicado\n\nCuerpo repetido", "/img.png", status="success", pill_id="pill_dup")
        pub = LinkedInPublisher(dry_run=False)
        ok = pub.publish_post("Diario #4: Post ya publicado\n\nCuerpo repetido", project_name="JobSeeker", pill_id="pill_dup")
        assert ok is False
        assert pub.last_error and "duplicada" in pub.last_error.lower()

    def test_reviewer_blocks_double_publish_on_already_published_draft(self, tmp_path, tmp_processed_file):
        from src.telegram_reviewer import TelegramReviewer
        drafts_file = tmp_path / "pending_drafts.json"
        drafts_file.write_text(json.dumps({
            "abc": {"draft_id": "abc", "project_name": "JobSeeker", "text": "Post ya subido", "status": "published"}
        }), encoding="utf-8")
        with patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts_file):
            assert TelegramReviewer.publish_approved_draft("abc") is False

    def test_dev_diary_never_repeats_exhausted_curated_pills(self, tmp_processed_file):
        from src.dev_diary import DevDiaryGenerator, EDUCATIONAL_PILLS_BY_PROJECT
        all_js_pills = EDUCATIONAL_PILLS_BY_PROJECT["JobSeeker"]
        history = [{"dir_name": "JobSeeker", "pill_id": p["pill_id"], "status": "published"} for p in all_js_pills]
        inspected = {
            "dir_name": "JobSeeker",
            "source_file": "src/ats_analyzer.py",
            "tech_stack": ["Python"],
            "repo_inventory": ["src/new_mod.py: run_unique_flow"]
        }
        selected = DevDiaryGenerator._select_educational_pill(inspected, history)
        assert selected.get("exhausted") is False
        assert selected["pill_id"] not in {p["pill_id"] for p in all_js_pills}
        assert "run_unique_flow" in selected["pill_id"]

    def test_blocks_duplicate_against_active_pending_or_scheduled_draft(self, tmp_processed_file):
        drafts_file = tmp_processed_file.parent / "pending_drafts.json"
        drafts_file.write_text(json.dumps({
            "d_sched": {
                "draft_id": "d_sched",
                "pill_id": "jobseeker_ats_weighting",
                "text": "Diario #3: Ponderación ATS en JobSeeker\n\nCuerpo unico",
                "status": "scheduled",
                "scheduled_for": "2026-11-12T10:00:00"
            }
        }), encoding="utf-8")

        # En generación (include_active_drafts=True) queda bloqueado por pill_id y contenido
        is_dup, reason = AntiBanValidator.is_duplicate_publication(
            "Diario #4: Otro titulo distinto\n\nTexto distinto",
            pill_id="jobseeker_ats_weighting",
            include_active_drafts=True
        )
        assert is_dup is True
        assert "scheduled" in reason

        # Y al publicar ese mismo borrador (include_active_drafts=False) sí permite continuar si no se ha publicado aún
        is_dup_pub, _ = AntiBanValidator.is_duplicate_publication(
            "Diario #3: Ponderación ATS en JobSeeker\n\nCuerpo unico",
            pill_id="jobseeker_ats_weighting",
            include_active_drafts=False
        )
        assert is_dup_pub is False

    def test_prepare_daily_diary_draft_aborts_if_scheduled_or_pending_exists(self, tmp_path):
        from src.dev_diary import DevDiaryGenerator
        drafts_file = tmp_path / "pending_drafts.json"
        drafts_file.write_text(json.dumps({
            "sched10": {
                "draft_id": "sched10",
                "pill_id": "jobseeker_ats_weighting",
                "project_name": "Diario #3 · JobSeeker",
                "text": "Texto programado",
                "status": "scheduled",
                "scheduled_for": "2026-11-12T10:00:00"
            }
        }), encoding="utf-8")

        with patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts_file):
            assert DevDiaryGenerator.prepare_daily_diary_draft(wait_approval=False) is None

        drafts_file.write_text(json.dumps({
            "pend1": {
                "draft_id": "pend1",
                "pill_id": "jobseeker_ats_weighting",
                "project_name": "Diario #3 · JobSeeker",
                "text": "Texto pendiente",
                "status": "pending"
            }
        }), encoding="utf-8")

        with patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts_file):
            assert DevDiaryGenerator.prepare_daily_diary_draft(wait_approval=False) is None

    def test_expire_stale_drafts_marks_old_pending_as_expired(self, tmp_path):
        from src.telegram_reviewer import expire_stale_drafts
        drafts_file = tmp_path / "pending_drafts.json"
        drafts_file.write_text(json.dumps({
            "old1": {
                "draft_id": "old1",
                "pill_id": "jobseeker_ats_weighting",
                "status": "pending",
                "created_at": "2020-01-01T10:00:00"
            }
        }), encoding="utf-8")
        with patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts_file):
            drafts = expire_stale_drafts(max_age_hours=24.0)
        assert drafts["old1"]["status"] == "expired"
        saved = json.loads(drafts_file.read_text(encoding="utf-8"))
        assert saved["old1"]["status"] == "expired"

    def test_rejected_and_regenerated_pills_are_never_reproposed(self, tmp_processed_file):
        from src.dev_diary import DevDiaryGenerator, EDUCATIONAL_PILLS_BY_PROJECT
        first_pill = EDUCATIONAL_PILLS_BY_PROJECT["JobSeeker"][0]["pill_id"]
        second_pill = EDUCATIONAL_PILLS_BY_PROJECT["JobSeeker"][1]["pill_id"]
        history = [
            {"dir_name": "JobSeeker", "pill_id": first_pill, "status": "rejected"},
            {"dir_name": "JobSeeker", "pill_id": second_pill, "status": "regenerated"},
        ]
        inspected = {
            "dir_name": "JobSeeker",
            "source_file": "src/ats_analyzer.py",
            "tech_stack": ["Python"],
            "repo_inventory": []
        }
        selected = DevDiaryGenerator._select_educational_pill(inspected, history)
        assert selected.get("exhausted") is False
        assert selected["pill_id"] not in {first_pill, second_pill}

    def test_resolve_repo_path_finds_reorganized_projects(self):
        from src.dev_diary import DevDiaryGenerator
        for name in ("JobSeeker", "GTA6Channel", "GaTDSEQ", "mando-tv", "GaBookAutoDownloader"):
            resolved = DevDiaryGenerator._resolve_repo_path(name)
            assert resolved.exists(), f"No se encontró el repositorio '{name}' en {resolved}"

    def test_regenerate_falls_back_to_next_project_when_same_exhausted(self, tmp_path, tmp_processed_file):
        from src.dev_diary import DevDiaryGenerator, EDUCATIONAL_PILLS_BY_PROJECT
        drafts_file = tmp_path / "pending_drafts.json"
        hist_file = tmp_path / "dev_diary_history.json"
        only_pill = EDUCATIONAL_PILLS_BY_PROJECT["InteractiveCV"][0]["pill_id"]
        drafts_file.write_text(json.dumps({
            "d_icv": {
                "draft_id": "d_icv",
                "project_name": "Diario #3 · InteractiveCV",
                "pill_id": only_pill,
                "status": "pending",
                "created_at": "2026-11-16T10:00:00",
            }
        }), encoding="utf-8")
        hist_file.write_text("[]", encoding="utf-8")

        fake_rec = {"draft_id": "new123", "dir_name": "GTA6Channel"}
        calls = []

        def _fake_prepare(**kwargs):
            calls.append(kwargs.get("project_filter"))
            return None if kwargs.get("project_filter") else fake_rec

        with patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts_file), \
             patch("src.dev_diary.DEV_DIARY_HISTORY_FILE", hist_file), \
             patch.object(DevDiaryGenerator, "prepare_daily_diary_draft", side_effect=_fake_prepare):
            new_id = DevDiaryGenerator.regenerate_draft_by_id("d_icv")
        assert new_id == "new123"
        assert calls == ["InteractiveCV", None]
        saved_hist = json.loads(hist_file.read_text(encoding="utf-8"))
        assert saved_hist[0]["status"] == "regenerated"

    def test_format_clean_post_removes_orphan_empty_bullets(self):
        from src.dev_diary import DevDiaryGenerator
        dirty = "Diario #4: Titulo\n\n• Punto uno.\n\n•\n\n•   \n\n• Punto dos.\n\n#Python"
        cleaned = DevDiaryGenerator._format_clean_post(dirty)
        lines = [l for l in cleaned.splitlines() if l.strip()]
        assert "•" not in lines
        assert cleaned.count("• ") == 2

    def test_preferred_topic_track_balances_programming_and_systems(self):
        from src.dev_diary import DevDiaryGenerator
        assert DevDiaryGenerator._preferred_topic_track([]) == "programacion"
        only_prog = [{"topic_track": "programacion"} for _ in range(4)]
        assert DevDiaryGenerator._preferred_topic_track(only_prog) == "sistemas"
        recent_sys = [
            {"topic_track": "programacion"},
            {"topic_track": "programacion"},
            {"topic_track": "sistemas"},
            {"topic_track": "programacion"},
        ]
        assert DevDiaryGenerator._preferred_topic_track(recent_sys) == "programacion"

    def test_resolve_repo_path_and_vscode_explorer_nested_tree(self):
        from src.dev_diary import DevDiaryGenerator
        from src.project_capturer import ProjectCapturer
        devops_repo = DevDiaryGenerator._resolve_repo_path("DevOps")
        assert devops_repo.exists()
        tabs_html, explorer_html, branch, _ = ProjectCapturer._build_explorer_and_tabs(
            devops_repo, "collector/monitor.py", "DevOps"
        )
        assert "monitor.py" in tabs_html
        assert "collector" in explorer_html and "tree-selected" in explorer_html
        assert isinstance(branch, str) and len(branch) > 0

    def test_multiline_docstring_highlights_all_lines_as_string(self):
        from src.project_capturer import ProjectCapturer
        lines = [
            'def foo():',
            '    """',
            '    1. Texto descriptivo if else def return',
            '    2. Otro texto',
            '    """',
            '    return True',
        ]
        rendered = ProjectCapturer._highlight_with_pygments(lines, "demo.py")
        # La línea interior del docstring debe ir coloreada como string (#ce9178), no keywords (#569cd6/#c586c0)
        assert "#ce9178" in rendered[2]
        assert "#c586c0" not in rendered[2]
        assert "#c586c0" in rendered[5]

    def test_pick_next_diary_prefers_tier1_before_tier2(self, tmp_processed_file):
        from src.dev_diary import DevDiaryGenerator
        with patch.object(DevDiaryGenerator, "_load_history", return_value=[]):
            picked = DevDiaryGenerator.pick_next_diary_entry()
        assert picked.get("focus_tier", 1) == 1
        assert picked.get("topic_track") == "programacion"


class TestEngagementLimits:

    def test_allows_first_engagement(self, tmp_engagement_file):
        assert AntiBanValidator.check_engagement_limit("comment") is True
        assert AntiBanValidator.check_engagement_limit("connection") is True
        assert AntiBanValidator.check_engagement_limit("reaction") is True

    def test_blocks_comments_at_limit(self, tmp_engagement_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "comment", "status": "success", "target": f"co{i}"}
            for i in range(10)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_COMMENTS", 8):
            assert AntiBanValidator.check_engagement_limit("comment") is False

    def test_blocks_connections_at_limit(self, tmp_engagement_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "connection", "status": "success", "target": f"co{i}"}
            for i in range(6)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_CONNECTIONS", 5):
            assert AntiBanValidator.check_engagement_limit("connection") is False

    def test_different_actions_independent(self, tmp_engagement_file):
        """El limite de comments no afecta al de connections."""
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "comment", "status": "success", "target": f"co{i}"}
            for i in range(10)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_COMMENTS", 8):
            assert AntiBanValidator.check_engagement_limit("comment") is False
            assert AntiBanValidator.check_engagement_limit("connection") is True

    def test_record_engagement(self, tmp_engagement_file):
        AntiBanValidator.record_engagement("comment", "Acme Corp", "Buen enfoque tecnico")
        records = json.loads(tmp_engagement_file.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["action"] == "comment"
        assert records[0]["target"] == "Acme Corp"
        assert records[0]["status"] == "success"

    def test_today_engagement_summary(self, tmp_engagement_file):
        AntiBanValidator.record_engagement("comment", "Acme")
        AntiBanValidator.record_engagement("comment", "Beta Inc")
        AntiBanValidator.record_engagement("connection", "Gamma")
        summary = AntiBanValidator.get_today_engagement_summary()
        assert summary["comment"] == 2
        assert summary["connection"] == 1

    def test_unknown_action_always_allowed(self, tmp_engagement_file):
        """Acciones no definidas en _ENGAGEMENT_LIMITS pasan siempre."""
        assert AntiBanValidator.check_engagement_limit("unknown_action") is True
