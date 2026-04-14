import json
import anthropic
from app.config import ANTHROPIC_API_KEY


def search_companies(icp: dict) -> list[dict]:
    """Use Claude API with web search to find real companies matching the ICP."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    intel = icp.get('company_intel', {})
    intel_block = ""
    if intel:
        intel_block = f"""
SOBRE LA EMPRESA VENDEDORA (extraído de su web):
- Productos/servicios: {intel.get('productos_servicios', 'N/A')}
- Propuesta de valor: {intel.get('propuesta_valor', 'N/A')}
- Clientes típicos: {intel.get('clientes_tipicos', 'N/A')}
- Industrias que atiende: {', '.join(intel.get('industrias', []))}
"""

    size_lower = (icp.get('company_size') or '').lower()
    if any(k in size_lower for k in ["pequeñ", "micro"]):
        size_instructions = """
FILTRO DE TAMAÑO CRÍTICO:
Busca SOLO empresas pequeñas con menos de 50 empleados. NO incluyas empresas grandes como Grupo Castores, FEMSA Logística, Bimbo Transport, etc. Busca transportistas independientes, empresas familiares, operadores con 1-20 camiones.
"""
    elif "median" in size_lower:
        size_instructions = """
FILTRO DE TAMAÑO CRÍTICO:
Busca empresas de 50-200 empleados. NO incluyas corporativos con más de 500 empleados.
"""
    else:
        size_instructions = ""

    prompt = f"""Eres un experto en investigación de mercado B2B. Necesito que busques en internet empresas REALES que coincidan con este Perfil de Cliente Ideal (ICP):

- Empresa vendedora: {icp['company_name']}
- Industria objetivo: {icp['target_industry']}
- Tamaño de empresa objetivo: {icp['company_size']}
- Región: {icp['region']}
- Tipo de cliente: {icp['client_type']}
- Momento de la empresa objetivo: {icp['buying_signal']}
{intel_block}
{size_instructions}
INSTRUCCIONES:
1. Busca en la web empresas REALES que operen en la industria "{icp['target_industry']}" en la región "{icp['region']}"
2. Que tengan el tamaño aproximado de "{icp['company_size']}"
3. Que sean del tipo "{icp['client_type']}"
4. Que estén en un momento de: "{icp['buying_signal']}"
5. Que sean potenciales compradores de lo que vende la empresa vendedora

Devuelve EXACTAMENTE un JSON array con 5 a 10 empresas reales. Cada objeto debe tener:
- "name": nombre real de la empresa
- "industry": industria específica
- "city": ciudad donde opera
- "size_estimate": tamaño estimado (empleados o facturación)
- "website": sitio web real si lo encuentras
- "why_matches": por qué encaja con el ICP (1-2 frases)

Responde SOLO con el JSON array, sin texto adicional ni markdown."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text from response blocks
    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    # Parse JSON from response
    result_text = result_text.strip()
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:-1])

    try:
        companies = json.loads(result_text)
    except json.JSONDecodeError:
        # Try to extract JSON array from the text
        start = result_text.find("[")
        end = result_text.rfind("]") + 1
        if start != -1 and end > start:
            companies = json.loads(result_text[start:end])
        else:
            raise ValueError(f"Could not parse companies from response: {result_text[:200]}")

    return companies
