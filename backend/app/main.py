from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import auth, budgets, cards, categories, expenses, insights, loans, recurring

app = FastAPI(
    title="spend-a-thon API",
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

if get_settings().cors_origins:  # only needed for local dev without the Vite proxy
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    return response


api = APIRouter(prefix="/api")


@api.get("/health")
def health():
    return {"ok": True}


for r in (auth.router, expenses.router, budgets.router, recurring.router, categories.router,
          cards.router, loans.router, insights.router):
    api.include_router(r)

app.include_router(api)
