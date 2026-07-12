FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV NVM_DIR=/root/.nvm
ENV NODE_VERSION=22.23.1
ENV OPENCODE_VERSION=1.17.18
ENV PATH=/root/.local/bin:/root/.nvm/versions/node/v${NODE_VERSION}/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        docker.io \
        git \
        jq \
        nodejs \
        npm \
        procps \
        rsync \
        tar \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /opt/harbor
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY packages ./packages
COPY adapters ./adapters
COPY skills ./skills
COPY registry.json skills-lock.json ./

RUN uv sync --frozen

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install "$NODE_VERSION" \
    && nvm alias default "$NODE_VERSION" \
    && npm i -g "opencode-ai@$OPENCODE_VERSION" \
    && ln -sf "$(command -v opencode)" /usr/local/bin/opencode \
    && opencode --version

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) docker_arch="x86_64" ;; \
      arm64) docker_arch="aarch64" ;; \
      *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${docker_arch}/docker-27.5.1.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz; \
    docker --version

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) compose_arch="x86_64" ;; \
      arm64) compose_arch="aarch64" ;; \
      *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-${compose_arch}" -o /usr/local/lib/docker/cli-plugins/docker-compose; \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose; \
    docker compose version

RUN ln -sf /opt/harbor/.venv/bin/harbor /usr/local/bin/harbor \
    && ln -sf /opt/harbor/.venv/bin/harbor /usr/local/bin/hr \
    && harbor --help >/dev/null

WORKDIR /run/task
CMD ["bash", "-lc", "harbor --help"]
