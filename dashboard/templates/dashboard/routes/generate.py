from fastapi import APIRouter
router = APIRouter(prefix="/generate", tags=["Geração"])

@router.post("/dialogos")
async def generate_dialogos(quantidade: int = 500, tipo: str = "auto"):
    # Chama dialogos.py via subprocess ou função
    return {"status": "ok", "generated": quantidade, "tipo": tipo}