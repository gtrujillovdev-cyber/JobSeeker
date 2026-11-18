import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import BASE_DIR, DATA_DIR, GEMINI_API_KEY, CANDIDATE_PROFILE
from src.anti_ban import AntiBanValidator
from src.project_capturer import ProjectCapturer
from src.telegram_reviewer import TelegramReviewer, expire_stale_drafts

DEV_DIARY_HISTORY_FILE = DATA_DIR / "dev_diary_history.json"
PROJECTS_ROOT = BASE_DIR.parent  # /Users/.../Developer/Projects
_DRAFT_GEN_LOCK = threading.Lock()

# Banco de Píldoras Educativas Multi-Publicación por Proyecto:
# Permite extraer decenas de publicaciones didácticas sobre programación, arquitectura,
# planteamiento técnico, lógica de negocio, resiliencia en sistemas y QA/CI-CD a partir de cada proyecto.
EDUCATIONAL_PILLS_BY_PROJECT: Dict[str, List[Dict[str, Any]]] = {
    "JobSeeker": [
        {
            "pill_id": "jobseeker_ats_weighting",
            "category": "Lógica de negocio",
            "topic_track": "programacion",
            "source_file": "src/ats_analyzer.py",
            "target_symbol": "analyze_match",
            "code_focus": "for cv_filename, meta in CV_PROFILES_METADATA.items():",
            "headline": "Evitar falsos positivos entre 'Java' y 'JavaScript' al evaluar vacantes IT",
            "context": (
                "Dentro del motor de análisis de requisitos, el primer problema técnico que tuve que resolver fue la precisión "
                "al detectar tecnologías en texto libre: una búsqueda simple de subcadenas ('in') da positivo en 'Java' cuando la oferta "
                "pide 'JavaScript', y trata por igual una habilidad secundaria frente a un requisito principal del título."
            ),
            "lead_in": "En src/ats_analyzer.py implementé la evaluación ponderada de este modo:",
            "bullets": [
                "Filtro las tecnologías con límites de palabra (\\b en regex) para evitar colisiones entre nombres similares.",
                "Si una tecnología aparece en el título de la vacante, aporta el triple de peso que en la descripción.",
                "Calculo las brechas (gaps) separando los requisitos cubiertos de los que faltan antes de postular."
            ],
            "question": "¿Cómo soléis estructurar la normalización y ponderación de requisitos cuando trabajáis con texto libre?"
        },
        {
            "pill_id": "jobseeker_antiban_governor",
            "category": "Persistencia de Estado",
            "topic_track": "programacion",
            "source_file": "src/anti_ban.py",
            "target_symbol": "check_engagement_limit",
            "code_focus": "def check_engagement_limit",
            "headline": "Por qué desacoplar contadores de rate-limit de la memoria del proceso en Python",
            "context": (
                "En cualquier servicio ejecutado mediante cron o reinicios nocturnos, mantener contadores diarios "
                "únicamente en memoria hace que cada reinicio reinicie el límite y desajuste las cuotas del sistema."
            ),
            "lead_in": "En src/anti_ban.py externalicé el control de cuotas fuera del ciclo de vida del proceso:",
            "bullets": [
                "Antes de ejecutar una operación, la compuerta consulta el registro diario persistido en disco.",
                "Cada tipo de tarea mantiene su propio umbral diario independiente y trazable en JSON.",
                "Aunque el daemon se reinicie varias veces, el acumulado en ventana de 24 horas se respeta siempre."
            ],
            "question": "¿Qué mecanismo ligero soléis preferir para persistir cuotas o rate-limits en servicios pequeños sin depender de Redis?"
        },
        {
            "pill_id": "jobseeker_resource_governor",
            "category": "Sistemas y RAM",
            "topic_track": "sistemas",
            "source_file": "src/resource_governor.py",
            "target_symbol": "clean_orphaned_browser_locks",
            "code_focus": "def clean_orphaned_browser_locks",
            "headline": "Gestión de bloqueos SingletonLock y fugas de memoria con Chromium en servidor",
            "context": (
                "Al ejecutar automatizaciones con Playwright sobre una máquina dedicada con recursos ajustados, la interrupción "
                "abrupta de una sesión deja archivos SingletonLock activos en el perfil del navegador e impide las ejecuciones posteriores."
            ),
            "lead_in": "Para garantizar estabilidad en 24/7 añadí en src/resource_governor.py un protocolo preventivo:",
            "bullets": [
                "Al arrancar cada ciclo verifico procesos Chromium huérfanos y libero los bloqueos SingletonLock residuales.",
                "Purgo automáticamente capturas y logs antiguos para mantener acotado el almacenamiento del sistema.",
                "Ejecuto el daemon con prioridad nice 15 para convivir con otros pipelines sin saturar la CPU."
            ],
            "question": "¿Cómo gestionáis la limpieza de procesos huérfanos y bloqueos de perfil al automatizar navegadores en servidor?"
        },
        {
            "pill_id": "jobseeker_hitl_state_machine",
            "category": "Arquitectura",
            "topic_track": "programacion",
            "source_file": "src/telegram_bot.py",
            "target_symbol": "_scheduler_worker",
            "code_focus": "def _scheduler_worker",
            "headline": "Arquitectura Human-in-the-Loop con máquina de estados y control en Telegram",
            "context": (
                "En flujos que interactúan con perfiles públicos o candidaturas reales, automatizar el envío final sin "
                "supervisión añade un riesgo innecesario. La decisión técnica fue separar la preparación de datos de la confirmación."
            ),
            "lead_in": "En src/telegram_bot.py organicé el flujo con una máquina de estados intermedia:",
            "bullets": [
                "El planificador genera el borrador y las capturas a primera hora, dejándolo bloqueado en estado pending.",
                "Desde Telegram puedo revisar, editar el texto en caliente, regenerar el enfoque o programarlo para las 10:00.",
                "El módulo de publicación no se ejecuta en ningún caso sin una transición de estado aprobada explícitamente."
            ],
            "question": "¿En qué puntos de vuestros flujos automatizados mantenéis una validación humana intermedia antes de ejecutar?"
        },
        {
            "pill_id": "jobseeker_session_atomic_persistence",
            "category": "Persistencia y Sesiones",
            "topic_track": "programacion",
            "source_file": "src/browser_helper.py",
            "target_symbol": "persist_browser_session",
            "code_focus": "def persist_browser_session",
            "headline": "Persistencia atómica de cookies y storage preserving TTL en Playwright",
            "context": (
                "Al actualizar tokens de autenticación en navegadores headless, sobreescribir sesiones sin preservar "
                "los campos de expiración (expires) o volcar JSONs de forma no atómica genera cierres de sesión repentinos."
            ),
            "lead_in": "En src/browser_helper.py blindé la serialización del estado del navegador:",
            "bullets": [
                "Preservo atributos clave de cada cookie (SameSite, HttpOnly y timestamp exacto de expiración).",
                "Escribo a un archivo temporal intermedio (.tmp) antes de reemplazar el destino para evitar JSONs corruptos.",
                "Valido la presencia de cookies críticas antes de confirmar que la sesión sigue siendo válida."
            ],
            "question": "¿Qué patrón utilizáis para evitar que un reinicio abrupto corrompa las sesiones de usuario en disco?"
        },
    ],
    "Tv-streamer": [
        {
            "pill_id": "tvstreamer_socket_precheck",
            "category": "Redes locales",
            "topic_track": "sistemas",
            "source_file": "stream_manager.py",
            "target_symbol": "def ",
            "headline": "Validar la interfaz de red y el socket local antes de emitir hacia un Chromecast",
            "context": (
                "En las primeras pruebas de emisión hacia la televisión en LAN, el Chromecast recibía la URL correctamente pero "
                "quedaba en espera indefinida porque el servidor HTTP había quedado enlazado a loopback (127.0.0.1) en lugar de la IP Wi-Fi."
            ),
            "lead_in": "En stream_manager.py resolví este fallo añadiendo comprobaciones de red previas:",
            "bullets": [
                "Detecto dinámicamente la IP LAN de la interfaz de red activa en lugar de depender de localhost.",
                "Realizo una apertura de socket TCP de validación contra el puerto antes de enviar el payload al televisor.",
                "Si el firewall local bloquea el puerto, el servicio informa del diagnóstico exacto al instante."
            ],
            "question": "¿Qué comprobaciones previas de red soléis incorporar al desarrollar herramientas locales que comunican dispositivos en LAN?"
        },
        {
            "pill_id": "tvstreamer_remux_vs_transcode",
            "category": "Rendimiento Multimedia",
            "topic_track": "programacion",
            "source_file": "stream_manager.py",
            "target_symbol": "def ",
            "headline": "Servir vídeo por HTTP Range sin saturar la CPU con transcodificación innecesaria",
            "context": (
                "Recodificar vídeo al vuelo dispara el consumo de CPU de forma innecesaria cuando el dispositivo de destino "
                "ya soporta de forma nativa el códec H.264 del archivo original."
            ),
            "lead_in": "En stream_manager.py optimicé la entrega multimedia priorizando la compatibilidad nativa:",
            "bullets": [
                "Cuando el contenedor MP4 es compatible con Google Cast, sirvo el flujo directo mediante HTTP por rangos de bytes.",
                "Reservo la conversión únicamente para pistas de audio o contenedores que el receptor no soporta de serie.",
                "Controlo el ciclo de vida del subproceso para liberar el puerto limpiamente al detener la reproducción."
            ],
            "question": "¿Qué enfoque os ha dado mejor equilibrio entre latencia y consumo de CPU trabajando con streaming local en Python?"
        },
        {
            "pill_id": "tvstreamer_http_range_requests",
            "category": "Protocolos Web y Streaming",
            "topic_track": "programacion",
            "source_file": "video_server.py",
            "target_symbol": "def ",
            "headline": "Implementar respuestas HTTP 206 Partial Content para scrubbing de vídeo en Python",
            "context": (
                "Cuando un reproductor de televisión intenta avanzar o rebobinar una película por red local, un servidor web "
                "que envía el archivo completo sin cabeceras Range bloquea el buffer y congela la reproducción."
            ),
            "lead_in": "En video_server.py implementé soporte nativo para peticiones por rangos de bytes:",
            "bullets": [
                "Parseo la cabecera Range solicitada por el reproductor para devolver fragmentos con código de estado 206.",
                "Uso seek para saltar directamente al byte requerido en disco sin cargar el archivo completo en memoria RAM.",
                "Calculo y emito cabeceras Content-Range y Accept-Ranges para permitir saltos temporales inmediatos."
            ],
            "question": "¿Habéis tenido que implementar soporte para HTTP Range manualmente o delegáis siempre en proxies como Nginx?"
        },
        {
            "pill_id": "tvstreamer_tailscale_mtu_discovery",
            "category": "Redes y VPNs",
            "topic_track": "sistemas",
            "source_file": "app.py",
            "target_symbol": "def ",
            "headline": "Detección dinámica de interfaces LAN vs túneles VPN Tailscale sin IPs fijas en código",
            "context": (
                "Al transmitir contenido multimedia entre subredes o a través de VPNs como Tailscale, fijar una IP en un "
                "archivo de configuración rompe el servicio cuando la máquina cambia de red Wi-Fi o conmuta a la interfaz de túnel."
            ),
            "lead_in": "En app.py automaticé la detección de la interfaz de enlace activa:",
            "bullets": [
                "Sondeo las rutas del sistema operativo para identificar qué interfaz conecta directamente con el cliente.",
                "Distingo automáticamente si el destino está en la red local o en la red virtual de Tailscale.",
                "Gestiono la reutilización de sockets con SO_REUSEADDR para permitir reinicios sin esperar al TIME_WAIT."
            ],
            "question": "¿Cómo gestionáis el enlace dinámico de interfaces de red en servicios que conviven con túneles VPN?"
        },
    ],
    "InteractiveCV": [
        {
            "pill_id": "interactivecv_data_driven_ui",
            "category": "Frontend y Arquitectura",
            "topic_track": "programacion",
            "source_file": "index.html",
            "target_symbol": "function",
            "headline": "Desacoplar datos del DOM para alternar perfiles técnicos sin duplicar HTML",
            "context": (
                "Para mostrar un enfoque especializado en Backend Python, Sistemas Linux/Ciberseguridad o QA desde un único "
                "enlace, mantener plantillas HTML separadas generaba duplicidad y desincronización en cada actualización."
            ),
            "lead_in": "En index.html apliqué un renderizado guiado por estructuras de datos:",
            "bullets": [
                "Centralicé la definición de proyectos y stack en un objeto JSON filtrable por rol profesional.",
                "Al cambiar de perfil en la barra superior, el DOM se actualiza de forma reactiva sin recargar la página.",
                "Valido la consistencia de estilos con Tailwind CSS logrando tiempos de carga inferiores a 200 ms."
            ],
            "question": "¿Para interfaces interactivas ligeras preferís JavaScript modular sin dependencias o integráis un framework desde el inicio?"
        },
        {
            "pill_id": "interactivecv_theme_fouc_prevention",
            "category": "Frontend y Rendimiento",
            "topic_track": "programacion",
            "source_file": "index.html",
            "target_symbol": "matchMedia",
            "headline": "Eliminar el parpadeo de tema (FOUC) en SPAs mediante evaluación en el HEAD",
            "context": (
                "Cuando una página web evalúa el modo oscuro dentro de DOMContentLoaded o mediante scripts asíncronos, "
                "el usuario sufre un destello blanco molesto antes de que los estilos oscuros lleguen a aplicarse."
            ),
            "lead_in": "En el encabezado de index.html aislé la comprobación de color antes de pintar el DOM:",
            "bullets": [
                "Ejecuto un script síncrono ultra-ligero en el head consultando window.matchMedia y localStorage.",
                "Añado la clase dark a documentElement antes de que el navegador procese el cuerpo de la página.",
                "Garantizo coherencia visual instantánea sin importar la velocidad de renderizado del dispositivo."
            ],
            "question": "¿Qué técnica soléis emplear para evitar el flash de estilos en aplicaciones frontend sin SSR?"
        },
        {
            "pill_id": "interactivecv_chartjs_responsive_canvas",
            "category": "Visualización y Canvas",
            "topic_track": "programacion",
            "source_file": "index.html",
            "target_symbol": "Chart",
            "headline": "Gráficos radar reactivos en Canvas con adaptación dinámica a cambios de tema",
            "context": (
                "Al cambiar entre tema claro y oscuro, los lienzos HTML5 Canvas de librerías como Chart.js mantienen los "
                "colores originales de sus ejes, volviendo el gráfico ilegible contra el nuevo fondo."
            ),
            "lead_in": "En index.html orquesté la sincronización de temas con la capa Canvas:",
            "bullets": [
                "Configuré paletas tipadas para ejes y rejillas vinculadas al observador de mutaciones del tema.",
                "Actualizo las propiedades de la instancia de Chart.js dinámicamente evitando recrear el canvas desde cero.",
                "Ajusto fuentes monoespaciadas legibles tanto en pantallas móviles como en monitores de escritorio."
            ],
            "question": "¿Cómo sincronizáis elementos gráficos en Canvas cuando el usuario conmuta el modo oscuro en caliente?"
        },
    ],
    "LawLab": [
        {
            "pill_id": "lawlab_client_server_contracts",
            "category": "Arquitectura y Contratos API",
            "topic_track": "programacion",
            "source_file": "backend-api/main.py",
            "target_symbol": "def ",
            "headline": "Separar una app nativa en SwiftUI del motor en Python mediante contratos OpenAPI",
            "context": (
                "El reto técnico principal del proyecto era combinar la fluidez de una interfaz nativa de escritorio en macOS "
                "con las librerías de análisis documental de Python sin acoplar ambos entornos."
            ),
            "lead_in": "En backend-api/main.py diseñé una arquitectura cliente-servidor desacoplada:",
            "bullets": [
                "Encapsulé todo el procesamiento en una API REST con FastAPI dentro de Docker mediante contratos JSON tipados.",
                "Utilizo el esquema OpenAPI (/docs) como contrato único entre los modelos de SwiftUI y el backend Python.",
                "Puedo iterar sobre los algoritmos del servidor sin necesidad de recompilar ni redistribuir la app de macOS."
            ],
            "question": "¿Cómo soléis estructurar la comunicación cuando combináis una interfaz nativa (Swift/Kotlin) con lógica en Python?"
        },
        {
            "pill_id": "lawlab_async_document_ingestion",
            "category": "Procesamiento Asíncrono",
            "topic_track": "programacion",
            "source_file": "backend-api/ingest.py",
            "target_symbol": "def ",
            "headline": "Extracción y limpieza de textos jurídicos extensos en Python sin bloquear la API",
            "context": (
                "Procesar sentencias y documentos legales en PDF de cientos de páginas mediante llamadas bloqueantes en FastAPI "
                "satura los workers HTTP y dispara la latencia de las peticiones concurrentes."
            ),
            "lead_in": "En backend-api/ingest.py desacoplé la extracción en tareas no bloqueantes:",
            "bullets": [
                "Delego el parseo pesado de PDFs a un pool de procesos secundarios manteniendo la API reactiva.",
                "Normalizo caracteres especiales, saltos de línea irregulares y notas al pie antes de indexar.",
                "Divido el texto en fragmentos semánticos con metadatos de página para su posterior consulta."
            ],
            "question": "¿Cómo abordáis el parseo de documentos extensos para no comprometer el tiempo de respuesta de vuestras APIs?"
        },
        {
            "pill_id": "lawlab_boe_xml_sync_pipeline",
            "category": "Sistemas y Resiliencia",
            "topic_track": "sistemas",
            "source_file": "backend-api/sync_legislation.py",
            "target_symbol": "def ",
            "headline": "Pipeline de sincronización periódica con boletines oficiales tolerante a cortes de red",
            "context": (
                "Los servicios de boletines oficiales pueden sufrir microcortes o devolver respuestas parciales cuando se "
                "ejecutan sincronizaciones programadas de madrugada."
            ),
            "lead_in": "En backend-api/sync_legislation.py implementé un recolector con reanudación por cursor:",
            "bullets": [
                "Valido esquemas XML antes de persistir las disposiciones en la base de datos.",
                "Guardo el último identificador procesado para reanudar el trabajo exactamente en el punto de fallo.",
                "Ejecuto el script en un contenedor Docker con políticas de reinicio y logs estructurados."
            ],
            "question": "¿Qué estrategias de tolerancia a fallos aplicáis al sincronizar periódicamente datos desde APIs públicas?"
        },
    ],
    "GeminiJobBot": [
        {
            "pill_id": "geminijobbot_idempotent_sqlite",
            "category": "Backend y Persistencia",
            "topic_track": "programacion",
            "source_file": "src/orchestrator.py",
            "target_symbol": "def ",
            "headline": "Garantizar la idempotencia en pipelines programados apoyándose en SQLite",
            "context": (
                "En cualquier proceso periódico de extracción y análisis, volver a procesar elementos ya evaluados en ciclos "
                "anteriores desperdicia recursos computacionales y genera notificaciones duplicadas."
            ),
            "lead_in": "En src/orchestrator.py aseguré la idempotencia de cada ejecución antes de lanzar llamadas costosas:",
            "bullets": [
                "Genero una clave canónica por cada registro antes de invocar la fase de evaluación.",
                "Si el identificador ya existe en la base de datos SQLite local, el elemento se descarta en milisegundos.",
                "Aplico tiempos de espera variables (jitter) entre peticiones para evitar patrones de tráfico rígidos."
            ],
            "question": "¿Soléis apoyaros en SQLite para garantizar la idempotencia en pipelines autónomos o preferís otra capa de persistencia?"
        },
        {
            "pill_id": "geminijobbot_multimodal_dom_pruning",
            "category": "Optimización y DOM",
            "topic_track": "programacion",
            "source_file": "src/orchestrator.py",
            "target_symbol": "def ",
            "headline": "Podar el árbol DOM antes del análisis semántico para ahorrar un 80% de tokens",
            "context": (
                "Enviar documentos HTML completos con miles de nodos a modelos de lenguaje eleva costes, satura las ventanas "
                "de contexto y alarga el tiempo de inferencia de segundos a casi medio minuto."
            ),
            "lead_in": "En src/orchestrator.py estructuré un podado selectivo del DOM:",
            "bullets": [
                "Elimino nodos invisibles, scripts, estilos CSS y SVGs decorativos antes de serializar.",
                "Conservo exclusivamente etiquetas de interacción (inputs, botones y enlaces) y textos contextuales.",
                "Reduzco payloads de medio megabyte a menos de 40 KB manteniendo intacta la semántica del formulario."
            ],
            "question": "¿Qué técnicas de limpieza de HTML utilizáis antes de procesar páginas web con modelos de lenguaje?"
        },
        {
            "pill_id": "geminijobbot_backoff_rate_limit_controller",
            "category": "Control de Tráfico y Cuotas",
            "topic_track": "sistemas",
            "source_file": "src/app.py",
            "target_symbol": "def ",
            "headline": "Control matemático de cuotas de API y exponential backoff ante respuestas 429",
            "context": (
                "Las capas gratuitas de APIs de inferencia aplican cuotas por minuto estrictas; si el orquestador no calcula "
                "los intervalos de espera, una ráfaga corta aborta todo el ciclo programado."
            ),
            "lead_in": "En src/app.py implementé un limitador de ritmo con ventana deslizante:",
            "bullets": [
                "Monitorizo el recuento de llamadas por minuto y pauso las peticiones antes de alcanzar el tope.",
                "Interpreto cabeceras Retry-After aplicando un factor aleatorio de dispersión para evitar tormentas de peticiones.",
                "Si la cuota diaria se agota, el bot entra en modo reposo ordenado sin provocar excepciones no controladas."
            ],
            "question": "¿Preferís limitadores tipo token bucket en local o gestionar reactivamente los códigos 429 de las APIs?"
        },
    ],
    "PolyPrec": [
        {
            "pill_id": "polyprec_ws_reconnect",
            "category": "AsyncIO y WebSockets",
            "topic_track": "programacion",
            "source_file": "poly-football-arb/src/ws_client.py",
            "target_symbol": "async def",
            "headline": "Reconexión resiliente y desacoplamiento de dominio en clientes WebSocket con AsyncIO",
            "context": (
                "Al consumir flujos de datos en tiempo real durante horas, cualquier microcorte de red o cierre inesperado del "
                "servidor detiene la lectura si el cliente no gestiona el ciclo de reconexión y la validación del heartbeat."
            ),
            "lead_in": "En poly-football-arb/src/ws_client.py estructuré el cliente asíncrono separando responsabilidades:",
            "bullets": [
                "Implementé un bucle de reconexión con control de ping/pong y captura aislada de caídas de socket.",
                "Desacoplé el parseo del mensaje JSON de la lógica de negocio para poder testear las reglas en frío con Pytest.",
                "Si el canal deja de responder, se reinicia la suscripción limpia sin tumbar el proceso principal."
            ],
            "question": "¿Qué patrón os ha resultado más fiable en Python con AsyncIO para mantener WebSockets estables a largo plazo?"
        },
        {
            "pill_id": "polyprec_inmemory_orderbook_arbitrage",
            "category": "Baja Latencia y Concurrencia",
            "topic_track": "programacion",
            "source_file": "poly-football-arb/src/monitor.py",
            "target_symbol": "def ",
            "headline": "Evaluación de spreads en memoria con latencia inferior a 5 milisegundos en Python",
            "context": (
                "Al procesar cotizaciones en vivo para detectar discrepancias, persistir cada actualización en base de datos "
                "introduce demoras de I/O que hacen perder la ventana de oportunidad."
            ),
            "lead_in": "En poly-football-arb/src/monitor.py mantuve el libro de cotizaciones en estructuras puras de memoria:",
            "bullets": [
                "Almaceno el estado más reciente en diccionarios indexados por ID de evento con acceso en tiempo constante O(1).",
                "Calculo márgenes matemáticos mediante funciones puras sin bloqueos globales de concurrencia.",
                "Delego el volcado de alertas históricas a un hilo en segundo plano para no demorar el hilo de eventos."
            ],
            "question": "¿Cómo evitáis que las escrituras a disco o logs degraden el rendimiento en flujos de baja latencia?"
        },
        {
            "pill_id": "polyprec_heartbeat_deadmanswitch",
            "category": "Redes y Resiliencia",
            "topic_track": "sistemas",
            "source_file": "poly-football-arb/src/ws_client.py",
            "target_symbol": "def ",
            "headline": "Watchdog con Dead Man's Switch para detectar conexiones WebSocket silenciosas (zombies)",
            "context": (
                "Un socket TCP puede quedar en un estado semi-abierto tras un corte en la infraestructura del proveedor, "
                "dejando al cliente esperando paquetes indefinidamente sin emitir un evento de desconexión."
            ),
            "lead_in": "En poly-football-arb/src/ws_client.py implementé un temporizador de pulso activo:",
            "bullets": [
                "Envío tramas ping periódicas y exijo un acuse pong dentro de un umbral temporal riguroso.",
                "Si el servidor no responde en 15 segundos, fuerzo el cierre inmediato del socket con close explícito.",
                "Reinicio el handshake desde cero garantizando que el pipeline nunca quede congelado en silencio."
            ],
            "question": "¿Cómo detectáis conexiones caídas cuando el sistema operativo no recibe tramas TCP RST o FIN?"
        },
    ],
    "GaBookAutoDownloader": [
        {
            "pill_id": "gabook_multi_mirror_failover",
            "category": "Tolerancia a fallos",
            "topic_track": "programacion",
            "source_file": "src/gabook/services/book_client.py",
            "target_symbol": "def ",
            "headline": "Patrón failover multi-servidor para absorber caídas de servicios externos en Python",
            "context": (
                "Acoplar un servicio a un único dominio externo convierte cualquier caída temporal o degradación de latencia "
                "ajena en un fallo directo de cara al usuario final."
            ),
            "lead_in": "En src/gabook/services/book_client.py apliqué tolerancia a fallos por rotación de mirrors:",
            "bullets": [
                "Mantengo un listado priorizado de servidores espejo evaluados con timeouts estrictos.",
                "Ante cualquier error de conexión o latencia excesiva, el cliente conmuta automáticamente al siguiente nodo.",
                "La capa de interfaz en Telegram queda totalmente aislada de qué servidor resolvió finalmente la consulta."
            ],
            "question": "¿Cómo soléis implementar failover o circuit breakers cuando integráis servicios externos inestables?"
        },
        {
            "pill_id": "gabook_kindle_size_and_cleanup",
            "category": "Higiene y Recursos",
            "topic_track": "sistemas",
            "source_file": "src/gabook/bot.py",
            "target_symbol": "def ",
            "headline": "Control estricto de tamaño y limpieza automática de temporales en bots de Telegram",
            "context": (
                "En entornos gratuitos con disco muy limitado, dejar archivos EPUB temporales acumulados tras cada descarga "
                "termina llenando el almacenamiento y bloqueando el bot."
            ),
            "lead_in": "En src/gabook/bot.py blindé el ciclo de vida de cada documento:",
            "bullets": [
                "Valido el peso máximo antes de adjuntar archivos hacia correo Kindle o chats de Telegram.",
                "Envuelvo cada envío en bloques de limpieza garantizada para borrar el temporal al instante.",
                "Verifico integridad de cabecera EPUB antes de aceptar una descarga desde mirrors externos."
            ],
            "question": "¿Qué prácticas seguís para evitar fugas de disco en microservicios gratuitos o con almacenamiento limitado?"
        },
        {
            "pill_id": "gabook_gmail_imap_push_listener",
            "category": "Sistemas y Protocolos",
            "topic_track": "sistemas",
            "source_file": "src/gabook/services/gmail_monitor.py",
            "target_symbol": "def ",
            "headline": "Monitoreo eficiente de buzones IMAP con IDLE para verificar correos sin polling continuo",
            "context": (
                "Hacer peticiones HTTP o consultas de correo cada pocos segundos para comprobar enlaces de verificación "
                "desperdicia ancho de banda y arriesga bloqueos por saturar las cuotas del proveedor."
            ),
            "lead_in": "En src/gabook/services/gmail_monitor.py configuré un listener con extensión IMAP IDLE:",
            "bullets": [
                "Mantengo un socket en reposo que recibe notificaciones push instantáneas del servidor de correo.",
                "Filtro por remitente y asunto directamente en el servidor antes de descargar el cuerpo del mensaje.",
                "Extraigo el enlace de confirmación con expresiones regulares y lo proceso sin intervención humana."
            ],
            "question": "¿Utilizáis IMAP IDLE para automatizaciones con correo o preferís ganchos webhook mediante APIs REST?"
        },
        {
            "pill_id": "gabook_atomic_user_state_store",
            "category": "Persistencia Concurrente",
            "topic_track": "programacion",
            "source_file": "src/gabook/services/user_manager.py",
            "target_symbol": "def ",
            "headline": "Persistencia JSON atómica con bloqueo cooperativo para evitar corrupción en microservicios",
            "context": (
                "Cuando múltiples usuarios interactúan simultáneamente con un bot, escrituras concurrentes sobre un único "
                "archivo de configuración pueden truncar el contenido o dejar el JSON inservible."
            ),
            "lead_in": "En src/gabook/services/user_manager.py implementé escrituras atómicas protegidas:",
            "bullets": [
                "Uso un bloqueo threading.Lock para serializar las operaciones de guardado entre distintos hilos.",
                "Escribo a un archivo auxiliar temporal y realizo un reemplazo atómico mediante os.replace.",
                "Si la máquina sufre un corte de energía en mitad del guardado, el estado anterior permanece intacto."
            ],
            "question": "¿Qué estrategia aplicáis para persistir configuraciones locales sin recurrir a una base de datos externa?"
        },
    ],
    "BtcBriefing_iOS_ShortCut": [
        {
            "pill_id": "btcbriefing_api_aggregation",
            "category": "APIs y Atajos iOS",
            "topic_track": "programacion",
            "source_file": "main.py",
            "target_symbol": "def ",
            "headline": "Integrar un agregador REST en Python directamente con Atajos nativos de iOS",
            "context": (
                "Para automatizar informes diarios en el móvil no siempre hace falta desarrollar una aplicación nativa completa "
                "si expones un endpoint ligero con un contrato JSON bien estructurado."
            ),
            "lead_in": "En main.py diseñé el flujo para conectarlo directamente con Atajos de iOS:",
            "bullets": [
                "El script agrega métricas de múltiples APIs públicas y devuelve una respuesta JSON normalizada.",
                "Gestiono timeouts individuales por fuente para que un fallo parcial no bloquee el informe completo.",
                "Un pipeline en GitHub Actions valida la calidad del código en cada cambio antes de actualizar producción."
            ],
            "question": "¿Habéis utilizado Atajos de iOS o integraciones ligeras similares para consumir vuestros propios scripts en Python?"
        },
        {
            "pill_id": "btcbriefing_resilient_timeout_budget",
            "category": "Resiliencia en Red",
            "topic_track": "programacion",
            "source_file": "main.py",
            "target_symbol": "def ",
            "headline": "Presupuesto de tiempo (Timeout Budget) al agregar múltiples APIs públicas en paralelo",
            "context": (
                "Al recopilar datos de varios proveedores externos en una misma ejecución, la degradación de uno solo "
                "puede provocar que el script agote el timeout global del cliente móvil."
            ),
            "lead_in": "En main.py definí un presupuesto estricto de espera distribuido por fuente:",
            "bullets": [
                "Asigno límites temporales independientes por consulta evitando que un servicio lento bloquee a los demás.",
                "Si una fuente no responde en tiempo, degrado el informe devolviendo el último valor conocido o fallback.",
                "La respuesta JSON se garantiza siempre en menos de 2.5 segundos para no interrumpir el atajo de iOS."
            ],
            "question": "¿Cómo gestionáis presupuestos temporales al integrar múltiples APIs dependientes en un único flujo?"
        },
        {
            "pill_id": "btcbriefing_docker_minimal_scratch",
            "category": "Contenedores y Docker",
            "topic_track": "sistemas",
            "source_file": "Dockerfile",
            "target_symbol": "FROM",
            "headline": "Construcción de imágenes Docker ultraligeras en Alpine para scripts de ejecución periódica",
            "context": (
                "Emplear imágenes base pesadas de Python para scripts que solo se ejecutan una vez al día consume espacio "
                "innecesario y ralentiza las actualizaciones en servidores con almacenamiento limitado."
            ),
            "lead_in": "En el Dockerfile optimicé las capas de compilación logrando una imagen de apenas 55 MB:",
            "bullets": [
                "Uso Python Alpine como base eliminando herramientas de compilación una vez instalados los paquetes.",
                "Configuro el proceso para correr bajo un usuario sin privilegios root mejorando la postura de seguridad.",
                "Optimizo el orden de directivas COPY para aprovechar al máximo la caché de capas de Docker."
            ],
            "question": "¿Qué imagen base preferís en producción para scripts de Python ligeros: Alpine, Slim o Distroless?"
        },
    ],
    "GTA6Channel": [
        {
            "pill_id": "gta6_video_render_fit_sync",
            "category": "Procesado Multimedia y FFmpeg",
            "topic_track": "programacion",
            "source_file": "src/video_editor.py",
            "target_symbol": "render_final_video",
            "code_focus": "def render_final_video",
            "headline": "Sincronizar audio TTS y vídeo 16:9 a 9:16 con VideoToolbox sin recortes laterales",
            "context": (
                "Al adaptar clips horizontales a formato vertical con doblaje sintético, el recorte central agresivo "
                "amputa más del 50% de la escena y cortar el vídeo antes de que acabe la locución deja frases truncadas."
            ),
            "lead_in": "En src/video_editor.py aseguré fidelidad visual y temporal en cada render:",
            "bullets": [
                "Sondeo la duración real de vídeo y audio para congelar el último frame con tpad si la voz excede al clip.",
                "Conservé el encuadre panorámico completo dentro del lienzo 9:16 evitando perder contexto en pantalla.",
                "Forcé codificación hardware h264_videotoolbox con hilos acotados para no degradar otros procesos del host."
            ],
            "question": "¿Preferís aceleración hardware específica como VideoToolbox o libx264 cuando automatizáis renders con FFmpeg?"
        },
        {
            "pill_id": "gta6_compliance_auditor",
            "category": "Reglas y Auditoría Automática",
            "topic_track": "programacion",
            "source_file": "src/compliance_auditor.py",
            "target_symbol": "ComplianceAuditor",
            "code_focus": "class ComplianceAuditor",
            "headline": "Diseñar un auditor previo de cumplimiento y deduplicación antes de publicar",
            "context": (
                "En pipelines multimedia automatizados, publicar contenido duplicado o con metadatos incompletos genera "
                "penalizaciones inmediatas y ruido innecesario en el canal."
            ),
            "lead_in": "En src/compliance_auditor.py añadí una compuerta determinista previa a cualquier subida:",
            "bullets": [
                "Verifico fuentes de origen, duración óptima y atribución obligatoria al creador antes de renderizar.",
                "Registro firmas de títulos recientes para impedir que dos variantes del mismo clip entren en cola.",
                "Superviso el rendimiento de las últimas publicaciones para aislar el canal ante caídas anómalas de alcance."
            ],
            "question": "¿Qué validaciones automáticas consideráis imprescindibles antes de permitir que un job publique contenido?"
        },
        {
            "pill_id": "gta6_dynamic_audio_ducking",
            "category": "Filtros de Audio en FFmpeg",
            "topic_track": "programacion",
            "source_file": "src/video_editor.py",
            "target_symbol": "def ",
            "headline": "Audio Ducking reactivo con filtros FFmpeg para equilibrar voz sintética y sonido de juego",
            "context": (
                "Mezclar una pista de voz en off generada por IA con el audio ambiental de un gameplay a volumen constante "
                "hace que las explicaciones queden inaudibles cuando hay ruidos fuertes o explosiones en el juego."
            ),
            "lead_in": "En src/video_editor.py apliqué atenuación sidechain sobre el flujo de audio:",
            "bullets": [
                "Atenúo el audio ambiental al 18% automáticamente durante los periodos en los que la voz está activa.",
                "Aplico curvas de ataque y decaimiento suaves para que la transición sonora no resulte abrupta.",
                "Integro el grafo de filtros complejos en la misma pasada de codificación para evitar pasos intermedios."
            ],
            "question": "¿Automatizáis filtros complejos de audio con FFmpeg en Python o preferís librerías de procesado previas?"
        },
        {
            "pill_id": "gta6_thermal_throttling_courtesy_mode",
            "category": "Coexistencia y Sistemas",
            "topic_track": "sistemas",
            "source_file": "src/video_editor.py",
            "target_symbol": "def ",
            "headline": "Modo cortesía de CPU: auto-limitación de hilos en hosts que ejecutan cálculo financiero",
            "context": (
                "En un servidor de producción que comparte hardware con modelos cuantitativos sensibles, una tarea de vídeo "
                "descontrolada puede estrangular la CPU por temperatura y degradar los algoritmos principales."
            ),
            "lead_in": "En src/video_editor.py implementé una compuerta de cortesía antes de renderizar:",
            "bullets": [
                "Compruebo mediante pgrep si hay procesos cuantitativos en curso antes de asignar hilos a FFmpeg.",
                "Si el nodo está ocupado, reduzco el render a 1 solo hilo y cedo prioridad con nice 15 en segundo plano.",
                "Fuerzo recolección de basura con gc.collect al terminar cada vídeo para devolver buffers al sistema operativo."
            ],
            "question": "¿Cómo gestionáis la coexistencia pacífica entre tareas batch pesadas y servicios críticos en el mismo host?"
        },
    ],
    "GaTDSEQ": [
        {
            "pill_id": "gatdseq_confidence_gate",
            "category": "Arquitectura y Testing en Python",
            "topic_track": "programacion",
            "source_file": "core/strategy.py",
            "target_symbol": "calculate_confidence_score",
            "code_focus": "def calculate_confidence_score",
            "headline": "Aislar lógica de decisión en funciones puras para testear rápido con Pytest",
            "context": (
                "Cuando las reglas de decisión están mezcladas con llamadas de red, ficheros o base de datos, "
                "cada test unitario se vuelve lento, frágil y difícil de depurar ante casos límite."
            ),
            "lead_in": "En core/strategy.py separé la lógica pura de evaluación del resto de la infraestructura:",
            "bullets": [
                "Extraigo el cálculo a funciones puras deterministas sin efectos secundarios ni acceso a red.",
                "Combino factores normalizados con pesos claros en lugar de anidar condiciones rígidas.",
                "Valido cada rama y caso extremo en milisegundos con suites unitarias en Pytest."
            ],
            "question": "¿Cómo separáis la lógica pura de dominio de la capa de E/S para mantener tests rápidos y deterministas?"
        },
        {
            "pill_id": "gatdseq_walkforward_gates",
            "category": "Testing y Validación",
            "topic_track": "programacion",
            "source_file": "backtesting/research_lab.py",
            "target_symbol": "check_go_nogo_gates",
            "code_focus": "def check_go_nogo_gates",
            "headline": "Validar algoritmos en Python con baterías de regresión y pruebas de estrés automatizadas",
            "context": (
                "Probar un motor de procesamiento únicamente contra un escenario feliz oculta fallos ante datos ruidosos "
                "o casos atípicos cuando pasa a ejecución real."
            ),
            "lead_in": "En backtesting/research_lab.py implementé compuertas automáticas de validación antes de promover cambios:",
            "bullets": [
                "Evalúo el algoritmo por ventanas temporales independientes para verificar estabilidad fuera de muestra.",
                "Simulo escenarios degradados y eliminación de outliers antes de dar una build por válida.",
                "Bloqueo automáticamente cualquier configuración que no supere los umbrales mínimos de Pytest."
            ],
            "question": "¿Qué pruebas de estrés o regresión aplicáis para asegurar que un cambio de lógica no rompe casos reales?"
        },
        {
            "pill_id": "gatdseq_vectorized_signal_pipeline",
            "category": "Rendimiento y NumPy",
            "topic_track": "programacion",
            "source_file": "backtesting/engine.py",
            "target_symbol": "def ",
            "headline": "Acelerar simulaciones sustituyendo bucles iterativos por operaciones vectorizadas",
            "context": (
                "Iterar fila a fila con bucles for en Python sobre series de cientos de miles de registros temporales toma minutos, "
                "haciendo inviable el ajuste fino de parámetros algorítmicos en pruebas continuas."
            ),
            "lead_in": "En backtesting/engine.py rediseñé el motor de simulación con operaciones matriciales:",
            "bullets": [
                "Transformo las condiciones de entrada y salida en arrays booleanos calculados en bloque por NumPy.",
                "Reduzco los tiempos de simulación de 45 segundos a menos de 300 milisegundos por corrida.",
                "Calculo métricas de drawdown acumulado directamente sobre los vectores sin penalizar la memoria."
            ],
            "question": "¿Qué herramientas preferís para acelerar procesamiento numérico en Python: NumPy, Polars o extensiones C?"
        },
        {
            "pill_id": "gatdseq_strict_drawdown_circuit_breaker",
            "category": "Resiliencia y Control de Riesgo",
            "topic_track": "programacion",
            "source_file": "core/strategy.py",
            "target_symbol": "def ",
            "headline": "Circuit breaker algorítmico para abortar ejecuciones ante anomalías estadísticas en vivo",
            "context": (
                "En sistemas autónomos que procesan datos numéricos en vivo, datos corruptos o anomalías en la fuente "
                "pueden inducir decisiones erróneas encadenadas si no existe un mecanismo de paro de emergencia."
            ),
            "lead_in": "En core/strategy.py integré un freno preventivo de seguridad:",
            "bullets": [
                "Superviso la desviación típica en ventanas recientes de cálculo antes de emitir cualquier orden.",
                "Si los valores exceden tres desviaciones estándar, el sistema congela operaciones automáticamente.",
                "Envío un volcado de diagnóstico estructurado a Telegram para revisión manual antes de reactivar."
            ],
            "question": "¿Qué patrones de disyuntor (circuit breaker) consideráis obligatorios en automatizaciones críticas?"
        },
    ],
    "DevOps": [
        {
            "pill_id": "devops_psutil_collector",
            "category": "Sistemas Linux/Unix y Python",
            "topic_track": "sistemas",
            "source_file": "collector/monitor.py",
            "target_symbol": "collect_metrics",
            "code_focus": "def collect_metrics",
            "headline": "Recolectar métricas de CPU, RAM y procesos del sistema en Python tolerando fallos de permisos",
            "context": (
                "Al monitorizar procesos del sistema operativo con psutil en segundo plano, un proceso puede terminar en "
                "mitad de la iteración o pertenecer a root y lanzar excepciones si no se manejan bien las señales del kernel."
            ),
            "lead_in": "En collector/monitor.py blindé la recolección periódica de telemetría del host:",
            "bullets": [
                "Caliento psutil.cpu_percent antes del bucle y capturo NoSuchProcess y AccessDenied por proceso.",
                "Ordeno los procesos por uso de CPU de forma segura incluso si algún descriptor devuelve None.",
                "Persisto snapshots estructurados en JSON Lines para que la API los sirva sin bloquear al recolector."
            ],
            "question": "¿Qué enfoque preferís para monitorizar procesos y recursos en hosts Linux/macOS: scripts ligeros propios o agentes externos?"
        },
        {
            "pill_id": "devops_docker_api_separation",
            "category": "Docker, Sistemas y FastAPI",
            "topic_track": "sistemas",
            "source_file": "api/api.py",
            "target_symbol": "metrics",
            "code_focus": "def read_logs",
            "headline": "Desacoplar un recolector de métricas del sistema de su API REST en Docker Compose",
            "context": (
                "Acoplar el servidor HTTP que consulta telemetría dentro del mismo bucle que muestrea el kernel provoca "
                "contención de lecturas y complica escalar o reiniciar ambos procesos por separado."
            ),
            "lead_in": "En system-monitor-cli separé el recolector de sistemas y el servicio web en contenedores distintos:",
            "bullets": [
                "El módulo collector muestrea CPU, disco y red de forma aislada volcando logs rotables en JSONL.",
                "La API en FastAPI lee las últimas N muestras tolerando FileNotFoundError en arranques limpios.",
                "Todo el stack levanta en un comando con Docker Compose y Makefile incluyendo tests automatizados."
            ],
            "question": "¿Soléis separar servicios de recolección de sistema y APIs de consulta en contenedores distintos desde el inicio?"
        },
        {
            "pill_id": "devops_log_rotation_bounded_disk",
            "category": "Almacenamiento y Observabilidad",
            "topic_track": "sistemas",
            "source_file": "collector/monitor.py",
            "target_symbol": "def ",
            "headline": "Rotación circular de telemetría en JSON Lines con límite estricto de espacio en disco",
            "context": (
                "Un script de monitorización en segundo plano que acumula métricas de sistema sin rotación termina llenando "
                "la partición raíz en servidores pequeños, provocando fallos en cadena en otros servicios."
            ),
            "lead_in": "En collector/monitor.py configuré rotación de archivos acotada por cuota:",
            "bullets": [
                "Verifico el tamaño del fichero JSONL antes de cada escritura y roto hacia .old al superar el umbral fijado.",
                "Mantengo un histórico máximo garantizando que el uso de almacenamiento nunca exceda la cuota asignada.",
                "Permito lecturas concurrentes sin bloqueos de archivo para que la API consulte las muestras en tiempo real."
            ],
            "question": "¿Gestionáis la rotación de métricas desde la propia aplicación en Python o delegáis en logrotate del sistema operativo?"
        },
        {
            "pill_id": "devops_clean_sigterm_handling",
            "category": "Señales POSIX y Contenedores",
            "topic_track": "programacion",
            "source_file": "collector/monitor.py",
            "target_symbol": "def ",
            "headline": "Captura limpia de señales POSIX (SIGTERM/SIGINT) para paradas ordenadas en Docker",
            "context": (
                "Al detener un contenedor con docker stop, si el script en Python no intercepta la señal SIGTERM, el demonio "
                "de Docker lo mata de forma forzosa con SIGKILL tras 10 segundos, dejando buffers incompletos."
            ),
            "lead_in": "En collector/monitor.py registré manejadores de señales para una salida ordenada:",
            "bullets": [
                "Intercepto SIGTERM y SIGINT cambiando un flag atómico que permite completar la iteración en curso.",
                "Vuelco la última muestra de telemetría a disco y cierro descriptores antes de invocar sys.exit(0).",
                "El contenedor se apaga limpiamente en menos de 300 ms sin esperar el timeout forzoso de Docker."
            ],
            "question": "¿Registráis siempre manejadores de señales POSIX en scripts de Python dentro de contenedores?"
        },
    ],
    "mando-tv": [
        {
            "pill_id": "mandotv_xiaomi_sleep_sync",
            "category": "Sistemas Embebidos y ADB",
            "topic_track": "sistemas",
            "source_file": "mando_tv/xiaomi.py",
            "target_symbol": "apagar_xiaomi",
            "code_focus": "def apagar_xiaomi",
            "headline": "Evitar desincronización entre control remoto por red (ADB) y mando físico en Android TV",
            "context": (
                "Forzar apagados falsos bajando el backlight a cero mientras el sistema sigue despierto provoca que el "
                "botón físico Power pierda sincronía y deje el televisor con la pantalla en negro."
            ),
            "lead_in": "En mando_tv/xiaomi.py corregí el ciclo de energía usando eventos idempotentes nativos:",
            "bullets": [
                "Sustituí el toggle de encendido (keyevent 26) por eventos explícitos KEYCODE_SLEEP (223) y WAKEUP (224).",
                "Restauro ajustes limpios de retroiluminación y energía antes de dormir para respetar al mando físico.",
                "Cacheo el estado real de mWakefulness y brillo en ventana corta para no saturar adbd desde la UI."
            ],
            "question": "¿Os habéis topado alguna vez con estados fantasmas entre automatizaciones por red y controles físicos?"
        },
        {
            "pill_id": "mandotv_mac_arp_discovery",
            "category": "Redes LAN y Concurrencia",
            "topic_track": "sistemas",
            "source_file": "mando_tv/discovery.py",
            "target_symbol": "_elegir_ip_por_mac",
            "code_focus": "def _elegir_ip_por_mac",
            "headline": "Autodescubrimiento de dispositivos en LAN validando dirección MAC sobre tabla ARP",
            "context": (
                "Cuando el router asigna nuevas IPs por DHCP tras un reinicio, los scripts domóticos dejan de encontrar "
                "sus dispositivos si dependen de direcciones fijas en código."
            ),
            "lead_in": "En mando_tv/discovery.py resolví la resolución dinámica sin falsos positivos:",
            "bullets": [
                "Consulto la tabla ARP local y escaneo la subred /24 en paralelo solo fuera del lock principal.",
                "Verifico que la IP con el puerto abierto pertenezca exactamente a la MAC del televisor objetivo.",
                "Persisto la nueva IP en disco para arrancar directamente sin re-escaneos tras reiniciar el servidor."
            ],
            "question": "¿Cómo gestionáis el descubrimiento de dispositivos con DHCP dinámico en vuestras redes locales?"
        },
        {
            "pill_id": "mandotv_webos_ws_client_handshake",
            "category": "WebSockets y Protocolos IoT",
            "topic_track": "programacion",
            "source_file": "mando_tv/lg.py",
            "target_symbol": "def ",
            "headline": "Apretón de manos criptográfico y persistencia de token con Smart TVs LG en Python",
            "context": (
                "El protocolo SSAP de LG webOS exige autenticación mutua y aprobación en pantalla; si la clave de sesión "
                "no se preserva en disco, el televisor solicita permiso al usuario en cada pulsación del mando virtual."
            ),
            "lead_in": "En mando_tv/lg.py implementé la negociación persistente sobre WebSocket:",
            "bullets": [
                "Almaceno el client-key autorizado en un archivo local para reutilizarlo en conexiones posteriores.",
                "Envío las órdenes mediante tramas JSON asíncronas verificando la confirmación de entrega del televisor.",
                "Detecto pérdidas de enlace en la desconexión del socket para reconectar sin reiniciar el servidor HTTP."
            ],
            "question": "¿Cómo gestionáis el ciclo de vida de tokens y emparejamiento con dispositivos domóticos en red local?"
        },
        {
            "pill_id": "mandotv_wake_on_lan_magic_packet",
            "category": "Sockets y Redes Locales",
            "topic_track": "sistemas",
            "source_file": "mando_tv/wol.py",
            "target_symbol": "def ",
            "headline": "Construcción y difusión de tramas Wake-on-LAN sobre sockets UDP en Python puro",
            "context": (
                "Cuando un televisor entra en reposo profundo apaga su pila IP y deja de responder a HTTP o ADB; la única vía "
                "para despertarlo es emitir un paquete mágico a nivel de enlace de datos."
            ),
            "lead_in": "En mando_tv/wol.py construí el emisor de tramas mágicas sin requerir dependencias externas:",
            "bullets": [
                "Estructuro la trama concatenando 6 bytes 0xFF con la dirección MAC de la TV repetida 16 veces.",
                "Abro un socket UDP configurado con SO_BROADCAST para difundir hacia la dirección de difusión de la subred.",
                "Sondeo la disponibilidad de puertos tras el envío para confirmar que la interfaz de red despertó."
            ],
            "question": "¿Habéis implementado Wake-on-LAN en Python para encender equipos o televisores de forma remota?"
        },
    ],
}
CURATED_DEVLOG_PROJECTS: List[Dict[str, Any]] = [
    {
        "dir_name": "Tv-streamer",
        "repo_url": "https://github.com/gtrujillovdev-cyber/tv-streamer",
        "topic_track": "programacion",
        "focus_tier": 1,
        "target_file": "stream_manager.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "",
            "command": ["python3", "-m", "streamlit", "run", "app.py", "--server.port", "18505", "--server.headless", "true"],
            "port": 18505,
            "url_path": "/",
            "wait_seconds": 4.0,
            "click_selectors": [
                "summary:has-text('Asistente de Configuración Rápida')",
                "summary:has-text('Transmitir Archivo Directo')"
            ]
        },
        "display_name": "Tv-streamer — Servidor Multimedia Local y Google Cast en Red",
        "domain": "Redes Locales, Python y Docker",
        "tech_stack": ["Python", "Networking", "Docker", "macOS"],
        "project_intro": (
            "Tv-streamer es un servidor multimedia local que he desarrollado en Python con interfaz en Streamlit y soporte Docker "
            "para detectar dispositivos Google Cast en la red Wi-Fi y transmitir contenido desde macOS sin depender de cables ni configuración manual."
        ),
        "default_headline": "Creando un servidor de streaming local en Python para eliminar el cable HDMI",
        "default_context": (
            "Quería enviar vídeo desde mi Mac a la TV por la red local sin depender de cables HDMI ni configuraciones pesadas, "
            "así que diseñé Tv-streamer en Python."
        ),
        "default_learning": (
            "Autodescubrimiento Google Cast en LAN y chequeo previo de socket antes de iniciar el streaming."
        ),
        "fallback_snippet": (
            "# Gestión de reproducción local y descubrimiento Cast\n"
            "def start_cast_session(device_ip: str, media_url: str):\n"
            "    cast = pychromecast.Chromecast(device_ip)\n"
            "    cast.wait()\n"
            "    mc = cast.media_controller\n"
            "    mc.play_media(media_url, 'video/mp4')\n"
            "    mc.block_until_active()"
        ),
    },
    {
        "dir_name": "InteractiveCV",
        "topic_track": "programacion",
        "focus_tier": 1,
        "target_file": "index.html",
        "anchor_keyword": "script",
        "live_capture": {
            "mode": "static_server",
            "serve_dir": "dist",
            "port": 18912,
            "extra_views": [
                {
                    "scroll_y": 520,
                    "wait_seconds": 1.5
                }
            ]
        },
        "display_name": "InteractiveCV — CV Técnico Dinámico con Vite, Tailwind v4 y CI/CD",
        "domain": "Frontend con Vite, Tailwind CSS y GitHub Actions",
        "tech_stack": ["Vite", "TailwindCSS", "GitHubActions", "QA"],
        "project_intro": (
            "InteractiveCV es mi currículum técnico interactivo construido con JavaScript modular, Vite y Tailwind CSS v4, "
            "pensado para adaptar la visualización de proyectos y competencias según el perfil profesional (Backend Python, Sistemas/Ciberseguridad o QA) que busque el visitante."
        ),
        "default_headline": "Mi CV web interactivo con perfiles dinámicos y validación en GitHub Actions",
        "default_context": (
            "Como mi formación en DAM y mis proyectos abarcan Sistemas Linux/Ciberseguridad, Desarrollo en Python y QA, "
            "construí InteractiveCV para que quien visite mi CV pueda filtrar mi perfil según el rol técnico que busque."
        ),
        "default_learning": (
            "Migración a Vite + Tailwind v4 con pipeline en GitHub Actions que valida cada build automáticamente."
        ),
        "fallback_snippet": (
            "// Cambio dinámico de perfil técnico en InteractiveCV\n"
            "export function selectProfile(profileKey) {\n"
            "  const active = PROFILES[profileKey] || PROFILES.default;\n"
            "  renderSkills(active.skills);\n"
            "  renderProjects(active.projects);\n"
            "}"
        ),
    },
    {
        "dir_name": "JobSeeker",
        "repo_url": "https://github.com/gtrujillovdev-cyber/JobSeeker",
        "topic_track": "programacion",
        "focus_tier": 1,
        "target_file": "src/ats_analyzer.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["python3", "main.py", "--history"],
            "display_command": "python3 main.py --history",
            "terminal_title": "JobSeeker — Plataforma HR ATS & Historial de Actividad",
            "extra_views": [
                {
                    "mode": "terminal_command",
                    "cwd": "",
                    "command": [
                        "python3", "-c",
                        "from src.ats_analyzer import ATSAnalyzer; import json; "
                        "res = ATSAnalyzer.analyze_match('Backend Python & QA Automation Engineer', "
                        "'Buscamos perfil con Python, FastAPI, Docker, Linux, Pytest, GitHub Actions, SQL y CI/CD', "
                        "['Python', 'FastAPI', 'Docker', 'Linux', 'Pytest']); "
                        "print(json.dumps(res, indent=2, ensure_ascii=False))"
                    ],
                    "display_command": "python3 -m src.ats_analyzer --evaluate 'Backend Python & QA Automation Engineer'",
                    "terminal_title": "JobSeeker — Motor Analítico ATS (Taxonomía IT, Match Score & Gap Analysis)"
                }
            ]
        },
        "display_name": "JobSeeker — Plataforma HR ATS & Automatización de Candidaturas",
        "domain": "HR Tech, Análisis Semántico ATS, Python y Playwright",
        "tech_stack": ["Python", "Playwright", "HRTech", "ATS", "TelegramAPI"],
        "project_intro": (
            "JobSeeker es una plataforma de automatización y análisis técnico que he desarrollado en Python y Playwright para evaluar "
            "vacantes IT con un motor de compatibilidad ATS propio, adaptar candidaturas y gestionar publicaciones y networking con control en Telegram."
        ),
        "default_headline": "Diseñando un motor ATS en Python para evaluar vacantes y optimizar candidaturas",
        "default_context": (
            "Diseñé JobSeeker en Python para evaluar vacantes técnicas automáticamente mediante un motor analítico ATS "
            "que calcula el porcentaje de afinidad, detecta brechas de skills y gestiona alertas interactivas en Telegram."
        ),
        "default_learning": (
            "Clasificación por taxonomía IT en analyze_match, gap analysis y ponderación triple en el título de la oferta."
        ),
        "fallback_snippet": (
            "# Motor analítico ATS para cálculo de compatibilidad y brechas (gaps)\n"
            "analysis = ATSAnalyzer.analyze_match(job_title, job_desc, detected_stack)\n"
            "score = analysis['ats_score']  # 0-100%\n"
            "matched = analysis['matched_keywords']\n"
            "gaps = analysis['gaps']"
        ),
    },
    {
        "dir_name": "LawLab",
        "target_file": "backend-api/main.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "backend-api",
            "command": ["python3", "-m", "uvicorn", "main:app", "--port", "18008"],
            "port": 18008,
            "url_path": "/docs",
            "wait_seconds": 3.0,
            "click_selectors": [
                "div.opblock-summary"
            ]
        },
        "display_name": "LawLab — Backend en FastAPI + Cliente Nativo macOS en SwiftUI",
        "domain": "Arquitectura Cliente-Servidor con FastAPI, Docker y SwiftUI",
        "tech_stack": ["FastAPI", "Python", "SwiftUI", "Docker"],
        "project_intro": (
            "LawLab es una aplicación de análisis y gestión documental estructurada en dos capas: un backend de procesamiento en "
            "Python con FastAPI contenerizado en Docker y un cliente nativo de escritorio para macOS desarrollado en SwiftUI."
        ),
        "default_headline": "Conectando un backend en FastAPI (Docker) con una app nativa en SwiftUI",
        "default_context": (
            "En LawLab diseñé una arquitectura dividida en dos capas: una API en Python con FastAPI desplegada en Docker "
            "y una aplicación nativa de escritorio para macOS escrita en SwiftUI."
        ),
        "default_learning": (
            "Gestión reactiva con ObservableObject en Swift conectada a servicios FastAPI en Docker."
        ),
        "fallback_snippet": (
            "@app.post('/api/v1/analyze')\n"
            "async def analyze_document(payload: DocumentRequest):\n"
            "    result = await pipeline.run_extraction(payload.text)\n"
            "    return {'status': 'completed', 'data': result}"
        ),
    },
    {
        "dir_name": "GeminiJobBot",
        "target_file": "src/orchestrator.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "",
            "command": ["python3", "-m", "uvicorn", "src.app:app", "--port", "18099"],
            "port": 18099,
            "url_path": "/",
            "wait_seconds": 2.5,
            "extra_views": [
                {
                    "url_path": "/docs",
                    "wait_seconds": 2.0,
                    "click_selectors": ["div.opblock-summary"]
                }
            ]
        },
        "display_name": "GeminiJobBot — Descubrimiento de Ofertas y Control de Rate-Limit",
        "domain": "Python, Automatización y Resiliencia en Red",
        "tech_stack": ["Python", "SQLite", "Automation", "Backend"],
        "project_intro": (
            "GeminiJobBot es un orquestador backend desarrollado en Python, FastAPI y SQLite para monitorizar ofertas técnicas de empleo, "
            "filtrar requisitos frente a un perfil objetivo y exponer métricas de ejecución sin sobrecargar los portales de origen."
        ),
        "default_headline": "Evitando bloqueos en portales de empleo mediante búsqueda indexada y backoff",
        "default_context": (
            "Al construir GeminiJobBot comprobé que lanzar peticiones directas seguidas contra portales de empleo termina rápido en bloqueos por rate-limit."
        ),
        "default_learning": (
            "Descubrimiento por búsquedas indexadas en SQLite con tiempos de espera progresivos anti-bloqueo."
        ),
        "fallback_snippet": (
            "def run_discovery_cycle(queries: list[str]):\n"
            "    for q in queries:\n"
            "        results = search_proxy_index(q)\n"
            "        save_discovered_jobs(results)\n"
            "        time.sleep(random.uniform(3.5, 7.0))"
        ),
    },
    {
        "dir_name": "PolyPrec",
        "target_file": "poly-football-arb/src/ws_client.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "PolyPrec — Arquitectura WebSockets & Historial de Commits"
        },
        "display_name": "PolyPrec — Monitor en Tiempo Real con WebSockets Asíncronos",
        "domain": "Programación Asíncrona en Python, WebSockets y Testing",
        "tech_stack": ["Python", "WebSockets", "AsyncIO", "Pytest"],
        "project_intro": (
            "PolyPrec es un motor de monitorización en tiempo real construido sobre Python AsyncIO y WebSockets, diseñado para "
            "procesar flujos continuos de eventos de baja latencia, evaluar reglas de negocio y emitir alertas automáticas con cobertura de tests en Pytest."
        ),
        "default_headline": "Gestionando conexiones WebSocket en tiempo real con reconexión automática en Python",
        "default_context": (
            "En PolyPrec necesitaba escuchar múltiples flujos de datos en vivo al mismo tiempo sin que un corte de red puntual tumbara el proceso."
        ),
        "default_learning": (
            "Cliente asíncrono con reconexión automática en websockets, alertas en Telegram y tests en Pytest."
        ),
        "fallback_snippet": (
            "async def connect_and_listen(self):\n"
            "    async for ws in websockets.connect(self.uri, ping_interval=20):\n"
            "        try:\n"
            "            async for message in ws:\n"
            "                await self.handle_event(json.loads(message))\n"
            "        except websockets.ConnectionClosed:\n"
            "            continue"
        ),
    },
    {
        "dir_name": "GaBookAutoDownloader",
        "repo_url": "https://github.com/gtrujillovdev-cyber/GaBookAutoDownloader",
        "topic_track": "programacion",
        "focus_tier": 1,
        "target_file": "src/gabook/services/book_client.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "GaBookAutoDownloader — Historial de Commits & Arquitectura Multi-Mirror"
        },
        "display_name": "GaBookAutoDownloader — Motor de Búsqueda con Ranking y Failover",
        "domain": "Python, Tolerancia a Fallos y Arquitectura de Servicios",
        "tech_stack": ["Python", "Linux", "Automation", "Backend"],
        "project_intro": (
            "GaBookAutoDownloader es un servicio modular en Python con interfaz en Telegram pensado para localizar, puntuar por relevancia "
            "y descargar documentación técnica de forma automatizada integrando conmutación automática ante fallos de servidor."
        ),
        "default_headline": "Tolerancia a fallos multi-servidor y algoritmo de relevancia en Python",
        "default_context": (
            "En GaBookAutoDownloader busqué resolver un problema clásico: cuando dependes de servidores externos, tarde o temprano alguno cae o va lento."
        ),
        "default_learning": (
            "Ranking de resultados por relevancia y failover automático entre servidores espejo."
        ),
        "fallback_snippet": (
            "async def download_with_failover(mirrors: list[str], dest: Path) -> bool:\n"
            "    for mirror_url in mirrors:\n"
            "        try:\n"
            "            return await fetch_stream(mirror_url, dest)\n"
            "        except NetworkError:\n"
            "            continue\n"
            "    return False"
        ),
    },
    {
        "dir_name": "BtcBriefing_iOS_ShortCut",
        "repo_url": "https://github.com/gtrujillovdev-cyber/BtcBriefing_iOS_ShortCut",
        "topic_track": "programacion",
        "focus_tier": 2,
        "target_file": "main.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "BtcBriefing_iOS_ShortCut — Pipeline CI & Atajos de iOS"
        },
        "display_name": "BtcBriefing — Automatización en Python integrada con Atajos de iOS",
        "domain": "Python, APIs REST y CI con GitHub Actions",
        "tech_stack": ["Python", "APIs", "GitHubActions", "Automation"],
        "project_intro": (
            "BtcBriefing es un micro-servicio en Python validado con integración continua en GitHub Actions que agrega datos de "
            "múltiples APIs REST externas y entrega un resumen estructurado directamente en el iPhone mediante Atajos nativos de iOS."
        ),
        "default_headline": "Conectando scripts de Python con Atajos de iOS y control de calidad en CI",
        "default_context": (
            "Construí BtcBriefing_iOS_ShortCut para consultar varias APIs desde un script en Python y recibir el resumen directamente "
            "en mi iPhone al ejecutar un Atajo de iOS."
        ),
        "default_learning": (
            "Integración directa con Atajos de iOS y validación automática de linting en GitHub Actions."
        ),
        "fallback_snippet": (
            "def build_daily_briefing() -> dict:\n"
            "    metrics = fetch_market_snapshot()\n"
            "    sentiment = fetch_fear_and_greed_index()\n"
            "    return {'summary': format_for_ios(metrics, sentiment)}"
        ),
    },
    {
        "dir_name": "GTA6Channel",
        "repo_url": "https://github.com/gtrujillovdev-cyber/GTAVIHub",
        "topic_track": "programacion",
        "focus_tier": 2,
        "target_file": "src/video_editor.py",
        "anchor_keyword": "def render_final_video",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "GTA6Channel — Pipeline Editorial & VideoToolbox 24/7"
        },
        "display_name": "GTAVIHub — Pipeline Multimedia Automatizado en Python con FFmpeg",
        "domain": "Python, FFmpeg Hardware Encoding y Automatización 24/7",
        "tech_stack": ["Python", "FFmpeg", "VideoToolbox", "Backend", "Testing"],
        "project_intro": (
            "GTAVIHub es un pipeline de procesado multimedia 24/7 en Python que orquesta ingesta, generación de audio "
            "sincronizado, renderizado por hardware con FFmpeg/VideoToolbox y validación automática previa a publicación."
        ),
        "default_headline": "Sincronizar audio TTS y vídeo 16:9 a 9:16 con VideoToolbox sin recortes laterales",
        "default_context": (
            "Adaptar contenido panorámico 16:9 a vertical sin recortar partes clave ni truncar las frases de locución "
            "exigía medir duraciones reales de audio/vídeo y ajustar dinámicamente el grafo de filtros en FFmpeg."
        ),
        "default_learning": (
            "Congelado dinámico tpad sobre el último frame y limitación de hilos para convivir con workloads pesados."
        ),
        "fallback_snippet": (
            "def render_final_video(video_in: Path, audio_in: Path, out_mp4: Path):\n"
            "    v_dur = _probe_duration(video_in)\n"
            "    a_dur = _probe_duration(audio_in)\n"
            "    pad = max(0.0, a_dur - v_dur + 0.3)\n"
            "    # tpad=stop_mode=clone cuando la voz supera al vídeo"
        ),
    },
    {
        "dir_name": "GaTDSEQ",
        "repo_url": "https://github.com/gtrujillovdev-cyber/GaTDSeqB",
        "topic_track": "programacion",
        "focus_tier": 2,
        "target_file": "core/strategy.py",
        "anchor_keyword": "def calculate_confidence_score",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "GaTDSEQ — Arquitectura Modular en Python & Pytest"
        },
        "display_name": "GaTDSEQ — Motor Modular de Análisis en Python con Testing en Pytest",
        "domain": "Python, Arquitectura Modular, Pandas y Testing Automatizado",
        "tech_stack": ["Python", "Pytest", "Pandas", "Architecture", "CleanCode"],
        "project_intro": (
            "GaTDSEQ es una aplicación en Python con arquitectura desacoplada donde la lógica pura de evaluación vive en core/, "
            "separada de la infraestructura externa y verificada mediante una batería determinista en Pytest."
        ),
        "default_headline": "Aislar lógica de decisión en funciones puras para testear rápido con Pytest",
        "default_context": (
            "Evaluar reglas complejas junto a dependencias externas dificultaba las pruebas; separar la lógica pura en "
            "módulos independientes permitió validar cada caso con suites deterministas en Pytest."
        ),
        "default_learning": (
            "Desacoplamiento entre dominio puro e infraestructura y pruebas de estrés automatizadas."
        ),
        "fallback_snippet": (
            "def calculate_confidence_score(candle, atr_pct: float, weekly_ctx: dict) -> float:\n"
            "    score = 0.0\n"
            "    # Evaluación modular combinando factores normalizados\n"
            "    return round(min(100.0, score), 2)"
        ),
    },
    {
        "dir_name": "DevOps",
        "repo_url": "https://github.com/gtrujillovdev-cyber/DevOps",
        "topic_track": "sistemas",
        "focus_tier": 1,
        "target_file": "collector/monitor.py",
        "anchor_keyword": "def collect_metrics",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "system-monitor-cli — Telemetría Linux/Unix & FastAPI"
        },
        "display_name": "DevOps (system-monitor-cli) — Monitor de Sistemas en Python, Docker y FastAPI",
        "domain": "Sistemas Linux/Unix, Docker Compose, FastAPI y Python",
        "tech_stack": ["Linux", "Docker", "Python", "FastAPI", "DevOps"],
        "project_intro": (
            "system-monitor-cli es una herramienta de observabilidad para servidores Unix/Linux desarrollada en Python con psutil, "
            "API REST en FastAPI y despliegue en contenedores Docker Compose."
        ),
        "default_headline": "Recolectar métricas de CPU, RAM y procesos del sistema en Python tolerando fallos de permisos",
        "default_context": (
            "Monitorizar host y procesos en segundo plano exige manejar procesos efímeros y restricciones de permisos del sistema "
            "sin detener la API REST que sirve las métricas."
        ),
        "default_learning": (
            "Recolección resiliente con psutil, logs JSONL y separación en Docker Compose entre collector y API."
        ),
        "fallback_snippet": (
            "def collect_metrics():\n"
            "    cpu = psutil.cpu_percent(interval=None)\n"
            "    ram = psutil.virtual_memory().percent\n"
            "    disk = psutil.disk_usage('/').percent\n"
            "    return {'cpu': cpu, 'ram': ram, 'disk': disk}"
        ),
    },
    {
        "dir_name": "mando-tv",
        "topic_track": "sistemas",
        "focus_tier": 1,
        "target_file": "mando_tv/xiaomi.py",
        "anchor_keyword": "def apagar_xiaomi",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "mando-tv — Control Dual WebSocket SSAP + ADB Android TV"
        },
        "display_name": "mando-tv — Servidor HTTP Ligero para Control Multi-TV (webOS + Android TV)",
        "domain": "Redes LAN, WebSockets, ADB y Python Stdlib",
        "tech_stack": ["Python", "WebSockets", "ADB", "Networking", "HTTP"],
        "project_intro": (
            "mando-tv es un servidor ligero en Python para red local que unifica televisores LG webOS (vía WebSocket SSAP) y "
            "Xiaomi Android TV (vía ADB/WoL) bajo una PWA móvil y atajos de voz."
        ),
        "default_headline": "Evitar desincronización entre control remoto por red (ADB) y mando físico en Android TV",
        "default_context": (
            "Simular el apagado poniendo el brillo a 0 dejaba el mando físico desincronizado y el panel en negro al despertar; "
            "pasar a KEYCODE_SLEEP/WAKEUP idempotentes resolvió la convivencia real."
        ),
        "default_learning": (
            "Descubrimiento ARP validado por dirección MAC y caché TTL de estado para no saturar adbd."
        ),
        "fallback_snippet": (
            "def apagar_xiaomi(forzar_apagado_total: bool = False):\n"
            "    cmd = 'settings put global stay_on_while_plugged_in 0; input keyevent 223'\n"
            "    ejecutar_adb_xiaomi(cmd, timeout=3.0)"
        ),
    },
]


