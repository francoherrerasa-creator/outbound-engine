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

    industry_lower = (icp.get('target_industry') or '').lower()
    region = icp.get('region', '')
    is_transport = any(k in industry_lower for k in [
        "transporte", "autotransporte", "logistic", "logíst", "fletes", "carga", "trucking", "camion"
    ])
    if is_transport:
        transport_strategies = f"""
ESTRATEGIAS DE BÚSQUEDA ESPECÍFICAS PARA AUTOTRANSPORTE EN MÉXICO:
Las empresas pequeñas de transporte casi nunca tienen sitio web corporativo. Tienes que buscarlas donde SÍ están:

1. DIRECTORIOS DE TRANSPORTE:
   - "directorio transportistas {region}"
   - "empresas autotransporte federal {region}"
   - "páginas amarillas transporte carga {region}"

2. MARKETPLACES Y BOLSAS DE CARGA:
   - "empresa transporte carga {region} camiones contacto"
   - "fletes {region} contacto teléfono"
   - "bolsa de carga {region} transportistas"

3. REDES SOCIALES DE NEGOCIO (Facebook Business es oro para pymes mexicanas):
   - "transporte de carga {region} site:facebook.com"
   - "transportista independiente {region} facebook"
   - "autotransporte {region} facebook página"

4. BÚSQUEDA POR NECESIDAD (señales de compra):
   - "empresa transporte {region} renta camiones"
   - "transportista busca tractocamión {region}"
   - "cooperativa transportistas {region}"

5. BASES PÚBLICAS / REGULATORIAS:
   - "permiso autotransporte federal {region} SCT"
   - "concesionarios SCT autotransporte {region}"
   - "padrón transportistas {region}"

PRIORIDADES DE FILTRADO:
- PRIORIZA empresas que NO tengan sitio web corporativo (las grandes sí lo tienen; las chicas no). Un perfil de Facebook o una ficha en directorio es señal positiva, no negativa.
- Si encuentras la empresa en páginas amarillas, Sección Amarilla, Cylex, Infobel, Facebook Business → INCLÚYELA con el teléfono que aparezca.
- Incluye el TELÉFONO de contacto cuando lo veas en el directorio (en pymes mexicanas es más útil que el email).
- Estima el tamaño por SEÑALES INDIRECTAS cuando no hay dato oficial: número de camiones mencionados en su perfil, cantidad de empleados reportados en Facebook, fotos de flota en el directorio, reseñas, año de fundación, etc. Anota qué señal usaste.
- Si sólo encuentras el nombre comercial (no razón social), está bien — úsalo tal cual.
- NO inventes empresas. Si no encuentras lo suficiente, devuelve menos de 10 pero todas reales.
"""
    else:
        transport_strategies = ""

    prompt = f"""Eres un experto en investigación de mercado B2B. Necesito que busques en internet empresas REALES que coincidan con este Perfil de Cliente Ideal (ICP):

- Empresa vendedora: {icp['company_name']}
- Industria objetivo: {icp['target_industry']}
- Tamaño de empresa objetivo: {icp['company_size']}
- Región: {icp['region']}
- Tipo de cliente: {icp['client_type']}
- Momento de la empresa objetivo: {icp['buying_signal']}
{intel_block}
{size_instructions}
{transport_strategies}
INSTRUCCIONES:
1. Busca en la web empresas REALES que operen en la industria "{icp['target_industry']}" en la región "{icp['region']}"
2. Que tengan el tamaño aproximado de "{icp['company_size']}"
3. Que sean del tipo "{icp['client_type']}"
4. Que estén en un momento de: "{icp['buying_signal']}"
5. Que sean potenciales compradores de lo que vende la empresa vendedora

Devuelve EXACTAMENTE un JSON array con 5 a 10 empresas reales. Cada objeto debe tener:
- "name": nombre real de la empresa (comercial o razón social)
- "industry": industria específica
- "city": ciudad donde opera
- "size_estimate": tamaño estimado (empleados, facturación, o señal indirecta — ej: "~8 camiones según Facebook")
- "website": sitio web real si lo tiene; si no hay web pero SÍ tiene ficha en directorio/Facebook, pon esa URL
- "phone": teléfono si lo encuentras en el directorio/Facebook/ficha, sino ""
- "source": dónde la encontraste (ej: "Sección Amarilla", "Facebook Business", "Directorio SCT")
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
