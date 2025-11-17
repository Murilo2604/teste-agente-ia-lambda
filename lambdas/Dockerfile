# ============================================================
# 🧱 Stage 1 - Builder: instala dependências isoladamente
# ============================================================
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

# Copia o binário do UV (gerenciador de dependências)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /build

# Instala dependências de compilação apenas temporariamente
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia somente os arquivos de dependência
COPY src/pyproject.toml src/uv.lock ./

# Instala dependências num diretório temporário (melhor pra cache e tamanho)
RUN uv pip install --no-cache --target=/deps .

# ============================================================
# 🐍 Stage 2 - Final: imagem de produção leve
# ============================================================
FROM public.ecr.aws/docker/library/python:3.12-slim

LABEL maintainer="GCB AI Team" \
      description="GCB AI Agent - Contract Processing with Docling and OpenAI" \
      version="1.0"

# Define Lambda task root (padrão AWS Lambda)
ENV LAMBDA_TASK_ROOT=/var/task
WORKDIR ${LAMBDA_TASK_ROOT}

# Variáveis de ambiente para Lambda e ML frameworks
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    # RapidOCR configuration
    RAPIDOCR_HOME=/tmp/rapidocr_models \
    # PyTorch configuration
    TORCH_HOME=/tmp/torch \
    # HuggingFace/Transformers configuration
    HF_HOME=/tmp/huggingface \
    TRANSFORMERS_CACHE=/tmp/transformers \
    HUGGINGFACE_HUB_CACHE=/tmp/huggingface/hub \
    # Docling-specific configuration
    DOCLING_SERVE_ARTIFACTS_PATH=/tmp/docling_models \
    DOCLING_SERVE_SCRATCH_PATH=/tmp/docling_scratch \
    # Generic cache directories
    XDG_CACHE_HOME=/tmp/.cache \
    # Sentence Transformers
    SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers

# Instala apenas libs necessárias pro runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmupdf-dev \
        mupdf-tools \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Instala o AWS Lambda Runtime Interface Client
RUN pip install --no-cache-dir awslambdaric

# Instala o AWS Lambda Runtime Interface Emulator (para testes locais)
RUN curl -Lo /usr/local/bin/aws-lambda-rie \
    https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie && \
    chmod +x /usr/local/bin/aws-lambda-rie

# Copia dependências do builder (sem camadas pesadas do sistema)
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages

# Copia apenas o código-fonte necessário
COPY src/ ${LAMBDA_TASK_ROOT}/

# Create symlink for RapidOCR models to point to /tmp (must be done at build time)
# RapidOCR hardcodes its model path and doesn't respect environment variables
# The symlink target (/tmp/rapidocr_models) will be created at runtime by pdf_parser.py
RUN if [ -d "/usr/local/lib/python3.12/site-packages/rapidocr/models" ]; then \
        rm -rf /usr/local/lib/python3.12/site-packages/rapidocr/models; \
    fi && \
    ln -sf /tmp/rapidocr_models /usr/local/lib/python3.12/site-packages/rapidocr/models && \
    echo "✓ RapidOCR models symlink created"

# ENTRYPOINT usa diretamente o AWS Lambda Runtime Interface Client
ENTRYPOINT ["python", "-m", "awslambdaric"]

# CMD especifica o handler no formato módulo.função
CMD ["main.handler"]