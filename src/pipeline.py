from pathlib import Path
from typing import Optional, Dict, Any, List

from src.project_capturer import ProjectCapturer
from src.copy_generator import CopyGenerator
from src.linkedin_publisher import LinkedInPublisher
from src.telegram_reviewer import TelegramReviewer

class JobSeekerPipeline:
    def __init__(self, dry_run: bool = False, review_mode: bool = True):
        self.dry_run = dry_run
        self.review_mode = review_mode
        self.publisher = LinkedInPublisher(dry_run=dry_run)

    def run_post(
        self,
        project_name: str,
        headline_title: str,
        problem_context: str,
        implementation_details: str,
        technical_findings: str,
        objectives_achieved: List[str],
        tech_stack: List[str],
        code_snippet: Optional[str] = None,
        target_url: Optional[str] = None,
        custom_image: Optional[Path] = None,
        wait_approval: bool = True
    ) -> bool:
        """
        Ejecuta el ciclo:
        1. Captura o generación de tarjeta visual de código/arquitectura.
        2. Redacción técnica rigurosa (estilo informe/postmortem técnico).
        3. Envío al bot de Telegram (de trading) para aprobación con 1 click.
        4. Publicación en LinkedIn únicamente tras tu visto bueno.
        """
        print(f"\n=======================================================")
        print(f"💼 PIPELINE JOBSEEKER (Revisión Activa): {project_name}")
        print(f"=======================================================")

        # 1. Obtención o generación de la captura
        image_path = None
        if custom_image and Path(custom_image).exists():
            image_path = Path(custom_image)
            print(f"[1/3] Usando imagen personalizada: {image_path}")
        elif target_url:
            print(f"[1/3] Capturando URL en vivo: {target_url}...")
            image_path = ProjectCapturer.capture_url(target_url, filename=f"{project_name.lower()}_preview.png")
            print(f"[✓] Captura generada en: {image_path}")
        elif code_snippet:
            print(f"[1/3] Generando tarjeta técnica para {project_name}...")
            image_path = ProjectCapturer.generate_code_card(
                project_name=project_name,
                headline=headline_title,
                code_snippet=code_snippet,
                tech_tags=tech_stack,
                filename=f"{project_name.lower()}_card.png"
            )
            print(f"[✓] Tarjeta visual generada en: {image_path}")

        # 2. Generación de Copy Técnico Riguroso
        print(f"[2/3] Redactando publicación con perfil de ingeniería...")
        post_text = CopyGenerator.generate_post(
            project_name=project_name,
            headline_title=headline_title,
            problem_context=problem_context,
            implementation_details=implementation_details,
            technical_findings=technical_findings,
            objectives_achieved=objectives_achieved,
            tech_stack=tech_stack
        )

        # 3. Flujo de Aprobación vs Publicación Directa
        if self.review_mode and TelegramReviewer.is_configured() and not self.dry_run:
            print(f"[3/3] 🛡️ Enviando borrador al bot de Telegram para tu aprobación...")
            draft_id = TelegramReviewer.send_draft(
                project_name=project_name,
                post_text=post_text,
                image_path=image_path
            )
            if not draft_id:
                print("[!] Error enviando borrador a Telegram.")
                return False

            if wait_approval:
                return TelegramReviewer.listen_and_process_decision(target_draft_id=draft_id)
            else:
                print(f"[✓] Borrador {draft_id} encolado en Telegram. Esperando tu acción.")
                return True

        # Publicación directa (o Dry Run)
        print(f"[3/3] Publicando en LinkedIn (dry_run={self.dry_run})...")
        return self.publisher.publish_post(
            text=post_text,
            image_path=image_path,
            project_name=project_name
        )
