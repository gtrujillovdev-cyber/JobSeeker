"""
Módulo ATS Analyzer (Applicant Tracking System) para HR Tech & LinkedIn Jobs.
Simula el análisis que realizan plataformas de RRHH (Greenhouse, Lever, Workday, LinkedIn Recruiter):
- Extracción de entidades (Hard Skills, Frameworks, Certificaciones, Requisitos excluyentes).
- Evaluación de afinidad semántica y keyword matching exacto.
- Score de compatibilidad (0-100%).
- Gap Analysis (habilidades coincidentes vs habilidades faltantes).
- Recomendación justificada del CV oficial idóneo.
"""

import re
from typing import Dict, Any, List, Set, Tuple
from pathlib import Path

# Taxonomía de tecnologías, certificaciones y conceptos clave IT para matching ATS
TECH_TAXONOMY = {
    "languages": [
        "python", "swift", "javascript", "typescript", "java", "kotlin", "bash", "shell",
        "sql", "c", "c++", "c#", "html", "css", "php", "ruby", "rust", "go", "golang"
    ],
    "frameworks_backend": [
        "fastapi", "django", "flask", "spring", "spring boot", "nodejs", "node.js",
        "express", "nestjs", "graphql", "rest", "restful", "api"
    ],
    "frameworks_frontend_mobile": [
        "swiftui", "uikit", "ios", "android", "jetpack compose", "react", "react native",
        "vue", "angular", "tailwind", "flutter"
    ],
    "devops_cloud_sys": [
        "linux", "debian", "ubuntu", "docker", "kubernetes", "k8s", "aws", "azure", "gcp",
        "ci/cd", "github actions", "gitlab ci", "terraform", "ansible", "nginx", "apache",
        "ssh", "tcp/ip", "dns", "vpn", "firewall", "wireguard", "proxmox", "virtualbox"
    ],
    "testing_qa": [
        "qa", "testing", "playwright", "selenium", "cypress", "pytest", "karate", "postman",
        "tdd", "sdet", "unit testing", "integration testing", "automation"
    ],
    "ai_data": [
        "ai", "ia", "llm", "rag", "langchain", "gemini", "openai", "machine learning",
        "deep learning", "pandas", "numpy", "scikit-learn", "etl", "data engineering", "nlp"
    ],
    "cybersecurity": [
        "ciberseguridad", "cybersecurity", "grc", "iso 27001", "ens", "soc", "siem", "edr",
        "owasp", "pentesting", "auditoría", "ot", "scada", "seguridad informática", "cve"
    ],
    "methodologies_tools": [
        "git", "github", "jira", "confluence", "scrum", "agile", "kanban", "devops",
        "dam", "daw", "asir", "fp", "grado superior"
    ]
}

# CVs Oficiales y sus núcleos de especialización para el matching ATS
CV_PROFILES_METADATA = {
    "GTV_CV_Sys_ES2026.pdf": {
        "profile_key": "sys_cyber",
        "label": "Sistemas Linux, Ciberseguridad & Infraestructura IT",
        "strong_keywords": [
            "linux", "ciberseguridad", "cybersecurity", "seguridad", "grc", "iso 27001",
            "ens", "soc", "redes", "networking", "tcp/ip", "dns", "firewall", "vpn", "ssh",
            "docker", "bash", "shell", "infraestructura", "sysadmin", "sistemas", "ot", "scada", "soporte"
        ],
        "weight_bias": 1.15
    },
    "GTV_CV_IA_ES2026.pdf": {
        "profile_key": "ai_python",
        "label": "Python Backend, IA & Automatización de Procesos",
        "strong_keywords": [
            "python", "ia", "ai", "llm", "rag", "fastapi", "django", "flask", "backend",
            "data", "etl", "machine learning", "pandas", "automatización", "sql", "api", "gemini", "openai"
        ],
        "weight_bias": 1.15
    },
    "GTV_CV_iOS_ES2026.pdf": {
        "profile_key": "ios_dam",
        "label": "Desarrollo Multiplataforma (DAM), SwiftUI & Full-Stack",
        "strong_keywords": [
            "dam", "multiplataforma", "ios", "swift", "swiftui", "mobile", "android", "frontend",
            "fullstack", "full stack", "full-stack", "typescript", "javascript", "react", "html", "css", "web"
        ],
        "weight_bias": 1.15
    },
    "GTV_CV_ES2026.pdf": {
        "profile_key": "qa_sdet",
        "label": "QA Automation, SDET & Software Developer General",
        "strong_keywords": [
            "qa", "testing", "automation", "playwright", "pytest", "selenium", "karate", "sdet",
            "calidad", "test", "desarrollo", "software", "git", "scrum", "junior"
        ],
        "weight_bias": 1.10
    }
}


