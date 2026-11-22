# HireX on Hugging Face Spaces (Docker SDK). Built from the bundle that
# backend/scripts/make_deploy_bundle.py writes to deploy/build/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    ENVIRONMENT=production \
    ENABLE_SCHEDULER=false \
    FRONTEND_DIST=/home/user/app/frontend/dist

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# CPU-only torch first (the default wheel pulls several GB of CUDA).
COPY --chown=user backend/requirements-deploy.txt backend/requirements-deploy.txt
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r backend/requirements-deploy.txt \
 && python -m spacy download en_core_web_sm

USER user
# Bake the sentence encoder into the image so the first request does not download it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY --chown=user . .

WORKDIR /home/user/app/backend
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
