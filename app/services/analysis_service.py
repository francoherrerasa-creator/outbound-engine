import json
import anthropic
from app.config import ANTHROPIC_API_KEY


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
    text = text.strip()
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
    """Quick analysis: summary, signals, contact, outreach. Low token usage."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    context = _build_context(company, icp)

    prompt = f"""Eres un consultor estratégico B2B. Analiza brevemente esta empresa prospecto para "{icp['company_name']}".

{context}

Busca información actualizada sobre esta empresa en internet.

El análisis debe ser CORTO y DIRECTO — es una empresa pequeña, no un corporativo.

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
Responde SOLO con el JSON, sin texto adicional."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    return _parse_json(result_text)


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
