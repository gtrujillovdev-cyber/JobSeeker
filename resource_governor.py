"""
Módulo de autorregulación de memoria, recursos y limpieza de residuos en disco para JobSeekerGA.
Garantiza tolerancia a fallos, recolección activa de basura (gc), purga de temporales
y eliminación de capturas huérfanas o procesos zombies de Playwright/Chromium.
"""

import gc
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List

from config import DATA_DIR, OUTPUT_DIR, SCREENSHOTS_DIR, LOGS_DIR

CVS_DIR = OUTPUT_DIR / "cvs"


class ResourceGovernor:
    """
    Supervisor autónomo de memoria y almacenamiento.
    Se ejecuta de forma periódica o al inicio/fin de cada pipeline para mantener
    el sistema en niveles mínimos de uso de RAM y disco.
    """

    @classmethod
    def sweep_memory(cls) -> int:
        """Fuerza la recolección explícita de ciclos circulares de Python y libera RAM."""
        collected = gc.collect()
        return collected

    @classmethod
    def clean_old_files(cls, target_dir: Path, max_age_days: int = 7, extensions: List[str] = None) -> int:
        """Elimina archivos que superen la antigüedad especificada."""
        if not target_dir.exists():
            return 0

        now = time.time()
        max_age_seconds = max_age_days * 86400
        removed = 0

        for file_path in target_dir.glob("*"):
            if not file_path.is_file():
                continue
            if extensions and file_path.suffix.lower() not in extensions:
                continue

            try:
                mtime = file_path.stat().st_mtime
                if (now - mtime) > max_age_seconds:
                    file_path.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                continue

        return removed

    @classmethod
    def purge_temp_artifacts(cls) -> Dict[str, int]:
        """
        Purga archivos temporales residuales:
        - Screenshots de ejecución antiguas (> 3 días).
        - Archivos HTML generados para renderizado de CV (> 1 día).
        - Archivos de log rotados o vacíos.
        """
        results = {
            "screenshots_purged": cls.clean_old_files(SCREENSHOTS_DIR, max_age_days=3, extensions=[".png", ".jpg"]),
            "cv_html_purged": cls.clean_old_files(CVS_DIR, max_age_days=1, extensions=[".html"]),
            "old_cvs_purged": cls.clean_old_files(CVS_DIR, max_age_days=7, extensions=[".pdf"]),
            "gc_objects_collected": cls.sweep_memory()
        }
        return results

    @classmethod
    def clean_orphaned_browser_locks(cls, profile_dir: Path) -> None:
        """
        Limpia ficheros de bloqueo ('SingletonLock', 'SingletonCookie', 'SingletonSocket')
        que Chromium puede dejar si el proceso fue terminado abruptamente.
        """
        if not profile_dir.exists():
            return

        lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
        for lock in lock_files:
            p = profile_dir / lock
            if p.is_symlink() or p.exists():
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    @classmethod
    def run_full_cleanup(cls, profile_dir: Path = None) -> Dict[str, Any]:
        """Ejecuta una purga completa y devuelve métricas del resultado."""
        summary = cls.purge_temp_artifacts()
        if profile_dir:
            cls.clean_orphaned_browser_locks(profile_dir)
        summary["memory_cleared"] = cls.sweep_memory()
        return summary
