import os
from typing import Dict, Any, Optional
from config import GEMINI_API_KEY
from src.dev_diary import DevDiaryGenerator

class CopyGenerator:
    """
    Generador de publicaciones técnicas serias, rigurosas y maduras para LinkedIn.
    Estilo basado en ingeniería de software pragmática, auditoría de sistemas y métricas.
    Cero frases naíf ('trasteando', 'una pasada'), cero clichés corporativos.
    """

    @staticmethod
    def generate_post(
        project_name: str,
        headline_title: str,
        problem_context: str,
        implementation_details: str,
        technical_findings: str,
        objectives_achieved: list,
        tech_stack: list
    ) -> str:
        stack_str = ", ".join(tech_stack[:4])
        hashtags = [f"#{t.replace(' ', '')}" for t in tech_stack[:4]] + ["#SoftwareEngineering", "#SystemArchitecture"]
        hashtags_str = " ".join(hashtags)

        bullets_str = "\n\n".join([f"• {obj}" for obj in objectives_achieved])

        if GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)

                prompt = f"""
                Eres un ingeniero de software con experiencia real en producción, redactando una publicación para LinkedIn.
                Tu objetivo NO es solo mostrar tu trabajo, sino GENERAR CONVERSACIÓN e INTERACCIÓN con otros profesionales del sector.

                REGLAS DE ESTILO Y DIRECTRIZ ANTI-APELOTONAMIENTO (NO NEGOCIABLES):
                - Tono: profesional, directo y cercano. Como explicarle un problema técnico a un compañero senior.
                - PROHIBIDO lenguaje naíf/infantil: 'trasteando', 'una pasada', 'jugando con', 'cositas', 'chulo'.
                - PROHIBIDO humo corporativo: 'revolucionario', 'encantado de anunciar', 'game-changer', 'orgulloso de compartir'.
                - PROHIBIDO TEXTO APELOTONADO EN MÓVIL:
                  * Deja SIEMPRE una línea en blanco ('\\n\\n') entre cada viñeta ('• ') y la siguiente. Jamás pongas dos viñetas en líneas consecutivas.
                  * Cada viñeta ('• ') debe tener MÁXIMO 15 palabras (máx. 110 caracteres, 1 sola idea corta).
                  * Párrafos muy cortos (máximo 2 frases por bloque). LinkedIn penaliza bloques densos de texto.

                ESTRUCTURA OBLIGATORIA (optimizada para el algoritmo de LinkedIn):

                1. HOOK (primera línea): Una frase impactante, un dato concreto o una pregunta provocadora.
                   Esto es lo que se ve ANTES del "ver más". Si no engancha aquí, nadie lee el resto.
                   Ejemplos buenos: "El 38% de nuestros drawdowns no eran fallos del modelo." / "Descubrimos que el problema no estaba en el código, sino en el libro de órdenes."

                2. CONTEXTO DEL PROBLEMA (2-3 líneas): Qué problema real encontraste en producción. Sin preámbulos.

                3. QUÉ HICISTE (3-4 líneas): Decisión técnica e implementación. Sé concreto: nombra tecnologías, patrones, métricas.

                4. RESULTADO CON DATOS (2-3 puntos): Impacto medible. Números > adjetivos.

                5. PREGUNTA ABIERTA A LA COMUNIDAD: Cierra con una pregunta genuina que invite a otros ingenieros a compartir su experiencia.
                   Ejemplos: "¿Habéis encontrado problemas similares de slippage en vuestros sistemas?" / "¿Qué estrategia usáis para monitorizar la huella de memoria en servicios long-running?"
                   La pregunta DEBE ser específica al tema del post, NO genérica.

                6. HASHTAGS (máximo 5): Técnicos y relevantes. Al final, separados del texto.

                REGLAS ADICIONALES DE ENGAGEMENT:
                - NO menciones "adjunto captura" ni "ver diagrama adjunto" — LinkedIn adjunta la imagen automáticamente.
                - Si el stack incluye tecnologías populares, menciónalo de forma que otros profesionales de ese stack se sientan interpelados.
                - Extensión ideal: 800-1300 caracteres (el sweet spot de LinkedIn para reach orgánico).

                DATOS DEL PROYECTO:
                - Proyecto: {project_name}
                - Título de referencia: {headline_title}
                - Problema / Contexto: {problem_context}
                - Implementación técnica: {implementation_details}
                - Hallazgos en logs/pruebas: {technical_findings}
                - Objetivos logrados: {bullets_str}
                - Stack: {stack_str}

                Genera SOLO el texto del post. Sin comillas, sin explicaciones meta, sin "aquí tienes el post".
                """

                for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt
                        )
                        if response.text and len(response.text.strip()) > 100:
                            return DevDiaryGenerator._format_clean_post(response.text.strip(), hashtags_line=hashtags_str)
                    except Exception:
                        continue
            except Exception as e:
                print(f"[!] Error llamando a Gemini: {e}. Usando formato riguroso de respaldo...")

        # Formato de respaldo optimizado para engagement en LinkedIn
        question = f"¿Habéis enfrentado retos similares trabajando con {stack_str} en producción? Me interesa conocer vuestro enfoque."
        fallback = f"""{headline_title}

{problem_context}

Implementación y resultados:

• {implementation_details}

• {technical_findings}

{bullets_str}

Stack: {" · ".join(tech_stack[:4])}

{question}

{hashtags_str}"""
        return DevDiaryGenerator._format_clean_post(fallback, hashtags_line=hashtags_str)
