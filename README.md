# JobSeeker 💼🚀

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automated-2EAD33?style=flat&logo=playwright&logoColor=white)](https://playwright.dev/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-2.5%20Flash-8E75B2?style=flat&logo=google&logoColor=white)](https://ai.google.dev/)
[![Telegram](https://img.shields.io/badge/Telegram-Co--Pilot%20Bot-26A5E4?style=flat&logo=telegram&logoColor=white)](https://telegram.org/)
[![Tests](https://img.shields.io/badge/Tests-81%20Passed-brightgreen?style=flat&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**JobSeeker** es una plataforma autónoma de ingeniería de talento y marca personal técnica en LinkedIn, diseñada con arquitectura **Human-in-the-Loop** vía Telegram. Integra escaneo inteligente de vacantes, motor analítico ATS (Applicant Tracking System), enrutamiento dinámico de currículums oficiales y networking relacional por grados de afinidad.

---

## 🏗️ Arquitectura del Sistema

```text
                                  ┌────────────────────────┐
                                  │   LinkedIn Jobs & Feed │
                                  └───────────┬────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         ┌─────────────────────────┐                     ┌─────────────────────────┐
         │     JobScanner / ATS    │                     │    Engagement Engine    │
         │   (Clasificación Taxon) │                     │   (Contactos 2º Grado)  │
         └────────────┬────────────┘                     └────────────┬────────────┘
                      │                                               │
                      ▼                                               ▼
         ┌─────────────────────────┐                     ┌─────────────────────────┐
         │     ATSAnalyzer HR      │                     │    Anti-Ban Governor    │
         │ (Match 0-100% + Gaps)   │                     │ (Rate Limits & Memory)  │
         └────────────┬────────────┘                     └────────────┬────────────┘
                      │                                               │
                      └───────────────────────┬───────────────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │ Telegram Bot Co-Pilot   │
                                 │   (Revisión Táctil)     │
                                 └────────────┬────────────┘
                                              │
                           [ Aprobado ] ──────┴────── [ Rechazado ]
                                 │                           │
                                 ▼                           ▼
                    ┌─────────────────────────┐         ┌─────────┐
                    │  Playwright Automation  │         │ Descart │
                    │ (Easy Apply & Publicar) │         └─────────┘
                    └─────────────────────────┘
```

---

## ✨ Características Principales

### 1. Motor ATS de Recursos Humanos (`ATSAnalyzer`)
* **Taxonomía IT Exhaustiva:** Extracción de entidades semánticas clasificadas en 8 ramas tecnológicas (Lenguajes, Backend, Mobile/Frontend, DevOps/Cloud, QA/Testing, IA/Data, Ciberseguridad y Metodologías).
* **Scoring Ponderado (0 a 100%):** Ponderación triple para keywords en el título de la vacante, simulando algoritmos de LinkedIn Recruiter y Workday.
* **Gap Analysis:** Identificación precisa de competencias clave requeridas vs competencias cubiertas.
* **Enrutamiento Oficial de CVs:** Asignación automática del PDF oficial preexistente de mayor compatibilidad:
  * `GTV_CV_Sys_ES2026.pdf` — Sistemas Linux, Redes y Ciberseguridad.
  * `GTV_CV_IA_ES2026.pdf` — Python Backend, APIs y Automatización IA.
  * `GTV_CV_iOS_ES2026.pdf` — Desarrollo Multiplataforma DAM, SwiftUI y Full-Stack.
  * `GTV_CV_ES2026.pdf` — QA Automation, SDET y Calidad de Software.

### 2. Networking Relacional de Confianza (Contactos de 2º Grado)
* **Filtro de Red de Confianza (`network_depth=F`):** Prioriza la búsqueda de responsables de selección (RRHH, Talent Acquisition) que ya sean **contactos de tus contactos actuales** (2º grado).
* **Mayor Tasa de Aceptación:** Conectar a través de vínculos compartidos multiplica la tasa de respuesta y minimiza flags de cuenta.

### 3. Human-in-the-Loop en Telegram (`@JobGaBot`)
* Panel de control interactivo mediante botones inline táctiles.
* Comandos disponibles:
  * `/status`: Dashboard diario de actividad.
  * `/scan`: Escaneo de ofertas en tiempo real.
  * `/summary`: Ranking de skills más demandadas del mercado.
  * `/publish`: Generación y revisión de post para LinkedIn.
  * `/engage`: Plan de networking estratégico (5 conexiones seguras).
  * `/apply`: Ofertas de Solicitud Sencilla con Score ATS y CV asignado.
  * `/history`: Historial consolidado de posts, contactos y candidaturas.
  * `/limits`: Verificación de cuotas diarias anti-ban.
  * `/health`: Estado de la sesión persistente.

### 4. Gobernanza de Recursos y Anti-Ban
* **`ResourceGovernor`:** Purga activa de bloqueos de Chromium (`SingletonLock`), liberación periódica de memoria residente (`gc.collect()`) y limpieza de capturas huérfanas.
* **`AntiBanValidator`:** Control estricto de límites orgánicos diarios (1 post, 5 invitaciones de contacto, 5 candidaturas) con retardos gaussianos humanos.

---

## 🚀 Instalación y Puesta en Marcha

### Prerrequisitos
* Python 3.11 o superior.
* Google Chrome instalado (o binario Chromium compatible).

### 1. Clonar el repositorio
```bash
git clone https://github.com/gtrujillovdev-cyber/JobSeeker.git
cd JobSeeker
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar variables de entorno
Copia la plantilla y configura tus credenciales:
```bash
cp .env.example .env
```
Campos necesarios en `.env`:
* `TELEGRAM_BOT_TOKEN`: Token obtenido de `@BotFather`.
* `TELEGRAM_CHAT_ID`: Tu ID de chat de Telegram.
* `GEMINI_API_KEY`: API Key de Google AI Studio.

### 4. Inicializar sesión persistente de LinkedIn (Solo la primera vez)
```bash
python scripts/setup_linkedin_session.py
```
Se abrirá un navegador Chrome para iniciar sesión. Una vez completado, el perfil persistente quedará guardado localmente de forma segura.

---

## 💻 Uso desde la Línea de Comandos (CLI)

```bash
# Iniciar el bot de Telegram en modo escucha continuo
python main.py --bot

# Ver el historial completo consolidado (publicaciones, contactos, candidaturas)
python main.py --history

# Escanear ofertas de empleo relevantes en el radar
python main.py --scan-jobs

# Ver resumen de habilidades más demandadas y empresas activas
python main.py --scan-summary

# Proponer y enviar invitaciones a recruiters (5 conexiones de 2º grado)
python main.py --engage

# Escanear y aplicar a vacantes de Solicitud Sencilla con CV adaptado ATS
python main.py --apply

# Ejecutar el Diario de Desarrollo técnico para LinkedIn
python main.py --dev-diary
```

---

## 🧪 Tests y Calidad de Código

Ejecutar la suite completa de pruebas unitarias:
```bash
pytest -v
```
Actualmente cuenta con **81 tests unitarios y de integración** pasando en verde.

---

## 🔒 Privacidad y Seguridad

* **Sin credenciales hardcodeadas:** Ninguna contraseña ni cookie se almacena en el repositorio.
* **Protección `.gitignore`:** Archivos `.env`, perfiles de sesión `.browser_profiles/` y bases de datos en `data/` quedan excluidos del control de versiones.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más información.
