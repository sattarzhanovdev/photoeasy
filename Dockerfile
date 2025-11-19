FROM python:3.10.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install Dependencies
RUN apt-get -y update && apt-get install -y --fix-missing \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    curl \
    graphicsmagick \
    libgraphicsmagick1-dev \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libswscale-dev \
    pkg-config \
    python3-dev \
    python3-numpy \
    software-properties-common \
    zip \
    && apt-get clean && rm -rf /tmp/* /var/tmp/*

# Virtual Environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

ENV CFLAGS=-static
RUN pip install --upgrade pip && \
    git clone -b 'v19.21' --single-branch https://github.com/davisking/dlib.git && \
    cd dlib/ && \
    python3 setup.py install --set BUILD_SHARED_LIBS=OFF

RUN pip install face_recognition

# Fixes for dlib building on weak CPUs
#ENV DLIB_USE_CUDA=0
#ENV DLIB_NO_GUI_SUPPORT=1
#ENV CFLAGS="-O3"
#ENV CXXFLAGS="-O3 -DDLIB_USE_BLAS -DDLIB_USE_LAPACK -Wno-strict-aliasing"
#ENV CMAKE_BUILD_PARALLEL_LEVEL=1

COPY req.txt .

RUN pip install --no-cache-dir -r req.txt

COPY . .

COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["sh", "./entrypoint.sh"]