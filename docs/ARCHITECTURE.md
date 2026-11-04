# Documentación Técnica de JobSeeker: Arquitectura, Desarrollo y Despliegue Headless

Documento de referencia técnica sobre cómo se concibió, desarrolló, optimizó y desplegó de forma autónoma la plataforma **JobSeeker** en un entorno multi-máquina con modo headless continuo.

---

## 1. Motivación y Objetivos del Proyecto

El proyecto surge ante la necesidad de construir una herramienta integral de **marca personal técnica, visibilidad en LinkedIn y optimización de candidaturas IT (DAM / Sistemas / Python / QA)** que opere de manera desatendida pero bajo el principio de **Human-in-the-Loop** ("Cero Burradas"):
- **Publicación técnica autónoma:** Generación de contenido riguroso a partir de código real y proyectos del desarrollador.
- **Evaluación ATS (Applicant Tracking System):** Simulación de algoritmos corporativos de RRHH para puntuar vacantes y maximizar la compatibilidad.
- **Networking de Confianza:** Priorización de reclutadores vinculados como contactos de 2º grado.
- **Alojamiento desatendido:** Operación en un servidor secundario (`mbp1`) en modo 100% headless sin monitor, liberando el equipo de trabajo principal.

---

## 2. Decisiones de Arquitectura y Componentes Clave

```text
 ┌────────────────────────────────────────────────────────┐
 │                   JobSeeker Core                       │
 └──────────────────────────┬─────────────────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  DevDiary    │     │ ATSAnalyzer  │     │  Engagement  │
│  Generator   │     │ (HR Scoring) │     │  (2º Grado)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ Telegram Reviewer / Bot   │
              │  (@JobGaBot Co-Pilot)     │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │   Resource Governor       │
              │  (Playwright / Chromium)  │
              └───────────────────────────┘
```

### A. Motor ATS de Recursos Humanos (`src/ats_analyzer.py`)
- **Taxonomía Normalizada:** Base de datos léxica de más de 80 tecnologías categorizadas en 8 ramas (Lenguajes, Backend, Frontend/Mobile, DevOps/Cloud, QA, IA/Data, Ciberseguridad, Metodologías).
- **Algoritmo de Scoring Ponderado (0 a 100%):** Ponderación triple (x3) para keywords detectadas en el título del puesto frente a la descripción, simulando el comportamiento de plataformas como *LinkedIn Recruiter* o *Workday*.
- **Gap Analysis:** Identificación matemática de habilidades faltantes en cada vacante para justificar la elección del currículum óptimo.
- **Enrutamiento Inteligente de CVs Oficiales:** Asignación automática de los PDFs oficiales existentes (`GTV_CV_Sys_ES2026.pdf`, `GTV_CV_IA_ES2026.pdf`, `GTV_CV_iOS_ES2026.pdf`, `GTV_CV_ES2026.pdf`).

### B. Networking Estratégico de Confianza (`src/engagement_engine.py`)
- Inyección del filtro `network=["S"]` en las consultas de búsqueda de personas de LinkedIn.
- Prioriza conectar con técnicos de selección y reclutadores que son **contactos de contactos actuales** (2º grado), multiplicando la tasa de aceptación y evitando flags de seguridad.

### C. Co-Pilot Táctil en Telegram (`src/telegram_bot.py`)
- Arquitectura desacoplada basada en botones inline táctiles:
  - `/status`: Dashboard de métricas en tiempo real.
  - `/history`: Historial unificado de posts, contactos y candidaturas.
  - `/apply`: Ofertas con desglose de Score ATS y confirmación en 1 toque.
  - `/engage`: Plan diario de conexiones estratégicas.
  - `/publish`: Generación y previsualización de artículos técnicos.

### D. Gobernanza de Recursos y Anti-Ban (`src/resource_governor.py` & `src/anti_ban.py`)
- Limpieza automática periódica (cada 15 min):
  - Purga de bloqueos de Chromium (`SingletonLock`, `SingletonCookie`).
  - Recolección activa de memoria residual (`gc.collect()`).
  - Eliminación de capturas de pantalla temporales huérfanas.
- Control de cuotas de seguridad biológica (1 post/día, 5 invitaciones/día, 5 solicitudes sencillas/día).

---

## 3. Retos de Ingeniería y Soluciones Técnicas en el Despliegue

### 1. Migración hacia Servidor Remoto sin Pantalla (`mbp1`)
- **Entorno:** MacBook Pro 2014 ejecutando **macOS 11.7.11 Big Sur (x86_64)** mientras que el desarrollo se realizó en MacBook Air M4 (macOS 15 Sequoia / ARM64).
- **Problema 1: Incompatibilidad de Node.js en Playwright:**
  - El driver bundled de Playwright requería macOS 13+.
  - *Solución:* Se instaló `Node 20` oficial x86_64 y se enlazó simbólicamente en `.venv/lib/python3.13/site-packages/playwright/driver/node`.
- **Problema 2: Cifrado de cookies entre versiones de macOS:**
  - Al transferir el perfil de usuario de Chrome, el Keychain de Big Sur no podía descifrar las cookies generadas en Sequoia.
  - *Solución:* Se extrajo el estado de almacenamiento (`storage_state.json`), se sanitizó de campos incompatibles y se inyectó en un binario de Chromium nativo para macOS 11, logrando autenticación inmediata en LinkedIn Feed por SSH sin tocar el teclado ni la pantalla del MBP1.
- **Problema 3: Persistencia del Servicio Headless:**
  - Se configuró la ejecución bajo `caffeinate -dimsu` en segundo plano para evitar que el equipo suspenda la conexión de red o los hilos de Playwright al cerrar la tapa.

---

## 4. Repositorios y Versionado

1. **Monorepo Local:** `Developer/Projects/JobSeekerGA` (dentro de GitGa).
2. **Repositorio Remoto Oficial:** [github.com/gtrujillovdev-cyber/JobSeeker](https://github.com/gtrujillovdev-cyber/JobSeeker).
