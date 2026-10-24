# Multi-Stage / Lightweight Production Image for Assault MLOps Dashboard
# Compatible with Hugging Face Spaces (Free Tier), Render, Fly.io, and Local Docker
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HOST=0.0.0.0

WORKDIR /app

# Install minimal OS dependencies for network & C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight CPU-only Python dependencies
COPY requirements-cloud.txt /app/requirements-cloud.txt
RUN pip install --no-cache-dir -r requirements-cloud.txt

# Copy complete application code, assets, docs, prebuilt frontend dist, and run data
COPY assault_model/ /app/assault_model/
COPY assault_backend/ /app/assault_backend/
COPY assault_rag/ /app/assault_rag/
COPY agents/ /app/agents/
COPY mlops/ /app/mlops/
COPY voec_sim/ /app/voec_sim/
COPY assets/ /app/assets/
COPY curriculums/ /app/curriculums/
COPY docs/ /app/docs/
COPY site/ /app/site/
# Ensure runtime directories exist (not tracked in git due to large checkpoints)
RUN mkdir -p /app/runs /app/runs_curriculum /app/runs_curriculum/experiments/reporting

# Create non-root user (UID 1000) for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user && \
    chown -R user:user /app

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

EXPOSE 7860

# Start reporting viewer with full React SPA, DuckDB analytics, and Replay Viewer
# Host 0.0.0.0 and port from $PORT (defaults to 7860 if not specified by cloud provider)
CMD ["python", "-m", "mlops.reporting.viewer", "--host", "0.0.0.0"]
