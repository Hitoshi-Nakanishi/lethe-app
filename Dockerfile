FROM python:3.14.4-slim-bookworm

ARG USERNAME=app
ARG USER_UID=1000
ARG USER_GID=1000
ARG TASK_VERSION=3.51.1

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/opt/lethe/.venv
ENV UV_CACHE_DIR=/home/app/.cache/uv
ENV UV_LINK_MODE=copy
ENV XDG_CACHE_HOME=/home/app/.cache
ENV HF_HOME=/home/app/.cache/huggingface
ENV LETHE_CONFIG=/workspace/lethe-app/docker/default.toml
ENV PATH="/opt/lethe/.venv/bin:/home/app/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        libasound2 \
        libasound2-plugins \
        libgomp1 \
        libportaudio2 \
        libpulse0 \
        libtcl8.6 \
        libtk8.6 \
        libx11-6 \
        libxext6 \
        libxft2 \
        libxrender1 \
        libxss1 \
        openssh-client \
        pkg-config \
        portaudio19-dev \
        sudo \
        tk \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    if ! getent group "${USER_GID}" >/dev/null; then \
        groupadd --gid "${USER_GID}" "${USERNAME}"; \
    fi; \
    if id -u "${USERNAME}" >/dev/null 2>&1; then \
        usermod --uid "${USER_UID}" --gid "${USER_GID}" "${USERNAME}"; \
    elif getent passwd "${USER_UID}" >/dev/null; then \
        existing_user="$(getent passwd "${USER_UID}" | cut -d: -f1)"; \
        usermod --login "${USERNAME}" --home "/home/${USERNAME}" --move-home --gid "${USER_GID}" "${existing_user}"; \
    else \
        useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home "${USERNAME}"; \
    fi; \
    mkdir -p /workspace/lethe-app /opt/lethe /home/${USERNAME}/.cache; \
    chown -R "${USER_UID}:${USER_GID}" /workspace/lethe-app /opt/lethe /home/${USERNAME}; \
    echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}"; \
    chmod 0440 "/etc/sudoers.d/${USERNAME}"

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) task_arch="amd64" ;; \
        arm64) task_arch="arm64" ;; \
        *) echo "Unsupported architecture for Task: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_linux_${task_arch}.tar.gz" -o /tmp/task.tar.gz; \
    tar -xzf /tmp/task.tar.gz -C /usr/local/bin task; \
    chmod +x /usr/local/bin/task; \
    rm /tmp/task.tar.gz

RUN python -m pip install --no-cache-dir --upgrade pip uv

WORKDIR /workspace/lethe-app

COPY --chown=${USER_UID}:${USER_GID} pyproject.toml uv.lock README.md default.toml ./
COPY --chown=${USER_UID}:${USER_GID} docker ./docker
COPY --chown=${USER_UID}:${USER_GID} src ./src

USER ${USERNAME}

RUN uv sync --frozen --dev

CMD ["bash"]
