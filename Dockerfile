# Stage 1 — Build da Interface React 19 + Three.js + Spell UI WebGL
FROM node:22-alpine AS ui-builder

WORKDIR /build/ui/react-app
COPY ui/react-app/package*.json ./
RUN npm ci

WORKDIR /build
COPY ui/static ./ui/static
COPY ui/react-app ./ui/react-app
WORKDIR /build/ui/react-app
RUN npm run build

# Stage 2 — Runtime enxuto FastAPI + ChromaDB ONNX + Edge Neural TTS
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False \
    CHROMA_TELEMETRY=False \
    FRYIVS_MODE=web \
    FRYIVS_DATA_DIR=/data \
    LLM_PROVIDER=gemini

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt \
    && python -c "import chromadb.utils.embedding_functions as ef; ef.DefaultEmbeddingFunction()(['fryivs'])"

COPY core ./core
COPY skills ./skills
COPY data/respostas_cache.json ./data/respostas_cache.json
COPY oragnizacoes_ideias/base_conhecimento ./oragnizacoes_ideias/base_conhecimento
COPY ui/index.html ./ui/index.html
COPY ui/static ./ui/static
COPY --from=ui-builder /build/ui/static/react ./ui/static/react
COPY icons8.json server.py ./

RUN mkdir -p /data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

