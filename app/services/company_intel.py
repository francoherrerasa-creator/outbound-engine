import json
import anthropic
from app.config import ANTHROPIC_API_KEY


def extract_company_intel(url: str) -> dict:
    """Read company URL and extract what they sell, value prop, typical clients."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Visita esta URL y analiza la empresa: {url}

Extrae la siguiente información:
1. Qué vende la empresa (productos y/o servicios principales)
2. Su propuesta de valor principal
3. Quiénes son sus clientes típicos
4. Industrias que atienden

Devuelve EXACTAMENTE un JSON con esta estructura:
{{
    "productos_servicios": "Descripción concisa de qué vende",
    "propuesta_valor": "Su propuesta de valor diferenciadora",
    "clientes_tipicos": "Perfil de sus clientes típicos",
    "industrias": ["lista", "de", "industrias"]
}}

Responde SOLO con el JSON, sin texto adicional ni markdown."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    result_text = result_text.strip()
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:-1])

    try:
        intel = json.loads(result_text)
    except json.JSONDecodeError:
        start = result_text.find("{")
        end = result_text.rfind("}") + 1
        if start != -1 and end > start:
            intel = json.loads(result_text[start:end])
        else:
            raise ValueError(f"Could not parse company intel: {result_text[:200]}")

    return intel
