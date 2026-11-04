#!/usr/bin/env python3
"""
Scheduler autónomo de JobSeekerGA integrado con el Bot de Telegram (@JobGaBot).
- Gestiona la cola de borradores programados en `data/pending_drafts.json` (ej. publicaciones programadas a las 10:00 AM).
- NUNCA publica sin confirmación previa: todos los borradores y planes de networking pasan por tu aprobación en Telegram.
"""

from src.telegram_bot import TelegramBot


def main():
    TelegramBot.run()


if __name__ == "__main__":
    main()
