FROM debian:bookworm-slim

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential wget sbcl libgmp-dev libreadline-dev libncurses5-dev \
        python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install FriCAS 1.3.11 from source (pinned)
WORKDIR /opt/build
RUN wget -q \
    https://github.com/fricas/fricas/releases/download/1.3.11/fricas-1.3.11.tar.bz2 \
    && tar xjf fricas-1.3.11.tar.bz2 \
    && cd fricas-1.3.11 \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && cd /opt && rm -rf /opt/build

# Server script
COPY server.py /server.py

ENV FRICAS_BIN=fricas
ENV FRICAS_CACHE_DIR=/var/cache/fricas_runtime

RUN mkdir -p /var/cache/fricas_runtime

HEALTHCHECK --interval=10s --timeout=5s CMD \
    echo '{"method":"ping","params":{},"id":0}' | python3 /server.py | grep -q pong

ENTRYPOINT ["python3", "/server.py"]