class DevDiaryGenerator:
    """
    Extrae código real y commits de los repositorios de Gabriel en /Developer/Projects,
    genera una captura de código limpia del archivo real y envía el borrador a Telegram
    para que Gabriel lo revise y apruebe con 1 clic antes de publicar en LinkedIn.
    """

    @staticmethod
    def _load_history() -> List[Dict[str, Any]]:
        if not DEV_DIARY_HISTORY_FILE.exists():
            return []
        try:
            return json.loads(DEV_DIARY_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    @staticmethod
    def _save_history(records: List[Dict[str, Any]]) -> None:
        DEV_DIARY_HISTORY_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @staticmethod
    def _resolve_repo_path(dir_name: str) -> Path:
        clean_name = dir_name.strip()
        if "jobseeker" in clean_name.lower() and BASE_DIR.exists():
            return BASE_DIR

        home_dir = Path.home()
        aliases = {
            "GTA6Channel": ["GTAVIHub", "GTA6Channel"],
            "GaTDSEQ": ["GaTDSEQ_Worker", "GaTDSEQ", "GaTDSeqB"],
            "mando-tv": ["mando-tv", "Sandbox/projects/mando-tv"],
            "GaBookAutoDownloader": ["GaBookAutoDownloader"],
            "DevOps": ["DevOps/system-monitor-cli", "system-monitor-cli", "DevOps"],
            "Tv-streamer": ["Tv-streamer", "tv-streamer"],
            "InteractiveCV": ["InteractiveCV", "DevOps/InteractiveCV", "Scripts/DevOps/InteractiveCV"],
            "LawLab": ["LawLab", "LawLab-macOS"],
            "GeminiJobBot": ["GeminiJobBot", "GJAgent"],
            "PolyPrec": ["PolyPrec", "PolyPred"],
            "BtcBriefing_iOS_ShortCut": ["BtcBriefing_iOS_ShortCut"],
        }
        names_to_try = aliases.get(clean_name, [clean_name])
        if dir_name != clean_name and dir_name not in names_to_try:
            names_to_try.append(dir_name)

        roots = [
            PROJECTS_ROOT,
            home_dir / "Developer" / "Projects",
            home_dir / "projects" / "AI",
            home_dir / "projects" / "Web",
            home_dir / "projects" / "Trading",
            home_dir / "projects" / "Tools",
            home_dir / "projects" / "Tools" / "DevOps",
            home_dir / "projects" / "Tools" / "Scripts" / "DevOps",
            home_dir / "projects" / "Tools" / "Sandbox" / "projects",
            home_dir / "Library" / "CloudStorage" / "GoogleDrive-4btrujillog@gmail.com" / "Mi unidad" / "Proyectos" / "Archivados",
            home_dir,
        ]
        for root in roots:
            for name in names_to_try:
                cand = root / name
                if cand.exists():
                    return cand

        return PROJECTS_ROOT / clean_name

    @classmethod
    def _inspect_repo(cls, project_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inspecciona en tiempo real el repositorio del proyecto:
        - Lee los últimos commits reales (`git log`).
        - Extrae los archivos modificados y el diff real del último commit (`git show`).
        - Enumera todos los archivos y funciones principales del proyecto para que cada post
          pueda hablar de un módulo o función distinta y generar su captura dinámica a medida.
        """
        repo_path = cls._resolve_repo_path(project_meta["dir_name"])
        commits = []
        recent_files = []
        last_commit_diff = ""
        repo_functions_inventory = []
        repo_url = project_meta.get("repo_url", "")
        snippet = project_meta["fallback_snippet"]
        source_file_label = project_meta.get("target_file", "main.py")

        if repo_path.exists():
            if (repo_path / ".git").exists():
                try:
                    rem = subprocess.check_output(
                        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if rem:
                        if rem.endswith(".git"):
                            rem = rem[:-4]
                        repo_url = rem
                except Exception:
                    pass

                try:
                    out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "log", "-n", "5", "--oneline"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if out:
                        commits = [line.strip() for line in out.splitlines() if line.strip()]
                except Exception:
                    pass

                try:
                    files_out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if files_out:
                        recent_files = [f.strip() for f in files_out.splitlines() if f.strip()][:6]
                except Exception:
                    pass

                try:
                    diff_out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "show", "--stat", "--oneline", "HEAD"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if diff_out:
                        last_commit_diff = "\n".join(diff_out.splitlines()[:12])
                except Exception:
                    pass

            # Escanear archivos y sus funciones reales en el repositorio
            code_files = [
                f for f in repo_path.rglob("*")
                if f.is_file()
                and f.suffix in (".py", ".swift", ".js", ".ts")
                and "node_modules" not in f.parts
                and ".venv" not in f.parts
                and "venv" not in f.parts
                and "__pycache__" not in f.parts
                and "dist" not in f.parts
            ]
            for cf in code_files[:15]:
                try:
                    rel_cf = str(cf.relative_to(repo_path))
                    lines = cf.read_text(encoding="utf-8", errors="ignore").splitlines()
                    funcs = [
                        l.strip().split("(")[0].replace("def ", "").replace("async ", "").replace("class ", "")
                        for l in lines
                        if l.strip().startswith(("def ", "async def ", "class ", "export function "))
                    ]
                    if funcs:
                        repo_functions_inventory.append(f"{rel_cf}: {', '.join(funcs[:6])}")
                except Exception:
                    continue

        return {
            **project_meta,
            "commits": commits,
            "recent_files": recent_files,
            "last_commit_diff": last_commit_diff,
            "repo_inventory": repo_functions_inventory,
            "repo_url": repo_url,
            "code_snippet": snippet,
            "source_file": source_file_label
        }

    @classmethod
    def _get_published_identifiers(
        cls,
        history: List[Dict[str, Any]],
        force_rotate_pill: bool = False,
        exclude_pill_ids: Optional[set[str]] = None
    ) -> tuple[set[str], set[str]]:
        """
        Recopila TODOS los `pill_id` y firmas de titulares ya publicados O presentes en
        borradores/programados activos para garantizar que nunca se vuelva a generar ni
        publicar una píldora repetida. Aplica cooldown de 14 días a borradores expirados o descartados.
        """
        now = datetime.now()
        used_pill_ids: set[str] = set()
        used_titles: set[str] = set()

        for h in history:
            st = h.get("status")
            pid = h.get("pill_id")
            preview = h.get("post_preview")

            # Consumo definitivo o activo en pipeline
            if st in {"published", "pending_approval", "scheduled", "regenerated", "duplicate_blocked"}:
                if pid:
                    used_pill_ids.add(pid)
                if preview:
                    first_line = preview.splitlines()[0]
                    used_titles.add(AntiBanValidator._normalize_text_for_dedup(first_line)[:120])
            # Cooldown de 14 días para borradores expirados, rechazados o descartados
            elif st in {"rejected", "expired", "pending_or_rejected"} or force_rotate_pill:
                in_cooldown = True
                raw_date = h.get("date") or h.get("created_at") or h.get("published_at")
                if raw_date and not force_rotate_pill:
                    try:
                        clean_dt = raw_date.replace("Z", "+00:00").split(".")[0]
                        entry_dt = datetime.fromisoformat(clean_dt)
                        if (now - entry_dt.replace(tzinfo=None)).total_seconds() > 14 * 86400:
                            in_cooldown = False
                    except Exception:
                        in_cooldown = True
                if in_cooldown:
                    if pid:
                        used_pill_ids.add(pid)
                    if preview:
                        first_line = preview.splitlines()[0]
                        used_titles.add(AntiBanValidator._normalize_text_for_dedup(first_line)[:120])

        if exclude_pill_ids:
            used_pill_ids.update(p for p in exclude_pill_ids if p)

        for rec in AntiBanValidator.get_records():
            if rec.get("status") == "success":
                if rec.get("pill_id"):
                    used_pill_ids.add(rec["pill_id"])
                title_sig = rec.get("title_signature") or AntiBanValidator._extract_title_signature(rec.get("caption_preview", ""))
                if title_sig:
                    used_titles.add(title_sig)

        try:
            from src.telegram_reviewer import _get_drafts
            for d in _get_drafts().values():
                if d.get("status") in {"pending", "scheduled", "publishing", "published"}:
                    if d.get("pill_id"):
                        used_pill_ids.add(d["pill_id"])
                    d_text = d.get("text", "")
                    if d_text:
                        first_line = d_text.splitlines()[0]
                        used_titles.add(AntiBanValidator._normalize_text_for_dedup(first_line)[:120])
                        title_sig = AntiBanValidator._extract_title_signature(d_text)
                        if title_sig:
                            used_titles.add(title_sig)
        except Exception:
            pass

        return used_pill_ids, used_titles

    @classmethod
    def _build_dynamic_unused_pill(cls, inspected: Dict[str, Any], used_pill_ids: set[str]) -> Optional[Dict[str, Any]]:
        """
        Si todas las píldoras curadas de un proyecto ya han sido publicadas, construye una píldora
        técnica única a partir de un módulo/función real no usado aún en `repo_inventory`.
        """
        dir_name = inspected["dir_name"]
        slug = dir_name.strip().lower().replace(" ", "_")
        proj_short = dir_name.strip()

        for inv_item in inspected.get("repo_inventory", []):
            if ":" not in inv_item:
                continue
            rel_file, funcs_str = inv_item.split(":", 1)
            rel_file = rel_file.strip()
            if rel_file.startswith("tests/") or "/tests/" in rel_file:
                continue
            for raw_fn in funcs_str.split(","):
                fn = raw_fn.strip().rstrip(":")
                if not fn or len(fn) < 3 or fn.startswith("_"):
                    continue
                dyn_id = f"{slug}_dyn_{rel_file}_{fn}"
                if dyn_id in used_pill_ids:
                    continue
                return {
                    "pill_id": dyn_id,
                    "category": "Código en producción",
                    "source_file": rel_file,
                    "target_symbol": fn,
                    "code_focus": f"def {fn}",
                    "headline": f"Cómo estructuré {fn} en {rel_file} dentro de {proj_short}",
                    "context": (
                        f"Siguiendo con la arquitectura interna de {proj_short}, en el módulo {rel_file} separé la responsabilidad "
                        f"de {fn} para mantener el código legible, fácil de probar por separado y listo para evolucionar sin romper el resto."
                    ),
                    "lead_in": f"En {rel_file} la lógica de {fn} está planteada así:",
                    "bullets": [
                        f"Aíslo {fn} dentro de {rel_file} para que cada componente tenga una sola responsabilidad clara.",
                        "Valido entradas y errores esperados antes de ejecutar la lógica principal del módulo.",
                        "Mantengo la función desacoplada para poder verificarla rápido desde consola o tests unitarios."
                    ],
                    "question": f"¿Cómo soléis organizar la separación de módulos y responsabilidades en proyectos de {inspected['tech_stack'][0]}?"
                }
        return None

    @classmethod
    def _select_educational_pill(
        cls,
        inspected: Dict[str, Any],
        history: List[Dict[str, Any]],
        force_rotate_pill: bool = False,
        exclude_pill_ids: Optional[set[str]] = None,
        preferred_track: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extrae la siguiente píldora educativa NO PUBLICADA para el proyecto seleccionado.
        Regla estricta anti-repetición: jamás recicla una píldora ya publicada ni existente en borradores.
        """
        dir_name = inspected["dir_name"]
        proj_track = inspected.get("topic_track", "programacion")
        curated_pills = (
            EDUCATIONAL_PILLS_BY_PROJECT.get(dir_name)
            or EDUCATIONAL_PILLS_BY_PROJECT.get(dir_name.strip(), [])
        )
        used_pill_ids, used_titles = cls._get_published_identifiers(
            history,
            force_rotate_pill=force_rotate_pill,
            exclude_pill_ids=exclude_pill_ids
        )

        unused_pills = []
        for pill in curated_pills:
            norm_head = AntiBanValidator._normalize_text_for_dedup(pill["headline"])[:120]
            if pill["pill_id"] not in used_pill_ids and not any(norm_head in t or t in norm_head for t in used_titles if len(t) > 18):
                unused_pills.append(pill)

        chosen_pill = None
        if unused_pills:
            if preferred_track:
                chosen_pill = next(
                    (p for p in unused_pills if p.get("topic_track", proj_track) == preferred_track),
                    None
                )
            if not chosen_pill:
                chosen_pill = unused_pills[0]

        # Si ya se han publicado todas las píldoras curadas de este proyecto, generar una dinámica NUEVA
        if not chosen_pill:
            chosen_pill = cls._build_dynamic_unused_pill(inspected, used_pill_ids)

        if not chosen_pill:
            inspected["exhausted"] = True
            return inspected

        inspected["exhausted"] = False
        inspected["pill"] = chosen_pill
        inspected["pill_id"] = chosen_pill["pill_id"]
        inspected["pill_category"] = chosen_pill["category"]
        inspected["topic_track"] = chosen_pill.get("topic_track", proj_track)
        inspected["default_headline"] = chosen_pill["headline"]
        inspected["default_context"] = chosen_pill["context"]
        inspected["pill_lead_in"] = chosen_pill.get("lead_in", f"En {chosen_pill.get('source_file', 'el código')} lo resolví así:")
        inspected["pill_bullets"] = chosen_pill.get("bullets", [])
        inspected["pill_question"] = chosen_pill.get("question", "")
        inspected["source_file"] = chosen_pill.get("source_file", inspected["source_file"])
        inspected["target_symbol"] = chosen_pill.get("target_symbol", "")
        inspected["code_focus"] = chosen_pill.get("code_focus", "")
        return inspected

    @staticmethod
    def _preferred_topic_track(published_history: List[Dict[str, Any]]) -> str:
        """
        Mantiene el equilibrio editorial deseado (~80% programación, ~20% sistemas):
        si en las últimas 3 entradas hubo alguna de sistemas, prioriza programación;
        si las últimas 4 fueron todas de programación, toca sistemas.
        """
        recent = published_history[-4:]
        recent_tracks = [
            (h.get("topic_track") or ("sistemas" if "sistema" in (h.get("pill_category") or "").lower() else "programacion"))
            for h in recent
        ]
        if any(t == "sistemas" for t in recent_tracks[-3:]):
            return "programacion"
        if len(recent_tracks) >= 4 and all(t == "programacion" for t in recent_tracks):
            return "sistemas"
        return "programacion"

    @classmethod
    def pick_next_diary_entry(
        cls,
        project_filter: Optional[str] = None,
        force_rotate_pill: bool = False,
        exclude_pill_ids: Optional[set[str]] = None
    ) -> Dict[str, Any]:
        """
        Selecciona el siguiente proyecto en rotación que AÚN tenga píldoras sin publicar,
        equilibrando ~80% Programación y ~20% Sistemas orientado a empleo IT.
        """
        history = cls._load_history()
        try:
            from src.telegram_reviewer import _get_drafts
            cur_drafts = _get_drafts()
            hist_changed = False
            for h in history:
                d_id = h.get("draft_id")
                if d_id and h.get("status") == "pending_approval" and d_id in cur_drafts:
                    dst = cur_drafts[d_id].get("status")
                    if dst in ("expired", "rejected"):
                        h["status"] = dst
                        hist_changed = True
            if hist_changed:
                cls._save_history(history)
        except Exception:
            pass
        slot_consuming = {"published", "pending_approval", "scheduled"}
        published_history = [h for h in history if h.get("status") in slot_consuming]
        entry_number = len(published_history) + 1
        preferred_track = cls._preferred_topic_track(published_history)

        if project_filter:
            clean_filter = project_filter.split("—")[-1].strip().lower()
            for proj in CURATED_DEVLOG_PROJECTS:
                if clean_filter in proj["dir_name"].lower() or proj["dir_name"].strip().lower() in clean_filter:
                    inspected = cls._inspect_repo(proj)
                    inspected["entry_number"] = entry_number
                    return cls._select_educational_pill(
                        inspected,
                        history,
                        force_rotate_pill=force_rotate_pill,
                        exclude_pill_ids=exclude_pill_ids,
                        preferred_track=preferred_track
                    )

        recent_dirs_norm = [
            (h.get("dir_name") or "").strip().lower()
            for h in history[-len(CURATED_DEVLOG_PROJECTS):]
            if h.get("dir_name")
        ]
        unpublished_recently = [
            p for p in CURATED_DEVLOG_PROJECTS
            if p["dir_name"].strip().lower() not in recent_dirs_norm
        ]
        published_recently = [
            p for p in CURATED_DEVLOG_PROJECTS
            if p["dir_name"].strip().lower() in recent_dirs_norm
        ]
        published_recently.sort(
            key=lambda p: max(
                (i for i, d in enumerate(recent_dirs_norm) if d == p["dir_name"].strip().lower()),
                default=-1
            )
        )

        used_pill_ids, _ = cls._get_published_identifiers(
            history, force_rotate_pill=force_rotate_pill, exclude_pill_ids=exclude_pill_ids
        )

        def _has_unused_track_pill(proj: Dict[str, Any], track: str) -> bool:
            pills = EDUCATIONAL_PILLS_BY_PROJECT.get(proj["dir_name"], [])
            return any(
                p["pill_id"] not in used_pill_ids and p.get("topic_track", proj.get("topic_track", "programacion")) == track
                for p in pills
            )

        def _has_unused_curated_pill(proj: Dict[str, Any]) -> bool:
            pills = EDUCATIONAL_PILLS_BY_PROJECT.get(proj["dir_name"], [])
            return any(p["pill_id"] not in used_pill_ids for p in pills)

        import hashlib
        from datetime import date as _date
        day_seed = int(hashlib.md5(_date.today().isoformat().encode()).hexdigest()[:8], 16)
        if unpublished_recently:
            offset = day_seed % len(unpublished_recently)
            unpublished_recently = unpublished_recently[offset:] + unpublished_recently[:offset]

        recent_set = {p["dir_name"].strip().lower() for p in published_recently}

        def _candidate_rank(proj: Dict[str, Any]) -> tuple[int, int, int, int]:
            has_local = 0 if cls._resolve_repo_path(proj["dir_name"]).exists() else 1
            tier = int(proj.get("focus_tier", 1))
            has_curated = _has_unused_curated_pill(proj)
            tier_bucket = 0 if (tier == 1 and has_curated) else (1 if has_curated else 2)
            matches_track = 0 if (
                _has_unused_track_pill(proj, preferred_track)
                or proj.get("topic_track", "programacion") == preferred_track
            ) else 1
            is_recent = 1 if proj["dir_name"].strip().lower() in recent_set else 0
            return (has_local, tier_bucket, matches_track, is_recent)

        ordered_candidates = sorted(unpublished_recently + published_recently, key=_candidate_rank)

        for proj in ordered_candidates:
            inspected = cls._inspect_repo(proj)
            inspected["entry_number"] = entry_number
            selected = cls._select_educational_pill(
                inspected,
                history,
                force_rotate_pill=force_rotate_pill,
                exclude_pill_ids=exclude_pill_ids,
                preferred_track=preferred_track
            )
            if not selected.get("exhausted"):
                return selected

        fallback = cls._inspect_repo(CURATED_DEVLOG_PROJECTS[0])
        fallback["entry_number"] = entry_number
        fallback["exhausted"] = True
        return fallback

    @staticmethod
    def _format_clean_post(text: str, hashtags_line: str = "") -> str:
        """
        Regla permanente de maquetación para LinkedIn y Telegram (Directriz Anti-Apelotonamiento):
        1. Elimina cualquier emoji al principio de las líneas (mantiene seriedad técnica; máximo 1-2 al final de frase si existen).
        2. Agrupa todas las tecnologías y todos los hashtags en UNA SOLA LÍNEA continua (sin saltos entre tecnologías).
        3. DIRECTRIZ ANTI-APELOTONAMIENTO EN MÓVIL:
           - Prohibido pegar viñetas en líneas consecutivas: fuerza SIEMPRE una línea en blanco ('\\n\\n') entre cada viñeta ('• ').
           - Prohibido texto denso dentro de una viñeta: cada viñeta debe ser de 1 sola idea corta (máx. ~115 caracteres / 2 líneas en móvil).
             Si una viñeta supera los 120 caracteres por encadenar enumeraciones, se sintetiza automáticamente en su cláusula principal.
           - Viñetas a ras de margen ('• ') sin espacios previos que descuadren el sangrado en la app móvil de LinkedIn.
        """
        import re
        text = text.replace("`", "")
        raw_lines = [line.strip() for line in text.strip().splitlines()]

        # Regex para limpiar emojis o símbolos decorativos al inicio de cualquier línea
        leading_emoji_re = re.compile(r"^[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f\u200d]+\s*")

        body_lines = []
        collected_hashtags = []

        def _ensure_blank_line():
            if body_lines and body_lines[-1] != "":
                body_lines.append("")

        def _condense_bullet(bullet_text: str, max_len: int = 120) -> str:
            bullet_text = " ".join(bullet_text.split()).strip()
            if len(bullet_text) <= max_len:
                return bullet_text
            # Cortar en el primer separador natural (. / ; / ,) a partir del carácter 60
            window = bullet_text[:max_len]
            for sep in [". ", "; ", ", "]:
                pos = window.find(sep, 60)
                if pos != -1:
                    trimmed = window[:pos].rstrip(".,;:") + "."
                    return trimmed
            # Si no hay puntuación intermedia, cortar por palabra limpia
            cut = window.rsplit(" ", 1)[0].rstrip(".,;:") + "."
            return cut

        for line in raw_lines:
            if not line:
                _ensure_blank_line()
                continue

            # Si la línea es solo de hashtags, recogerlos todos para unirlos en 1 sola línea al final
            tokens = line.split()
            if tokens and all(t.startswith("#") for t in tokens):
                for t in tokens:
                    if t not in collected_hashtags:
                        collected_hashtags.append(t)
                continue

            # Quitar cualquier emoji al principio de la línea
            line = leading_emoji_re.sub("", line).strip()

            # Descartar marcadores vacíos o huérfanos ("•", "*", "-") que rompen la maquetación
            if line in ("•", "*", "-", "·"):
                continue

            # Normalizar viñetas con separación obligatoria de línea en blanco y concisión anti-apelotonamiento
            if line.startswith(("• ", "* ", "- ")):
                clean_bullet = leading_emoji_re.sub("", line[2:].strip()).strip()
                if not clean_bullet:
                    continue
                if clean_bullet.lower().startswith(("stack", "tecnologías", "tecnologias")):
                    clean_bullet = " ".join(clean_bullet.split())
                else:
                    clean_bullet = _condense_bullet(clean_bullet, max_len=120)
                _ensure_blank_line()
                body_lines.append(f"• {clean_bullet}")
                _ensure_blank_line()
            elif line.lower().startswith(("stack:", "tecnologías:", "tecnologias:", "repositorio:")):
                _ensure_blank_line()
                body_lines.append(" ".join(line.split()))
            else:
                body_lines.append(line)

        while body_lines and body_lines[-1] == "":
            body_lines.pop()

        final_hashtags = " ".join(collected_hashtags) if collected_hashtags else hashtags_line.strip()
        if final_hashtags:
            final_hashtags = " ".join(final_hashtags.splitlines()).strip()
            _ensure_blank_line()
            body_lines.append(final_hashtags)

        return "\n".join(body_lines).strip()

    @classmethod
    def generate_diary_copy(cls, entry: Dict[str, Any]) -> str:
        """
        Genera una nota del Diario de Desarrollo con voz 100% humana en primera persona:
        - Título corto y natural en una sola línea ('Diario #3: ...') sin cortes tras '#X' ni etiquetas robóticas.
        - Explicación directa de un problema real de programación/arquitectura y cómo se resolvió en el código.
        """
        entry_num = entry["entry_number"]
        proj_short = entry["dir_name"].strip()
        headline = entry.get("default_headline", f"ajustes en {proj_short}").strip()
        if headline.lower().startswith("diario"):
            title_line = headline
        else:
            title_line = f"Diario #{entry_num}: {headline}"

        project_intro = (entry.get("project_intro") or "").strip()
        context_paragraph = (entry.get("default_context") or "").strip()
        intro_blocks = "\n\n".join(b for b in [project_intro, context_paragraph] if b)

        lead_in = entry.get("pill_lead_in") or f"En {entry.get('source_file', 'el código')} lo resolví así:"
        pill_bullets = entry.get("pill_bullets", [])
        source_file = entry.get("source_file", "main.py")
        repo_url = entry.get("repo_url", "").strip()
        repo_line = f"Repositorio: {repo_url}\n\n" if repo_url else ""
        stack_inline = " · ".join(entry["tech_stack"])
        topic_track = entry.get("topic_track", "programacion")
        track_tags = (
            ["#Sistemas", "#Linux", "#Programacion", "#DesarrolloDeSoftware", "#SevillaTech"]
            if topic_track == "sistemas"
            else ["#Programacion", "#DesarrolloDeSoftware", "#SevillaTech"]
        )
        base_tags = [f"#{t.replace(' ', '')}" for t in entry["tech_stack"][:3]]
        merged_tags = []
        for tg in base_tags + track_tags:
            if tg not in merged_tags:
                merged_tags.append(tg)
        hashtags = " ".join(merged_tags[:6])

        if pill_bullets and len(pill_bullets) >= 3:
            b1, b2, b3 = pill_bullets[0], pill_bullets[1], pill_bullets[2]
        else:
            b1 = f"Separé la lógica principal en {source_file} para no mezclar capas."
            b2 = f"{entry.get('default_learning', '')}"
            b3 = "Dejé pruebas directas por consola para verificar cada cambio rápido."

        structured_pill_post = (
            f"{title_line}\n\n"
            f"{intro_blocks}\n\n"
            f"{lead_in}\n\n"
            f"• {b1}\n\n"
            f"• {b2}\n\n"
            f"• {b3}\n\n"
            f"{repo_line}"
            f"Stack: {stack_inline}\n\n"
            f"{hashtags}"
        )
        if GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                pill_q = entry.get("pill_question", "")
                focus_desc = (
                    "sistemas Linux/Unix, automatización y redes"
                    if topic_track == "sistemas"
                    else "programación, arquitectura limpia y desarrollo de software"
                )
                prompt = f"""Eres un desarrollador de software junior (DAM, Sevilla) en búsqueda activa de empleo IT que publica entradas técnicas en LinkedIn para mostrar solvencia en {focus_desc} ante equipos de ingeniería y recruiters.
Reescribe esta entrada con voz natural en primera persona. Directo, técnico, cero clichés corporativos ni lenguaje infantil.

REGLAS ESTRICTAS:
- Primera línea OBLIGATORIA exacta: '{title_line}' (no la modifiques)
- Enfoque 100% en {focus_desc}: destaca decisiones de código, debugging, testing o sistemas reales que interesen a un responsable técnico o de selección IT.
- Línea en blanco entre cada viñeta '• ' y PROHIBIDO generar líneas con '•' vacío
- Cada viñeta máximo 15 palabras / 110 caracteres, 1 sola idea
- Párrafos cortos (máximo 2 frases). Sin texto apelotonado en móvil.
- Mantén exactamente 3 bullets técnicos concretos y la línea 'Stack: {stack_inline}'
{f"- Conserva la línea 'Repositorio: {repo_url}'" if repo_url else ""}
- Cierra con esta pregunta exacta: {pill_q if pill_q else '¿Cómo soléis resolver esto en vuestros proyectos?'}
- Última línea: exactamente '{hashtags}'
- NO añadas explicaciones meta, comillas ni texto introductorio. Solo el post.

CONTENIDO BASE:
{structured_pill_post}
"""
                for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        response = client.models.generate_content(model=model_name, contents=prompt)
                        if response.text and len(response.text.strip()) > 150:
                            return cls._format_clean_post(response.text.strip(), hashtags_line=hashtags)
                    except Exception:
                        continue
            except Exception as e:
                print(f"[DevDiary] Aviso Gemini: {e}. Usando formato estructurado.")
        return cls._format_clean_post(structured_pill_post, hashtags_line=hashtags)

    @classmethod
    def generate_first_comment(cls, entry: Dict[str, Any]) -> str:
        """
        Genera el texto del PRIMER COMENTARIO que se publica automáticamente justo después del post:
        incluye la URL real del repositorio de GitHub y una pregunta natural sobre el problema técnico.
        """
        repo_url = entry.get("repo_url", "").strip()
        main_tech = entry["tech_stack"][0] if entry.get("tech_stack") else "Python"
        proj_name = entry["dir_name"].strip()
        source_file = entry.get("source_file", "")
        pill_question = entry.get("pill_question", "").strip()
        if not pill_question:
            pill_question = f"¿Cómo soléis resolver esto vosotros trabajando con {main_tech}?"

        if repo_url:
            file_ref = f" ({source_file})" if source_file else ""
            return (
                f"Dejo por aquí el repo de {proj_name} por si queréis echarle un ojo al código{file_ref}:\n"
                f"{repo_url}\n\n"
                f"{pill_question}"
            )
        return pill_question

    @classmethod
    def _extract_dynamic_code_from_post(cls, repo_path: Path, post_text: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrae el bloque de código REAL de la función explicada en la píldora, saltándose
        docstrings largos para que en la captura de VS Code se vea directamente el algoritmo
        (bucles, regex, ponderaciones, validaciones) con su numeración de líneas real.
        """
        import re
        source_file = entry.get("source_file", "main.py")
        target_symbol = entry.get("target_symbol", "")
        code_focus = entry.get("code_focus", "")
        snippet = entry.get("code_snippet", "")
        start_line = 1
        git_commit = entry["commits"][0] if entry.get("commits") else ""

        if not repo_path.exists():
            return {"source_file": source_file, "snippet": snippet, "start_line": 1, "git_commit": git_commit}

        all_files = [
            f for f in repo_path.rglob("*")
            if f.is_file()
            and f.suffix in (".py", ".swift", ".js", ".ts", ".tsx", ".sh", ".yml", ".yaml")
            and "node_modules" not in f.parts
            and ".venv" not in f.parts
            and "venv" not in f.parts
            and "__pycache__" not in f.parts
            and "dist" not in f.parts
        ]

        matched_file = None
        preferred_path = repo_path / source_file
        if preferred_path.exists() and preferred_path.is_file():
            matched_file = preferred_path
        else:
            for f in all_files:
                rel = str(f.relative_to(repo_path))
                if f.name == Path(source_file).name or f.name in post_text or rel in post_text:
                    matched_file = f
                    break

        def _trim_incomplete_tail(chunk: list[str]) -> list[str]:
            trimmed = list(chunk)
            while trimmed and (
                not trimmed[-1].strip()
                or trimmed[-1].rstrip().endswith((":", "(", "{", "[", ",", "\\"))
            ):
                if len(trimmed) <= 8:
                    break
                trimmed.pop()
            return trimmed

        def _skip_docstring_window(lines_list: List[str], def_idx: int, num_lines: int = 28, lead_context: int = 0) -> tuple[str, int]:
            """Salta firma multilínea + docstring tras un def/class/async def para mostrar el código ejecutable real."""
            cur = def_idx + 1
            # Si es firma multilínea (def foo(\n ...\n) -> bool:), avanzar hasta el ':' que cierra la cabecera
            if lines_list[def_idx].strip().startswith(("def ", "async def ")) and not lines_list[def_idx].rstrip().endswith(":"):
                scan_limit = min(len(lines_list), def_idx + 20)
                while cur < scan_limit and not lines_list[cur].rstrip().endswith(":"):
                    cur += 1
                cur += 1
            while cur < len(lines_list) and not lines_list[cur].strip():
                cur += 1
            if cur < len(lines_list) and ('"""' in lines_list[cur] or "'''" in lines_list[cur]):
                delim = '"""' if '"""' in lines_list[cur] else "'''"
                if lines_list[cur].count(delim) == 1:
                    cur += 1
                    while cur < len(lines_list) and delim not in lines_list[cur]:
                        cur += 1
                    cur += 1
                else:
                    cur += 1
                while cur < len(lines_list) and not lines_list[cur].strip():
                    cur += 1
                if cur < len(lines_list) and len(lines_list) - cur >= 8:
                    return "\n".join(_trim_incomplete_tail(lines_list[cur:cur + num_lines])), cur + 1
            start_idx = max(0, def_idx - lead_context)
            return "\n".join(_trim_incomplete_tail(lines_list[start_idx:start_idx + num_lines])), start_idx + 1

        if matched_file and matched_file.exists():
            try:
                lines = matched_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                # 1. Si hay un code_focus explícito (la línea exacta donde empieza la lógica clave)
                if code_focus:
                    for idx, line in enumerate(lines):
                        if code_focus in line:
                            blk, st = _skip_docstring_window(lines, idx, 28, lead_context=3)
                            return {
                                "source_file": str(matched_file.relative_to(repo_path)),
                                "snippet": blk,
                                "start_line": st,
                                "git_commit": git_commit
                            }
                # 2. Si hay target_symbol, localizar la función y saltar el docstring si lo tiene
                if target_symbol:
                    for idx, line in enumerate(lines):
                        if target_symbol in line and (
                            line.strip().startswith(("def ", "async def ", "class ", "final class ", "func ", "export ", "@"))
                            or f"{target_symbol} =" in line
                            or f"def {target_symbol}" in line
                        ):
                            blk, st = _skip_docstring_window(lines, idx, 28)
                            if len(blk.strip()) > 30:
                                return {
                                    "source_file": str(matched_file.relative_to(repo_path)),
                                    "snippet": blk,
                                    "start_line": st,
                                    "git_commit": git_commit
                                }
            except Exception:
                pass

        words_in_post = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", post_text)
        if target_symbol:
            words_in_post.insert(0, target_symbol)
        stop_words = {
            "Diario", "Desarrollo", "Para", "Como", "Esta", "Este", "Stack", "Python",
            "Docker", "Linux", "macOS", "SevillaTech", "DesarrolloDeSoftware", "implementado",
            "versión", "proyecto", "proyectos", "código", "sistema", "cuando", "donde",
            "antes", "después", "través", "permite", "usando", "arquitectura", "configuración"
        }
        candidate_symbols = [w for w in words_in_post if w not in stop_words]

        best_score = -1
        best_block = None
        best_file = matched_file
        best_start_line = 1

        search_pool = [matched_file] if matched_file else all_files[:25]
        for f in search_pool:
            if not f or not f.exists():
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                for idx, line in enumerate(lines):
                    s = line.strip()
                    if s.startswith(("def ", "async def ", "class ", "final class ", "func ", "export function ", "@app.")):
                        blk, st = _skip_docstring_window(lines, idx, 19)
                        score = sum(3 for sym in candidate_symbols if sym in s) + sum(1 for sym in candidate_symbols if sym in blk)
                        if matched_file and f == matched_file:
                            score += 2
                        if score > best_score and len(blk.strip()) > 40:
                            best_score = score
                            best_block = blk
                            best_file = f
                            best_start_line = st
            except Exception:
                continue

        if best_block and best_file:
            return {
                "source_file": str(best_file.relative_to(repo_path)),
                "snippet": best_block,
                "start_line": best_start_line,
                "git_commit": git_commit
            }

        return {
            "source_file": source_file,
            "snippet": snippet,
            "start_line": start_line,
            "git_commit": git_commit
        }

    @classmethod
    def prepare_daily_diary_draft(
        cls,
        wait_approval: bool = True,
        project_filter: Optional[str] = None,
        force_rotate_pill: bool = False,
        exclude_pill_ids: Optional[set[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        1. Verifica que no exista ya ninguna publicación programada o borrador pendiente activo.
        2. Selecciona el proyecto en rotación y su siguiente Píldora Educativa (arquitectura,
           lógica de negocio, algoritmos o sistemas) aún no publicada ni en borrador.
        3. Genera DINÁMICAMENTE las capturas de la interfaz/consola en vivo + el bloque de código
           exacto (`source_file` + `target_symbol` con líneas reales) explicado en la píldora.
        4. Envía el borrador a Telegram (@JobGaBot) para confirmación previa.
        """
        with _DRAFT_GEN_LOCK:
            return cls._prepare_daily_diary_draft_locked(
                wait_approval=wait_approval,
                project_filter=project_filter,
                force_rotate_pill=force_rotate_pill,
                exclude_pill_ids=exclude_pill_ids,
            )

    @classmethod
    def _prepare_daily_diary_draft_locked(
        cls,
        wait_approval: bool = True,
        project_filter: Optional[str] = None,
        force_rotate_pill: bool = False,
        exclude_pill_ids: Optional[set[str]] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            existing_drafts = expire_stale_drafts(max_age_hours=24.0)
            for d_id, d_obj in existing_drafts.items():
                st = d_obj.get("status", "")
                if st in ("scheduled", "publishing"):
                    sched_for = d_obj.get("scheduled_for", "10:00")
                    print(
                        f"[DevDiary] [⛔] Ya existe una publicación programada o en curso "
                        f"({d_id} -> {sched_for}). No se generará otra."
                    )
                    return None
                if st == "pending":
                    print(
                        f"[DevDiary] [⛔] Ya existe un borrador pendiente ({d_id}). "
                        f"Publícalo, prográmalo o descártalo antes de generar otro."
                    )
                    return None
        except Exception:
            pass

        entry = cls.pick_next_diary_entry(
            project_filter=project_filter,
            force_rotate_pill=force_rotate_pill,
            exclude_pill_ids=exclude_pill_ids
        )
        if entry.get("exhausted"):
            print("[DevDiary] [⛔] Todas las píldoras disponibles de este alcance ya han sido publicadas. Abortando para no repetir.")
            return None

        project_slug = entry["dir_name"].strip().lower().replace(" ", "_")
        repo_path = cls._resolve_repo_path(entry["dir_name"])
        pill_cat = entry.get("pill_category", "Ingeniería")

        print(f"\n📓 [DevDiary] Preparando Entrada #{entry['entry_number']} ({pill_cat}): {entry['display_name']}")

        # 1. Generar PRIMERO el texto de la píldora educativa y el primer comentario (URL del repo + pregunta técnica)
        post_text = cls.generate_diary_copy(entry)
        is_dup, dup_reason = AntiBanValidator.is_duplicate_publication(
            post_text,
            pill_id=entry.get("pill_id"),
            include_active_drafts=True
        )
        if is_dup:
            print(f"[DevDiary] [⛔] Borrador bloqueado antes de generar capturas por repetición: {dup_reason}")
            return None

        first_comment = cls.generate_first_comment(entry)

        # 2. Construir galería dinámica de capturas según el proyecto y el concepto explicado:
        #    - Captura 1-2 (si tiene UI/consola en vivo): Interfaz y funcionalidades reales en ejecución
        #    - Captura final (siempre): Bloque de código exacto (archivo + líneas reales) del concepto de la píldora
        dyn = cls._extract_dynamic_code_from_post(repo_path, post_text, entry)
        ts_suffix = datetime.now().strftime("%H%M%S")
        image_paths: List[Path] = []

        live_spec = entry.get("live_capture")
        if live_spec and repo_path.exists():
            print(f"[*] Extrayendo galería real de la UI/funcionalidades en vivo ({live_spec.get('mode')})...")
            ui_imgs = ProjectCapturer.capture_live_project_gallery(
                project_dir=repo_path,
                capture_spec=live_spec,
                base_prefix=f"devlog_{entry['entry_number']}_{project_slug}_{ts_suffix}"
            )
            for idx_img, ui_img in enumerate(ui_imgs, 1):
                image_paths.append(ui_img)
                print(f"[✓] Captura {idx_img} (UI / Funcionalidades en vivo): {ui_img}")

        print(f"[*] Extrayendo captura dinámica del código de la píldora -> {dyn['source_file']} (línea {dyn['start_line']})...")
        code_img = ProjectCapturer.generate_code_card(
            project_name=entry["dir_name"].strip(),
            headline=entry["default_headline"],
            code_snippet=dyn["snippet"],
            tech_tags=entry["tech_stack"][:4],
            filename=f"devlog_{entry['entry_number']}_{project_slug}_{ts_suffix}_{len(image_paths) + 1}_code.png",
            source_file=dyn["source_file"],
            git_commit=dyn["git_commit"],
            start_line=dyn["start_line"],
            repo_path=repo_path,
            target_symbol=entry.get("target_symbol", "")
        )
        if code_img and code_img.exists():
            image_paths.append(code_img)
            print(f"[✓] Captura {len(image_paths)} (Código dinámico {dyn['source_file']}): {code_img}")

        # 3. Enviar a Telegram para revisión y confirmación previa
        project_title = f"Diario #{entry['entry_number']} · {entry['dir_name'].strip()}"
        draft_id = TelegramReviewer.send_draft(
            project_name=project_title,
            post_text=post_text,
            image_path=image_paths,
            first_comment=first_comment,
            pill_id=entry.get("pill_id")
        )

        if not draft_id:
            print("[!] No se pudo enviar el borrador a Telegram.")
            return None

        history = cls._load_history()
        record = {
            "entry_number": entry["entry_number"],
            "draft_id": draft_id,
            "date": datetime.now().isoformat(),
            "dir_name": entry["dir_name"],
            "pill_id": entry.get("pill_id"),
            "pill_category": pill_cat,
            "topic_track": entry.get("topic_track", "programacion"),
            "source_file": dyn["source_file"],
            "display_name": entry["display_name"],
            "commits_included": entry.get("commits", [])[:3],
            "image_paths": [str(p) for p in image_paths],
            "first_comment": first_comment,
            "post_preview": post_text[:250],
            "status": "pending_approval"
        }
        history.append(record)
        cls._save_history(history)

        if wait_approval:
            published = TelegramReviewer.listen_and_process_decision(target_draft_id=draft_id, timeout=900)
            record["status"] = "published" if published else "pending_or_rejected"
            cls._save_history(history)

        return record

    @classmethod
    def regenerate_draft_by_id(cls, old_draft_id: str) -> Optional[str]:
        """
        Regenera un borrador pendiente preservando la píldora previa como 'regenerated'
        en el historial (para no repetirla jamás) y rotando primero dentro del mismo proyecto
        o saltando al siguiente proyecto con píldoras inéditas si se agotó.
        """
        from src.telegram_reviewer import _get_drafts, _save_drafts
        drafts = expire_stale_drafts(max_age_hours=24.0)
        old = drafts.get(old_draft_id, {})
        if old.get("status") in ("scheduled", "publishing"):
            print(f"[DevDiary] [⛔] No se regenera {old_draft_id} porque ya está en estado '{old.get('status')}'.")
            return None

        old_pill_id = old.get("pill_id")
        proj_label = old.get("project_name", "")
        if "—" in proj_label:
            proj_filter = proj_label.split("—")[-1].strip()
        elif "·" in proj_label:
            proj_filter = proj_label.split("·")[-1].strip()
        else:
            proj_filter = None

        # Expirar cualquier otro pendiente huérfano antiguo y eliminar old_draft_id de activos
        if old_draft_id in drafts:
            drafts.pop(old_draft_id, None)
        for d_id, d_obj in drafts.items():
            if d_obj.get("status") == "pending":
                d_obj["status"] = "expired"
                d_obj["expired_reason"] = "superseded_by_regen"
        _save_drafts(drafts)

        # Marcar old_draft_id como 'regenerated' en vez de borrarlo (conserva memoria anti-repetición)
        history = cls._load_history()
        found_in_hist = False
        for h in history:
            if h.get("draft_id") == old_draft_id and h.get("status") != "published":
                h["status"] = "regenerated"
                found_in_hist = True
        if not found_in_hist and old_pill_id:
            history.append({
                "draft_id": old_draft_id,
                "date": datetime.now().isoformat(),
                "dir_name": proj_filter or "",
                "pill_id": old_pill_id,
                "status": "regenerated",
            })
        cls._save_history(history)

        exclude_ids = {old_pill_id} if old_pill_id else None
        rec = cls.prepare_daily_diary_draft(
            wait_approval=False,
            project_filter=proj_filter,
            force_rotate_pill=True,
            exclude_pill_ids=exclude_ids
        )
        # Si el mismo proyecto agotó sus píldoras, rotar automáticamente al siguiente proyecto inédito
        if not rec and proj_filter:
            print(f"[DevDiary] Proyecto '{proj_filter}' agotado; rotando al siguiente proyecto inédito...")
            rec = cls.prepare_daily_diary_draft(
                wait_approval=False,
                project_filter=None,
                force_rotate_pill=True,
                exclude_pill_ids=exclude_ids
            )
        return rec.get("draft_id") if rec else None
