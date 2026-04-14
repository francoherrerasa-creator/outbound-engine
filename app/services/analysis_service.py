import json
import logging
import re
from urllib.parse import quote_plus
import anthropic
from app.config import ANTHROPIC_API_KEY

logger = logging.getLogger("outbound-engine.analysis")


def _strip_citations(text: str) -> str:
    """Remueve tags <cite index="...">...</cite> dejando solo el texto interior."""
    return re.sub(r'</?cite[^>]*>', '', text)


def _fallback_analysis(company: dict) -> dict:
    """Análisis mínimo construido con los datos de búsqueda cuando Claude falla."""
    name = company.get("name", "Empresa")
    industry = company.get("industry", "N/A")
    city = company.get("city", "N/A")
    phone = (company.get("phone") or "").strip()
    size = (company.get("size_estimate") or "").strip()
    why = (company.get("why_matches") or "").strip()

    resumen = f"Empresa de {industry} en {city}."
    if why:
        resumen += f" {why}"
    elif size:
        resumen += f" Tamaño estimado: {size}."

    linkedin_search = (
        "https://www.google.com/search?q="
        + quote_plus(f"site:linkedin.com {name} {city}")
    )

    outreach = (
        f"Hola, vi que {name} opera en {industry} en {city}. "
        "Me gustaría platicar rápido sobre cómo podríamos apoyar su operación — "
        "¿tienes 5 minutos esta semana?"
    )

    return {
        "resumen_ejecutivo": resumen,
        "senales_compra": ["Empresa pequeña en zona industrial — potencial comprador"],
        "contacto_ideal": {
            "cargo": "Dueño/Director General",
            "nombre_sugerido": "Por investigar",
            "linkedin_search": linkedin_search,
            "telefono_empresa": phone,
            "email_empresa": "",
            "approach": "Contactar directo por teléfono o WhatsApp",
        },
        "mensaje_outreach": outreach,
        "score": 50,
        "score_justification": "Score base — información limitada, requiere investigación",
    }


def _build_context(company: dict, icp: dict) -> str:
    intel = icp.get('company_intel', {})
    intel_block = ""
    if intel:
        intel_block = f"""
SOBRE LA EMPRESA VENDEDORA (lo que vende):
- Productos/servicios: {intel.get('productos_servicios', 'N/A')}
- Propuesta de valor: {intel.get('propuesta_valor', 'N/A')}
- Clientes típicos: {intel.get('clientes_tipicos', 'N/A')}
"""

    return f"""EMPRESA PROSPECTO:
- Nombre: {company['name']}
- Industria: {company['industry']}
- Ciudad: {company.get('city', 'No disponible')}
- Tamaño estimado: {company.get('size_estimate', 'No disponible')}
- Sitio web: {company.get('website', 'No disponible')}
- Por qué encaja: {company.get('why_matches', 'No disponible')}

CONTEXTO DEL ICP:
- Industria objetivo: {icp['target_industry']}
- Tipo de cliente: {icp['client_type']}
- Momento de empresa buscado: {icp['buying_signal']}
{intel_block}"""


def _parse_json(text: str, open_char: str = "{") -> dict | list:
    text = _strip_citations(text).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        close_char = "}" if open_char == "{" else "]"
        start = text.find(open_char)
        end = text.rfind(close_char) + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse JSON: {text[:200]}")


def analyze_company_quick(company: dict, icp: dict) -> dict:
    """Quick analysis: summary, signals, contact, outreach. Low token usage.
    Falls back to a minimal analysis built from search data if Claude fails."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    context = _build_context(company, icp)

    prompt = f"""Eres un consultor estratégico B2B. Analiza brevemente esta empresa prospecto para "{icp['company_name']}".

{context}

Busca información actualizada sobre esta empresa en internet.

El análisis debe ser CORTO y DIRECTO — es una empresa pequeña, no un corporativo.

BÚSQUEDA AGRESIVA DE DECISION MAKER:
Para encontrar al decision maker, busca en TODAS estas fuentes:
1. Página de Facebook de la empresa (muchas PyMEs tienen el nombre del dueño en "Información")
2. Google Maps reviews (a veces el dueño responde con su nombre)
3. Directorio empresarial (Sección Amarilla, DENU, Kompass)
4. Registro público de comercio (si hay acta constitutiva pública)
5. Páginas de empleo (Indeed, Computrabajo — el contacto suele ser el dueño)
6. WhatsApp Business (si el número aparece en web, el perfil puede tener el nombre)

Si encuentras un teléfono de la empresa en CUALQUIER fuente, inclúyelo en telefono_empresa.
Si encuentras un email, inclúyelo en email_empresa.
El nombre del dueño de una empresa pequeña es el dato más valioso — búscalo agresivamente.

Devuelve EXACTAMENTE un JSON con esta estructura:
{{
    "resumen_ejecutivo": "Máximo 3 líneas: qué hace la empresa y por qué es buen prospecto",
    "senales_compra": ["máximo 3 señales concretas detectadas"],
    "contacto_ideal": {{
        "cargo": "Cargo del decisor ideal (ej: Director General, Dueño, Gerente de Operaciones)",
        "nombre_sugerido": "Nombre real si lo encuentras, o 'Por investigar'",
        "linkedin_search": "URL en formato https://www.google.com/search?q=site:linkedin.com+NOMBRE+EMPRESA (reemplaza NOMBRE por el nombre sugerido y EMPRESA por el nombre de la empresa, separando palabras con +)",
        "telefono_empresa": "Teléfono si está en la web, sino ''",
        "email_empresa": "Email si está en la web, sino ''",
        "approach": "1 frase sobre cómo contactarlo (ej: 'Contactar por WhatsApp mencionando que vimos su operación en Tampico')"
    }},
    "mensaje_outreach": "Máximo 4 líneas. Tono directo y personal, como mensaje de WhatsApp (NO email corporativo). Tutea. Menciona un dato concreto del prospecto y conéctalo con un problema real que resuelve la empresa vendedora.",
    "score": 85,
    "score_justification": "Justificación del score 0-100"
}}

IMPORTANTE: NO incluyas FODA, benchmark ni modelo de negocio — eso es solo para el análisis profundo.
IMPORTANTE: NO incluyas tags de citación como <cite> en tu respuesta. Solo texto plano.
Responde SOLO con el JSON, sin texto adicional."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        return _parse_json(result_text)
    except Exception as e:
        logger.warning(
            "analyze_company_quick failed for %s, returning fallback: %s",
            company.get("name", "?"),
            e,
        )
        return _fallback_analysis(company)


def analyze_company_deep(company: dict, icp: dict) -> dict:
    """Deep analysis: FODA, business model, benchmark. Called on demand."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    context = _build_context(company, icp)

    prompt = f"""Eres un consultor estratégico B2B de alto nivel. Genera un análisis profundo de esta empresa prospecto.

{context}

Busca información actualizada sobre esta empresa en internet y genera:

Devuelve EXACTAMENTE un JSON con esta estructura:
{{
    "foda": {{
        "fortalezas": ["lista de fortalezas identificadas"],
        "oportunidades": ["oportunidades de mercado"],
        "debilidades": ["debilidades o áreas de mejora"],
        "amenazas": ["amenazas del entorno"]
    }},
    "modelo_negocio": "Descripción del modelo de negocio en 2-3 frases",
    "benchmark": "Comparación con competidores principales en 2-3 frases"
}}

IMPORTANTE: NO incluyas tags de citación como <cite> en tu respuesta. Solo texto plano.
Responde SOLO con el JSON, sin texto adicional."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    return _parse_json(result_text)
