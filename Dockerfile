FROM python:3.10.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libopenblas-dev \
    liblapack-dev \
    libatlas-base-dev \
    libavutil-dev \
    && rm -rf /var/lib/apt/lists/*

# Fixes for dlib building on weak CPUs
ENV DLIB_USE_CUDA=0
ENV DLIB_NO_GUI_SUPPORT=1
ENV CFLAGS="-O3"
ENV CXXFLAGS="-O3 -DDLIB_USE_BLAS -DDLIB_USE_LAPACK -Wno-strict-aliasing"

COPY req.txt .

RUN uv pip install --no-cache-dir -r req.txt --system

COPY . .

COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["sh", "./entrypoint.sh"]