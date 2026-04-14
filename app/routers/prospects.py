from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.company_intel import extract_company_intel
from app.services.search_service import search_companies
from app.services.analysis_service import analyze_company_quick, analyze_company_deep
from app.services.sheets_service import save_prospect

router = APIRouter(prefix="/api", tags=["prospects"])

# In-memory store for current session
_current_icp: dict = {}
_company_intel: dict = {}
_found_companies: list[dict] = []
_analyses: dict[str, dict] = {}  # company_name -> analysis


class ICPRequest(BaseModel):
    company_name: str
    company_url: str
    target_industry: str
    company_size: str
    region: str
    client_type: str
    buying_signal: str


class ApproveRequest(BaseModel):
    company_name: str


@router.post("/search")
async def search(icp: ICPRequest):
    """Extract company intel, then search for matching companies."""
    global _current_icp, _company_intel, _found_companies, _analyses
    _current_icp = icp.model_dump()
    _analyses = {}

    try:
        _company_intel = extract_company_intel(icp.company_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analizando tu empresa: {str(e)}")

    _current_icp["company_intel"] = _company_intel

    try:
        _found_companies = search_companies(_current_icp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")

    return {"companies": _found_companies, "count": len(_found_companies)}


@router.post("/analyze/{company_index}")
async def analyze(company_index: int):
    """Generate quick analysis for a specific company."""
    if company_index < 0 or company_index >= len(_found_companies):
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    company = _found_companies[company_index]

    if company["name"] in _analyses:
        return {"company": company, "analysis": _analyses[company["name"]]}

    try:
        analysis = analyze_company_quick(company, _current_icp)
        _analyses[company["name"]] = analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en análisis: {str(e)}")

    return {"company": company, "analysis": analysis}


@router.post("/analyze-deep/{company_index}")
async def analyze_deep(company_index: int):
    """Generate deep FODA + benchmark analysis on demand."""
    if company_index < 0 or company_index >= len(_found_companies):
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    company = _found_companies[company_index]

    # If deep already cached, return it
    existing = _analyses.get(company["name"], {})
    if "foda" in existing:
        return {"company": company, "analysis": existing}

    try:
        deep = analyze_company_deep(company, _current_icp)
        _analyses[company["name"]].update(deep)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en análisis profundo: {str(e)}")

    return {"company": company, "analysis": _analyses[company["name"]]}


@router.post("/approve")
async def approve(req: ApproveRequest):
    """Approve a prospect and save to Google Sheets."""
    company = next((c for c in _found_companies if c["name"] == req.company_name), None)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    analysis = _analyses.get(req.company_name)
    if not analysis:
        raise HTTPException(status_code=400, detail="Empresa no analizada aún")

    try:
        sheet_url = save_prospect(company, analysis)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando en Sheets: {str(e)}")

    return {"status": "approved", "company": req.company_name, "sheet_url": sheet_url}


@router.post("/reject")
async def reject(req: ApproveRequest):
    """Reject a prospect (just removes from consideration)."""
    return {"status": "rejected", "company": req.company_name}


@router.get("/queue")
async def get_queue():
    """Get all companies with their analyses for the approval queue."""
    queue = []
    for company in _found_companies:
        item = {"company": company}
        if company["name"] in _analyses:
            item["analysis"] = _analyses[company["name"]]
        queue.append(item)
    return {"queue": queue}
