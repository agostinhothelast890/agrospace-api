from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AgroSpace API", version="0.1.0")

# Permite que o frontend (outro domínio) chame a API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "AgroSpace API", "version": "0.1.0"}


@app.get("/api/health")
def health():
    return {"status": "ok"}
