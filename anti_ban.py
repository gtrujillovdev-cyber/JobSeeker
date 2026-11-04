import json
from datetime import date, datetime
from typing import Dict, Any, List
from config import (
    PROCESSED_FILE, MAX_DAILY_POSTS,
    ENGAGEMENT_FILE, MAX_DAILY_CONNECTIONS, MAX_DAILY_COMMENTS, MAX_DAILY_REACTIONS
)

class AntiBanValidator:
    """Control de frecuencia y límites de seguridad para LinkedIn."""

    @staticmethod
    def get_records() -> List[Dict[str, Any]]:
        if not PROCESSED_FILE.exists():
            return []
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def check_daily_limit(cls) -> bool:
        records = cls.get_records()
        today_str = date.today().isoformat()
        today_posts = [
            r for r in records
            if r.get("date", "").startswith(today_str) and r.get("status") == "success"
        ]
        if len(today_posts) >= MAX_DAILY_POSTS:
            print(f"[Anti-Ban] Límite diario alcanzado ({len(today_posts)}/{MAX_DAILY_POSTS} posts hoy).")
            print("           Saltando publicación para mantener un perfil profesional y orgánico.")
            return False
        return True

    @classmethod
    def record_publication(cls, project_name: str, caption: str, image_path: str, status: str = "success") -> None:
        records = cls.get_records()
        records.append({
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "project_name": project_name,
            "caption_preview": caption[:100],
            "image_path": str(image_path),
            "status": status
        })
        try:
            with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error guardando historial: {e}")

    # --- Engagement limits ---

    _ENGAGEMENT_LIMITS = {
        "connection": MAX_DAILY_CONNECTIONS,
        "comment": MAX_DAILY_COMMENTS,
        "reaction": MAX_DAILY_REACTIONS,
    }

    @staticmethod
    def _get_engagement_records() -> List[Dict[str, Any]]:
        if not ENGAGEMENT_FILE.exists():
            return []
        try:
            return json.loads(ENGAGEMENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    @staticmethod
    def _save_engagement_records(records: List[Dict[str, Any]]) -> None:
        ENGAGEMENT_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def check_engagement_limit(cls, action_type: str) -> bool:
        limit = cls._ENGAGEMENT_LIMITS.get(action_type)
        if limit is None:
            return True
        today_str = date.today().isoformat()
        records = cls._get_engagement_records()
        today_count = sum(
            1 for r in records
            if r.get("date") == today_str
            and r.get("action") == action_type
            and r.get("status") == "success"
        )
        if today_count >= limit:
            print(f"[Anti-Ban] Limite diario de '{action_type}' alcanzado ({today_count}/{limit}).")
            return False
        return True

    @classmethod
    def record_engagement(cls, action_type: str, target: str, detail: str = "", status: str = "success") -> None:
        records = cls._get_engagement_records()
        records.append({
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "action": action_type,
            "target": target,
            "detail": detail[:200],
            "status": status
        })
        cls._save_engagement_records(records)

    @classmethod
    def get_today_engagement_summary(cls) -> Dict[str, int]:
        today_str = date.today().isoformat()
        records = cls._get_engagement_records()
        summary: Dict[str, int] = {}
        for r in records:
            if r.get("date") == today_str and r.get("status") == "success":
                action = r.get("action", "unknown")
                summary[action] = summary.get(action, 0) + 1
        return summary
