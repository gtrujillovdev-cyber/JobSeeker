import hashlib
import json
import re
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple
from config import (
    PROCESSED_FILE, MAX_DAILY_POSTS,
    ENGAGEMENT_FILE, MAX_DAILY_CONNECTIONS, MAX_DAILY_COMMENTS, MAX_DAILY_REACTIONS
)

class AntiBanValidator:
    """Control de frecuencia, no-repetición y límites de seguridad para LinkedIn."""

    @staticmethod
    def _normalize_text_for_dedup(text: str) -> str:
        """Normaliza texto eliminando la cabecera numérica ('Diario #N:' / 'Diario de Desarrollo #N —') y espacios."""
        clean = (text or "").strip()
        clean = re.sub(r"^diario(?:\s+de\s+desarrollo)?\s*#\d+\s*[:—·\-]*\s*", "", clean, flags=re.IGNORECASE)
        return " ".join(clean.lower().split())

    @classmethod
    def _compute_content_hash(cls, text: str) -> str:
        normalized = cls._normalize_text_for_dedup(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _extract_title_signature(cls, text: str) -> str:
        first_line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
        return cls._normalize_text_for_dedup(first_line)[:120]

    @classmethod
    def is_duplicate_publication(
        cls,
        text: str,
        pill_id: Optional[str] = None,
        include_active_drafts: bool = False
    ) -> Tuple[bool, str]:
        """
        Garantiza que NUNCA se repita una publicación en LinkedIn:
        1. Comprueba `pill_id` frente al historial publicado.
        2. Comprueba `content_hash` SHA-256 normalizado (independiente del número `#N`).
        3. Comprueba `title_signature` / prefijo normalizado frente a publicaciones previas.
        4. Si `include_active_drafts=True`, también bloquea cualquier píldora/contenido ya presente
           en `pending_drafts.json` (pending, scheduled, publishing, published) o `dev_diary_history.json`
           en estado pending_approval/scheduled.
        """
        new_hash = cls._compute_content_hash(text)
        new_title = cls._extract_title_signature(text)
        new_norm_prefix = cls._normalize_text_for_dedup(text)[:75]

        # 1. Revisar published_history.json (solo éxitos reales)
        for rec in cls.get_records():
            if rec.get("status") != "success":
                continue
            if pill_id and rec.get("pill_id") and rec.get("pill_id") == pill_id:
                return True, f"pill_id ya publicada anteriormente ({pill_id})"
            if rec.get("content_hash") and rec.get("content_hash") == new_hash:
                return True, "contenido idéntico al de una publicación previa (hash)"
            old_title = rec.get("title_signature") or cls._extract_title_signature(rec.get("caption_preview", ""))
            if new_title and old_title and (new_title == old_title or (len(old_title) > 25 and (new_title in old_title or old_title in new_title))):
                return True, f"título equivalente ya publicado ({old_title[:60]})"
            old_norm_prefix = cls._normalize_text_for_dedup(rec.get("caption_preview", ""))[:75]
            if new_norm_prefix and old_norm_prefix and len(old_norm_prefix) > 35 and new_norm_prefix == old_norm_prefix:
                return True, "inicio de publicación ya registrado en el historial"

        # 2. Revisar dev_diary_history.json en la misma carpeta de datos
        diary_statuses = {"published", "pending_approval", "scheduled"} if include_active_drafts else {"published"}
        diary_hist_file = PROCESSED_FILE.parent / "dev_diary_history.json"
        if diary_hist_file.exists():
            try:
                diary_hist = json.loads(diary_hist_file.read_text(encoding="utf-8"))
                for h in diary_hist:
                    if h.get("status") not in diary_statuses:
                        continue
                    if pill_id and h.get("pill_id") and h.get("pill_id") == pill_id:
                        return True, f"píldora '{pill_id}' ya registrada en dev_diary_history ({h.get('status')})"
                    old_preview = h.get("post_preview", "")
                    old_title = cls._extract_title_signature(old_preview)
                    if new_title and old_title and (new_title == old_title or (len(old_title) > 25 and (new_title in old_title or old_title in new_title))):
                        return True, f"entrada de diario ya registrada ({old_title[:60]})"
            except Exception:
                pass

        # 3. Revisar pending_drafts.json si include_active_drafts=True
        if include_active_drafts:
            drafts_file = PROCESSED_FILE.parent / "pending_drafts.json"
            if drafts_file.exists():
                try:
                    drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
                    if isinstance(drafts, dict):
                        for d in drafts.values():
                            d_status = d.get("status", "")
                            if d_status not in {"pending", "scheduled", "publishing", "published"}:
                                continue
                            if pill_id and d.get("pill_id") and d.get("pill_id") == pill_id:
                                return True, f"píldora '{pill_id}' ya existe como borrador ({d_status})"
                            d_text = d.get("text", "")
                            if d_text:
                                if cls._compute_content_hash(d_text) == new_hash:
                                    return True, f"contenido idéntico al de un borrador existente ({d_status})"
                                old_title = cls._extract_title_signature(d_text)
                                if new_title and old_title and (new_title == old_title or (len(old_title) > 25 and (new_title in old_title or old_title in new_title))):
                                    return True, f"título equivalente ya presente en borrador ({old_title[:60]})"
                except Exception:
                    pass

        return False, ""

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
    def record_publication(
        cls,
        project_name: str,
        caption: str,
        image_path: str,
        status: str = "success",
        pill_id: Optional[str] = None
    ) -> None:
        records = cls.get_records()
        entry: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "project_name": project_name,
            "caption_preview": caption[:100],
            "content_hash": cls._compute_content_hash(caption),
            "title_signature": cls._extract_title_signature(caption),
            "image_path": str(image_path),
            "status": status
        }
        if pill_id:
            entry["pill_id"] = pill_id
        records.append(entry)
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
