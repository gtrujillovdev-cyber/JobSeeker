import os
import time
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR
from src.linkedin_publisher import LinkedInPublisher

PENDING_DRAFTS_FILE = DATA_DIR / "pending_drafts.json"

def _get_drafts() -> Dict[str, Any]:
    if not PENDING_DRAFTS_FILE.exists():
        return {}
    try:
        with open(PENDING_DRAFTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_drafts(drafts: Dict[str, Any]) -> None:
    try:
        with open(PENDING_DRAFTS_FILE, "w", encoding="utf-8") as f:
            json.dump(drafts, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error guardando borradores: {e}")

class TelegramReviewer:
    """
    Sistema de aprobación en 1-click (Co-Pilot).
    Envía el borrador con la captura a Telegram y espera tu botón de aprobación
    antes de enviar nada a LinkedIn.
    """

    @staticmethod
    def is_configured() -> bool:
        return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

    @classmethod
    def send_draft(
        cls,
        project_name: str,
        post_text: str,
        image_path: Optional[Any] = None,
        first_comment: Optional[str] = None
    ) -> Optional[str]:
        if not cls.is_configured():
            print("[TelegramReviewer] Token o Chat ID no configurados en .env")
            return None

        # Normalizar lista de rutas de imagen
        image_paths = []
        if isinstance(image_path, (list, tuple)):
            image_paths = [Path(p) for p in image_path if p and Path(p).exists()]
        elif image_path and Path(image_path).exists():
            image_paths = [Path(image_path)]

        draft_id = uuid.uuid4().hex[:8]
        drafts = _get_drafts()
        drafts[draft_id] = {
            "draft_id": draft_id,
            "project_name": project_name,
            "text": post_text,
            "image_path": str(image_paths[0]) if image_paths else None,
            "image_paths": [str(p) for p in image_paths],
            "first_comment": first_comment or "",
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        _save_drafts(drafts)

        comment_block = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 PRIMER COMENTARIO AUTOMÁTICO (se publica justo después):\n\n"
            f"{first_comment.strip()}"
        ) if first_comment else ""

        caption_header = (
            f"🚨 NUEVO BORRADOR PARA LINKEDIN\n"
            f"📁 Proyecto: {project_name}\n"
            f"🖼️ Capturas adjuntas: {len(image_paths)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        caption_body = post_text.strip()
        full_caption = caption_header + caption_body + comment_block

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Publicar ahora", "callback_data": f"approve:{draft_id}"},
                    {"text": "🕙 Programar 10:00 AM", "callback_data": f"schedule10:{draft_id}"}
                ],
                [
                    {"text": "🔄 Regenerar enfoque", "callback_data": f"regen:{draft_id}"},
                    {"text": "❌ Descartar", "callback_data": f"reject:{draft_id}"}
                ]
            ]
        }

        url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        try:
            for idx, img in enumerate(image_paths, 1):
                with open(img, "rb") as photo:
                    data = {
                        "chat_id": TELEGRAM_CHAT_ID,
                        "caption": f"🖼️ Captura {idx}/{len(image_paths)} · {project_name}"
                    }
                    requests.post(url_photo, data=data, files={"photo": photo}, timeout=20)

            msg_payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": full_caption + "\n\n💡 _Tip: Responde (Reply) a este mensaje con texto nuevo si quieres editar el post antes de aprobar._",
                "reply_markup": keyboard
            }
            res = requests.post(url_msg, json=msg_payload, timeout=20)

            if res.status_code == 200:
                msg_id = res.json().get("result", {}).get("message_id")
                if msg_id:
                    drafts = _get_drafts()
                    if draft_id in drafts:
                        drafts[draft_id]["telegram_message_id"] = msg_id
                        _save_drafts(drafts)
                print(f"[TelegramReviewer] [✓] Borrador {draft_id} enviado a tu Telegram para aprobación.")
                return draft_id
            else:
                print(f"[TelegramReviewer] [!] Error enviando a Telegram ({res.status_code}): {res.text}")
                return None
        except Exception as e:
            print(f"[TelegramReviewer] [!] Excepción enviando borrador: {e}")
            return None

    @classmethod
    def schedule_draft_for_10am(cls, draft_id: str) -> Optional[str]:
        """
        Deja el borrador en cola con status='scheduled' para el próximo tramo de las 10:00 AM.
        El scheduler integrado del bot lo publicará automáticamente a esa hora.
        """
        drafts = _get_drafts()
        if draft_id not in drafts:
            return None
        now = datetime.now()
        target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        iso_str = target.isoformat()
        drafts[draft_id]["status"] = "scheduled"
        drafts[draft_id]["scheduled_for"] = iso_str
        _save_drafts(drafts)
        return target.strftime("%Y-%m-%d a las %H:%M")

    @classmethod
    def publish_approved_draft(cls, draft_id: str) -> bool:
        """
        Publica un borrador previamente aprobado por su draft_id en LinkedIn
        (incluyendo galería de imágenes, primer comentario automático, URL directa y captura de confirmación).
        """
        drafts = _get_drafts()
        if draft_id not in drafts:
            print(f"[TelegramReviewer] [!] Borrador {draft_id} no encontrado en pending_drafts.json")
            return False

        draft = drafts[draft_id]
        publisher = LinkedInPublisher(dry_run=False)
        img_list = [Path(p) for p in draft.get("image_paths", []) if p and Path(p).exists()]
        if not img_list and draft.get("image_path"):
            img_list = [Path(draft["image_path"])]

        success = publisher.publish_post(
            text=draft["text"],
            image_path=img_list,
            project_name=draft["project_name"],
            first_comment=draft.get("first_comment")
        )

        draft["status"] = "published" if success else "failed"
        draft["published_at"] = datetime.now().isoformat()
        if publisher.last_published_url:
            draft["published_url"] = publisher.last_published_url
        _save_drafts(drafts)

        # Actualizar también dev_diary_history.json para que el contador avance tras publicar
        history_file = DATA_DIR / "dev_diary_history.json"
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
                for rec in history:
                    if rec.get("draft_id") == draft_id:
                        rec["status"] = "published" if success else "failed"
                        rec["published_at"] = datetime.now().isoformat()
                        if publisher.last_published_url:
                            rec["published_url"] = publisher.last_published_url
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[TelegramReviewer] Aviso actualizando historial: {e}")

        if cls.is_configured():
            post_url = publisher.last_published_url or ""
            url_line = f"\n🔗 Enlace a la publicación:\n{post_url}" if post_url else ""
            msg_text = (
                f"🎉 ¡Publicado con éxito en LinkedIn (+ 1er comentario fijado)!\n"
                f"📁 Proyecto: {draft['project_name']}\n"
                f"🕒 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}{url_line}"
                if success else
                f"❌ Error al publicar en LinkedIn para {draft['project_name']}. Revisa logs/."
            )
            reply_markup = (
                {"inline_keyboard": [[{"text": "🔗 Ver publicación en LinkedIn", "url": post_url}]]}
                if post_url else None
            )
            try:
                if success and publisher.last_confirmation_screenshot and publisher.last_confirmation_screenshot.exists():
                    with open(publisher.last_confirmation_screenshot, "rb") as photo:
                        data_payload: Dict[str, Any] = {
                            "chat_id": TELEGRAM_CHAT_ID,
                            "caption": msg_text[:1024]
                        }
                        if reply_markup:
                            data_payload["reply_markup"] = json.dumps(reply_markup)
                        r_photo = requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                            data=data_payload,
                            files={"photo": photo},
                            timeout=20
                        )
                        if r_photo.status_code != 200:
                            msg_json: Dict[str, Any] = {"chat_id": TELEGRAM_CHAT_ID, "text": msg_text}
                            if reply_markup:
                                msg_json["reply_markup"] = reply_markup
                            requests.post(
                                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                json=msg_json,
                                timeout=15
                            )
                else:
                    msg_json = {"chat_id": TELEGRAM_CHAT_ID, "text": msg_text}
                    if reply_markup:
                        msg_json["reply_markup"] = reply_markup
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json=msg_json,
                        timeout=15
                    )
            except Exception as e:
                print(f"[TelegramReviewer] Error enviando confirmación a Telegram: {e}")

        return success

    @classmethod
    def listen_and_process_decision(cls, target_draft_id: Optional[str] = None, timeout: int = 1800) -> bool:
        """
        Escucha las decisiones en Telegram (long polling):
        - Publicar ahora ('approve')
        - Programar para las 10:00 AM ('schedule10')
        - Regenerar enfoque ('regen')
        - Descartar ('reject')
        - Editar texto respondiendo (Reply) al mensaje del borrador
        """
        if not cls.is_configured():
            return False

        print("\n" + "=" * 65)
        print(" 📲 ESPERANDO TU APROBACIÓN EN TELEGRAM...")
        print("=" * 65)
        print("[*] Usa los botones [✅ Publicar ahora], [🕙 Programar 10:00 AM], [🔄 Regenerar] o responde al mensaje para editar.")
        print(f"[*] Escuchando eventos (timeout: {timeout // 60} minutos)...")

        last_update_id = 0
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                params = {
                    "offset": last_update_id + 1,
                    "timeout": 10
                }
                res = requests.get(url, params=params, timeout=15)
                if res.status_code != 200:
                    time.sleep(2)
                    continue

                updates = res.json().get("result", [])
                for update in updates:
                    last_update_id = update["update_id"]

                    # Soporte de edición de borrador respondiendo (Reply) al mensaje en Telegram
                    if "message" in update and "reply_to_message" in update["message"]:
                        msg = update["message"]
                        replied_id = msg["reply_to_message"].get("message_id")
                        new_body = (msg.get("text") or "").strip()
                        if replied_id and new_body:
                            drafts = _get_drafts()
                            for d_id, d_obj in drafts.items():
                                if d_obj.get("telegram_message_id") == replied_id:
                                    from src.dev_diary import DevDiaryGenerator
                                    cleaned = DevDiaryGenerator._format_clean_post(new_body)
                                    d_obj["text"] = cleaned
                                    _save_drafts(drafts)
                                    requests.post(
                                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                        json={
                                            "chat_id": TELEGRAM_CHAT_ID,
                                            "text": f"✏️ *Texto del borrador `{d_id}` actualizado y formateado:*\n\n{cleaned}",
                                            "parse_mode": "Markdown",
                                            "reply_markup": {
                                                "inline_keyboard": [
                                                    [
                                                        {"text": "✅ Publicar ahora", "callback_data": f"approve:{d_id}"},
                                                        {"text": "🕙 Programar 10:00 AM", "callback_data": f"schedule10:{d_id}"}
                                                    ],
                                                    [
                                                        {"text": "❌ Descartar", "callback_data": f"reject:{d_id}"}
                                                    ]
                                                ]
                                            }
                                        }
                                    )
                                    break
                        continue

                    # Comprobar si es un click en botón inline (callback_query)
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb["id"]
                        data = cb.get("data", "")
                        message = cb.get("message", {})
                        message_id = message.get("message_id")
                        chat_id = message.get("chat", {}).get("id")

                        if ":" not in data:
                            continue

                        action, draft_id = data.split(":", 1)
                        if target_draft_id and draft_id != target_draft_id:
                            continue

                        drafts = _get_drafts()
                        if draft_id not in drafts:
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": "Borrador no encontrado o expirado."
                            })
                            continue

                        draft = drafts[draft_id]

                        if action == "approve":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": "🚀 Aprobado. Publicando en tu LinkedIn..."
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup", json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "reply_markup": {"inline_keyboard": []}
                            })
                            print(f"\n[✓] Aprobación recibida desde Telegram para '{draft['project_name']}'!")
                            return cls.publish_approved_draft(draft_id)

                        elif action == "schedule10":
                            when_str = cls.schedule_draft_for_10am(draft_id)
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": f"🕙 Programado para {when_str}"
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup", json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "reply_markup": {"inline_keyboard": []}
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": f"🕙 *Publicación programada* para *{when_str}*:\n*{draft['project_name']}* (`{draft_id}`)",
                                "parse_mode": "Markdown"
                            })
                            return True

                        elif action == "regen":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": "🔄 Regenerando enfoque y capturas..."
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup", json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "reply_markup": {"inline_keyboard": []}
                            })
                            from src.dev_diary import DevDiaryGenerator
                            new_id = DevDiaryGenerator.regenerate_draft_by_id(draft_id)
                            if new_id:
                                target_draft_id = new_id
                            continue

                        elif action == "reject":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                                "callback_query_id": cb_id,
                                "text": "🗑️ Borrador descartado."
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup", json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "reply_markup": {"inline_keyboard": []}
                            })
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": f"🗑️ Publicación para *{draft['project_name']}* descartada.",
                                "parse_mode": "Markdown"
                            })
                            draft["status"] = "rejected"
                            _save_drafts(drafts)
                            print(f"\n[!] Publicación descartada por el usuario desde Telegram.")
                            return False

            except Exception as e:
                print(f"[TelegramReviewer] Error en polling: {e}")
                time.sleep(3)

        print("[TelegramReviewer] Tiempo de espera agotado sin respuesta del usuario.")
        return False
