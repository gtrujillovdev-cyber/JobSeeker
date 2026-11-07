#!/usr/bin/env python3
"""
Punto de entrada de JobSeekerGA.
Pipeline de automatización de marca personal técnica en LinkedIn con revisión previa en Telegram.
"""

import sys
import argparse
from pathlib import Path

from src.pipeline import JobSeekerPipeline
from scripts.setup_linkedin_session import setup_linkedin_session
from src.project_capturer import ProjectCapturer
from src.copy_generator import CopyGenerator
from src.telegram_reviewer import TelegramReviewer
from src.job_scanner import JobScanner
from src.engagement_engine import EngagementEngine
from src.telegram_bot import TelegramBot
from src.dev_diary import DevDiaryGenerator
from src.easy_apply import EasyApplyEngine

def main():
    parser = argparse.ArgumentParser(description="JobSeekerGA - LinkedIn Autonomous Publisher con Co-Pilot")
    parser.add_argument("--bot", action="store_true", help="Inicia el bot de Telegram (daemon de long-polling)")
    parser.add_argument("--dry-run", action="store_true", help="Simula la ejecución completa sin publicar")
    parser.add_argument("--setup-session", action="store_true", help="Abre el asistente para iniciar sesión en LinkedIn")
    parser.add_argument("--test-card", action="store_true", help="Genera una tarjeta visual de prueba")
    parser.add_argument("--test-telegram", action="store_true", help="Envía un borrador de prueba a tu bot de trading en Telegram")
    parser.add_argument("--direct", action="store_true", help="Publica directamente sin esperar aprobación en Telegram")
    parser.add_argument("--scan-jobs", action="store_true", help="Escanea LinkedIn Jobs y guarda ofertas relevantes")
    parser.add_argument("--scan-summary", action="store_true", help="Muestra resumen del ultimo escaneo de ofertas")
    parser.add_argument("--scan-keywords", type=str, default=None, help="Keywords para el escaneo (sobreescribe .env)")
    parser.add_argument("--scan-location", type=str, default=None, help="Ubicacion para el escaneo (sobreescribe .env)")
    parser.add_argument("--engage", action="store_true", help="Propone y ejecuta plan de engagement (con aprobacion Telegram)")
    parser.add_argument("--engage-direct", action="store_true", help="Ejecuta engagement sin esperar aprobacion Telegram")
    parser.add_argument("--apply", action="store_true", help="Busca vacantes de Solicitud Sencilla + CV adaptado y pide aprobacion en Telegram")
    parser.add_argument("--apply-direct", action="store_true", help="Aplica directamente a vacantes de Solicitud Sencilla con el CV adaptado")
    parser.add_argument("--history", action="store_true", help="Muestra el historial completo de posts, contactos y candidaturas")
    parser.add_argument("--dev-diary", action="store_true", help="Publica la entrada de hoy del Diario de Desarrollo con Gemini")
    parser.add_argument("--publish-draft", type=str, default=None, help="Publica directamente un borrador aprobado por su draft_id")
    parser.add_argument("--publish-scheduled", action="store_true", help="Publica todos los borradores programados cuya hora haya llegado")
    parser.add_argument("--pipeline", action="store_true", help="Ejecuta el pase diario completo (escaneo, conexiones RRHH y borrador Diario)")
    parser.add_argument("--name", type=str, default="GaTDSEQ", help="Nombre del proyecto a promocionar")

    args = parser.parse_args()

    if args.publish_scheduled:
        from datetime import datetime
        from src.telegram_reviewer import _get_drafts
        drafts = _get_drafts()
        now = datetime.now()
        published_any = False
        for d_id, d_obj in list(drafts.items()):
            if d_obj.get("status") == "scheduled":
                sched_str = d_obj.get("scheduled_for", "")
                try:
                    sched_dt = datetime.fromisoformat(sched_str).replace(tzinfo=None)
                except Exception:
                    sched_dt = now
                if now >= sched_dt:
                    print(f"[*] Publicando borrador programado {d_id}...")
                    if TelegramReviewer.publish_approved_draft(d_id):
                        published_any = True
        if not published_any:
            print("[*] No había borradores programados pendientes de publicar en este momento.")
        return

    if args.pipeline:
        from scripts.daily_pass import run_daily_pass
        run_daily_pass(force=True)
        return

    if args.history:
        from src.easy_apply import EasyApplyEngine
        from src.anti_ban import AntiBanValidator

        print("=" * 65)
        print("          HISTORIAL COMPLETO DE ACTIVIDAD - JOBSEEKERGA")
        print("=" * 65)

        # 1. Publicaciones
        pub_records = [r for r in AntiBanValidator.get_records() if r.get("status") == "success"]
        print(f"\n[1] PUBLICACIONES REALIZADAS ({len(pub_records)}):")
        if pub_records:
            for p in reversed(pub_records[-8:]):
                p_date = p.get("date", "")[:16]
                p_name = p.get("project_name", "Post técnico")
                p_url = p.get("published_url", "https://www.linkedin.com/feed/")
                print(f"  • [{p_date}] {p_name} -> {p_url}")
        else:
            print("  • Sin publicaciones registradas.")

        # 2. Conexiones / Engagement
        eng_records = [r for r in AntiBanValidator._get_engagement_records() if r.get("status") == "success"]
        conn_records = [r for r in eng_records if r.get("action") == "connection"]
        print(f"\n[2] CONTACTOS RRHH Y CONEXIONES ENVIADAS ({len(conn_records)}):")
        if conn_records:
            for c in reversed(conn_records[-10:]):
                c_date = c.get("date", "")[:10]
                c_target = c.get("target", "Recruiter")
                c_detail = c.get("detail", "")
                print(f"  • [{c_date}] {c_target} — {c_detail}")
        else:
            print("  • Sin solicitudes de contacto registradas.")

        # 3. Solicitud Sencilla (Easy Apply)
        apply_records = [r for r in EasyApplyEngine._load_history() if r.get("status") == "success"]
        print(f"\n[3] VACANTES SOLICITUD SENCILLA APLICADAS ({len(apply_records)}):")
        if apply_records:
            for a in reversed(apply_records[-10:]):
                a_date = a.get("date", "")[:10]
                a_title = a.get("title", "Puesto IT")
                a_comp = a.get("company", "Empresa")
                a_cv = a.get("cv_label", "CV Oficial")
                a_url = a.get("url", "")
                print(f"  • [{a_date}] {a_title} @ {a_comp} [{a_cv}] -> {a_url}")
        else:
            print("  • Sin candidaturas registradas.")
        print("=" * 65)
        return

    if args.publish_draft:
        ok = TelegramReviewer.publish_approved_draft(args.publish_draft)
        sys.exit(0 if ok else 1)

    if args.bot:
        TelegramBot.run()
        return

    if args.setup_session:
        setup_linkedin_session()
        return

    if args.test_card:
        print("[*] Generando tarjeta visual de prueba...")
        card = ProjectCapturer.generate_code_card(
            project_name="GaTDSEQ",
            headline="Filtrado de Liquidez y Supresión de Ruido en Mercados de Alta Frecuencia",
            code_snippet="""# Validación de profundidad de libro de órdenes previa a ejecución
def validate_execution_liquidity(order_book, target_volume):
    depth = sum(bid.amount for bid in order_book.bids[:5])
    if depth < target_volume * 1.5:
        logger.warn("Slippage crítico previsto. Descartando orden.")
        return False
    return True""",
            tech_tags=["Python", "AlgorithmicTrading", "DataEngineering", "LowLatency"],
            filename="gatdseq_preview_card.png"
        )
        print(f"[✓] Tarjeta guardada en: {card}")
        return

    if args.test_telegram:
        print("[*] Generando copy riguroso con Gemini y enviando a tu bot de trading...")
        card = ProjectCapturer.generate_code_card(
            project_name="GaTDSEQ",
            headline="Filtrado de Liquidez y Supresión de Ruido en Mercados de Alta Frecuencia",
            code_snippet="""# Validación de profundidad de libro de órdenes previa a ejecución
def validate_execution_liquidity(order_book, target_volume):
    depth = sum(bid.amount for bid in order_book.bids[:5])
    if depth < target_volume * 1.5:
        logger.warn("Slippage crítico previsto. Descartando orden.")
        return False
    return True""",
            tech_tags=["Python", "AlgorithmicTrading", "DataEngineering", "LowLatency"],
            filename="gatdseq_test_card.png"
        )

        copy = CopyGenerator.generate_post(
            project_name="GaTDSEQ",
            headline_title="Control de Slippage y Filtrado de Ruido en Sistemas de Ejecución Automatizada",
            problem_context="En operativas cuantitativas con alta frecuencia de datos, los modelos predictivos basados únicamente en acción del precio suelen sufrir degradaciones severas causadas por barridos de liquidez transitorios y dispersión en la profundidad del libro de órdenes.",
            implementation_details="Diseñé un pipeline intermedio que audita en tiempo real la liquidez acumulada en los primeros niveles del libro antes de despachar cada orden, incorporando una ventana deslizante de volumen efectivo.",
            technical_findings="Al realizar backtesting y auditoría de eventos en vivo sobre pares de alta volatilidad, se detectó que más del 38% de los drawdowns no se debían a fallos en la señal, sino a ejecuciones en nodos de bajo volumen con impacto directo en el spread.",
            objectives_achieved=[
                "Reducción del Drawdown: Descarte proactivo de operaciones en zonas de escasa profundidad de mercado.",
                "Optimización de Ejecución: Eliminación de pérdidas por deslizamiento (slippage) involuntario en entradas de mercado.",
                "Resiliencia de Procesamiento: Pipeline asíncrono con latencia sub-milisegundo para evaluación de libros de órdenes."
            ],
            tech_stack=["Python", "BinanceAPI", "AlgorithmicTrading", "Backtesting"]
        )

        draft_id = TelegramReviewer.send_draft(
            project_name="GaTDSEQ",
            post_text=copy,
            image_path=card
        )
        if draft_id:
            print(f"[✓] Borrador enviado con éxito a tu bot de trading en Telegram.")
            print("[*] Revisa el bot en tu móvil y pulsa el botón.")
            TelegramReviewer.listen_and_process_decision(target_draft_id=draft_id)
        return

    if args.scan_jobs:
        jobs = JobScanner.scan(
            keywords=args.scan_keywords,
            location=args.scan_location
        )
        if jobs:
            summary = JobScanner.format_summary(jobs)
            print(f"\n{summary}")

            # Enviar resumen a Telegram si esta configurado
            if TelegramReviewer.is_configured():
                import requests
                from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
                tg_text = f"*RADAR DE EMPLEO*\n\n{summary}"
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": tg_text[:4000],
                        "parse_mode": "Markdown"
                    },
                    timeout=10
                )
                print("[*] Resumen enviado a Telegram.")
        return

    if args.scan_summary:
        today_jobs = JobScanner.get_today_results()
        if today_jobs:
            print(JobScanner.format_summary(today_jobs))
        else:
            all_results = JobScanner._load_results()
            if all_results:
                print(f"[*] No hay escaneos de hoy. Mostrando ultimos {min(15, len(all_results))} resultados:")
                print(JobScanner.format_summary(all_results[-15:]))
            else:
                print("[*] No hay resultados. Ejecuta primero: python main.py --scan-jobs")

        skills = JobScanner.get_demanded_skills()
        if skills:
            print("\n--- SKILLS MAS DEMANDADAS ---")
            for skill, count in list(skills.items())[:10]:
                bar = "#" * count
                print(f"  {skill:<20} {bar} ({count})")

        companies = JobScanner.get_target_companies()
        if companies:
            print(f"\n--- EMPRESAS TARGET ({len(companies)}) ---")
            for c in companies[:10]:
                print(f"  - {c}")
        return

    if args.engage or args.engage_direct:
        actions = EngagementEngine.propose_actions()
        if not actions:
            print("[*] No hay acciones de engagement disponibles.")
            return

        if args.engage_direct:
            print("[*] Ejecutando engagement en modo directo (sin esperar aprobacion previa)...")
            results = EngagementEngine._execute_actions(actions)
            success = sum(1 for r in results if r.get("status") == "success")
            print(f"[*] Engagement completado: {success}/{len(results)} acciones exitosas.")
            from config import TELEGRAM_CHAT_ID
            if TELEGRAM_CHAT_ID:
                EngagementEngine._report_results(results, int(TELEGRAM_CHAT_ID))
        else:
            proposal_id = EngagementEngine.send_proposals_to_telegram(actions)
            if proposal_id:
                EngagementEngine.listen_and_execute(actions)
        return

    if args.apply or args.apply_direct:
        jobs = EasyApplyEngine.scan_easy_apply_jobs(
            keywords=args.scan_keywords,
            location=args.scan_location,
            max_results=5
        )
        if not jobs:
            print("[*] No se encontraron ofertas de Solicitud Sencilla disponibles.")
            return

        if args.apply_direct:
            print("[*] Aplicando directamente con el CV adaptado a cada puesto...")
            results = EasyApplyEngine.execute_applications(jobs)
            EasyApplyEngine.report_results_to_telegram(results)
        else:
            proposal_id = EasyApplyEngine.send_proposals_to_telegram(jobs)
            if proposal_id:
                EasyApplyEngine.listen_and_execute(jobs)
        return

    if args.dev_diary:
        record = DevDiaryGenerator.prepare_daily_diary_draft(wait_approval=not args.dry_run)
        if record:
            print(f"\n[✓] Borrador #{record['entry_number']} enviado a Telegram: {record['display_name']}")
        else:
            print("\n[!] No se pudo preparar el borrador del Diario de Desarrollo.")
        return

    # Ejecución normal del pipeline
    review_mode = not args.direct
    pipeline = JobSeekerPipeline(dry_run=args.dry_run, review_mode=review_mode)

    pipeline.run_post(
        project_name=args.name,
        headline_title=f"Optimización de Rendimiento y Gestión de Estados en {args.name}",
        problem_context="Al mantener procesos en segundo plano de manera continua en sistemas macOS, la fragmentación de memoria y el estancamiento de hilos de ejecución representan el mayor riesgo de degradación del servicio.",
        implementation_details="Se desacopló el ciclo de ejecución en workers aislados con recolección periódica explícita y gestión estricta de descriptores de socket y contextos de navegador.",
        technical_findings="El perfilado con métricas de sistema evidenció que la retención de referencias en estructuras asíncronas no cerradas generaba un incremento sostenido de huella RSS superior a 350 MB en ciclos de 12 horas.",
        objectives_achieved=[
            "Estabilidad Operativa 24/7: Huella de memoria constante sin crecimiento residual.",
            "Aislamiento de Fallos: Recuperación automática ante desconexiones transitorias sin intervención humana.",
            "Eficiencia de Recursos: Reducción del uso de CPU en estado inactivo por debajo del 1.5%."
        ],
        tech_stack=["Python", "SystemArchitecture", "macOS", "Performance"],
        code_snippet="""# Aislamiento de workers y gestión de contexto persistente
async with task_supervisor() as supervisor:
    await supervisor.dispatch_isolated_process(pipeline_task)"""
    )

if __name__ == "__main__":
    main()
