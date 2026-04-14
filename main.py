import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import prospects
from app.services.sheets_service import get_prospects

app = FastAPI(title="Outbound Engine", version="1.0.0")

# CORS — en producción solo el dashboard de Vercel, en desarrollo cualquier origen
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
cors_origins = (
    ["https://leads-road-tractovan.vercel.app"]
    if ENVIRONMENT == "production"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(prospects.router)


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    return FileResponse("app/templates/index.html")


@app.get("/prospects")
async def listar_prospects():
    """Devuelve todos los prospects de la pestaña Outbound en formato JSON para el dashboard de Road Tractovan."""
    prospects_list = get_prospects()
    return {"total": len(prospects_list), "prospects": prospects_list}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