class ATSAnalyzer:
    """Motor analítico ATS para evaluación y optimización de candidaturas."""

    @classmethod
    def extract_job_keywords(cls, title: str, description: str) -> Dict[str, List[str]]:
        """Extrae términos técnicos clasificados a partir del texto de la vacante."""
        text = f"{title} {description}".lower()
        extracted: Dict[str, List[str]] = {}

        for category, terms in TECH_TAXONOMY.items():
            found = []
            for term in terms:
                # Búsqueda exacta de palabra completa con límites de palabra (\b)
                pattern = r"\b" + re.escape(term) + r"\b"
                if re.search(pattern, text):
                    found.append(term)
            if found:
                extracted[category] = sorted(list(set(found)))

        return extracted

    @classmethod
    def analyze_match(cls, title: str, description: str, detected_stack: List[str] = None) -> Dict[str, Any]:
        """
        Calcula el Score ATS detallado para la vacante y determina cuál es el mejor CV oficial.
        Devuelve un desglose compatible con un dashboard de Recursos Humanos.
        """
        title_clean = (title or "").lower()
        desc_clean = (description or "").lower()
        stack = [s.lower() for s in (detected_stack or [])]

        extracted_categories = cls.extract_job_keywords(title_clean, desc_clean)
        all_required_keywords: Set[str] = set()
        for term_list in extracted_categories.values():
            all_required_keywords.update(term_list)
        all_required_keywords.update(stack)

        # Si no se detectaron keywords específicas, agregamos términos base de desarrollo
        if not all_required_keywords:
            all_required_keywords.update(["software", "desarrollo", "git", "python"])

        # Evaluar compatibilidad con cada CV oficial
        cv_evaluations: List[Dict[str, Any]] = []

        for cv_filename, meta in CV_PROFILES_METADATA.items():
            strong_set = set(meta["strong_keywords"])
            
            # Coincidencias en keywords principales
            matched = sorted(list(all_required_keywords.intersection(strong_set)))
            
            # Ponderación de título (si la keyword aparece en el título suma triple)
            title_matches = [kw for kw in matched if re.search(r"\b" + re.escape(kw) + r"\b", title_clean)]
            
            # Cálculo base
            raw_score = (len(matched) * 12) + (len(title_matches) * 20)
            
            # Factor de cobertura
            coverage_pct = (len(matched) / max(1, len(all_required_keywords))) * 100
            
            final_score = int(min(98, max(45, (raw_score * 0.5) + (coverage_pct * 0.5) * meta["weight_bias"])))
            
            # Gaps: keywords que pide la vacante pero que no están en el foco prioritario de este CV
            gaps = sorted(list(all_required_keywords - strong_set))[:5]

            cv_evaluations.append({
                "filename": cv_filename,
                "label": meta["label"],
                "profile_key": meta["profile_key"],
                "score": final_score,
                "matched_keywords": matched,
                "gaps": gaps,
                "title_hits": title_matches
            })

        # Ordenar por score descendente
        cv_evaluations.sort(key=lambda x: x["score"], reverse=True)
        best = cv_evaluations[0]

        # Clasificación ATS de visibilidad para el reclutador
        if best["score"] >= 80:
            ranking_tier = "Alta Visibilidad (Top 10% en LinkedIn Recruiter)"
            tier_badge = "🟢 ALTO MATCH"
        elif best["score"] >= 65:
            ranking_tier = "Buena Compatibilidad (Filtros estándar superados)"
            tier_badge = "🟡 MATCH MEDIO"
        else:
            ranking_tier = "Perfil General (Requiere validación de requisitos de soporte)"
            tier_badge = "⚪ PERFIL GENERAL"

        return {
            "best_cv": best["filename"],
            "best_label": best["label"],
            "best_profile_key": best["profile_key"],
            "ats_score": best["score"],
            "tier_badge": tier_badge,
            "ranking_tier": ranking_tier,
            "matched_keywords": best["matched_keywords"],
            "gaps": best["gaps"],
            "extracted_taxonomies": extracted_categories,
            "all_evaluations": cv_evaluations
        }

    @classmethod
    def format_hr_report(cls, analysis: Dict[str, Any], title: str, company: str) -> str:
        """Formatea un informe técnico de RRHH listo para presentar en Telegram o consola."""
        matched_str = ", ".join(f"`{k}`" for k in analysis["matched_keywords"][:8]) or "Perfil IT General"
        gaps_str = ", ".join(f"`{k}`" for k in analysis["gaps"][:4]) if analysis["gaps"] else "Ninguna crítica"
        
        return (
            f"🎯 *EVALUACIÓN ATS DE RECURSOS HUMANOS*\n"
            f"💼 *Puesto:* {title}\n"
            f"🏢 *Empresa:* {company}\n"
            f"📊 *Score ATS:* `{analysis['ats_score']}%` ({analysis['tier_badge']})\n"
            f"🏷 *Visibilidad Recruiter:* {analysis['ranking_tier']}\n\n"
            f"📄 *CV Oficial Seleccionado:* `{analysis['best_cv']}`\n"
            f"📌 *Especialidad:* {analysis['best_label']}\n\n"
            f"✅ *Keywords Coincidentes:* {matched_str}\n"
            f"⚠️ *Gaps Detectados:* {gaps_str}"
        )
