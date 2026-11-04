"""Tests para ResourceGovernor - autorregulación de memoria y purga de temporales."""
import time
from pathlib import Path
from src.resource_governor import ResourceGovernor


class TestResourceGovernor:

    def test_sweep_memory_returns_integer(self):
        collected = ResourceGovernor.sweep_memory()
        assert isinstance(collected, int)
        assert collected >= 0

    def test_clean_old_files_deletes_expired(self, tmp_path):
        old_file = tmp_path / "old.png"
        old_file.write_text("dummy")
        # Forzar fecha de modificación a hace 10 días
        ten_days_ago = time.time() - (10 * 86400)
        import os
        os.utime(old_file, (ten_days_ago, ten_days_ago))

        recent_file = tmp_path / "recent.png"
        recent_file.write_text("recent")

        deleted = ResourceGovernor.clean_old_files(tmp_path, max_age_days=3, extensions=[".png"])
        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_clean_orphaned_browser_locks(self, tmp_path):
        lock_file = tmp_path / "SingletonLock"
        lock_file.write_text("lock_content")
        assert lock_file.exists()

        ResourceGovernor.clean_orphaned_browser_locks(tmp_path)
        assert not lock_file.exists()

    def test_run_full_cleanup_returns_metrics(self, tmp_path):
        metrics = ResourceGovernor.run_full_cleanup(profile_dir=tmp_path)
        assert "screenshots_purged" in metrics
        assert "cv_html_purged" in metrics
        assert "memory_cleared" in metrics
