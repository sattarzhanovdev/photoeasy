FROM python:3.10.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create workdir
WORKDIR /app

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libopenblas-dev liblapack-dev \
    libavutil-dev \
    && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY req.txt .

RUN uv pip install --no-cache-dir -r req.txt --system
#RUN --mount=type=cache,target=/root/.cache/uv \
#    --mount=type=bind,source=uv.lock,target=uv.lock \
#    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
#    uv sync --frozen --no-install-project
#


# Copy the project into the image
COPY . .
#
## Sync the project
#RUN --mount=type=cache,target=/root/.cache/uv \
#    uv sync --frozen


# Run server
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["sh", "./entrypoint.sh"]