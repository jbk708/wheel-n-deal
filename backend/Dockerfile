FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y wget curl unzip gnupg --no-install-recommends && \
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable \
    chromium-driver \
    openjdk-17-jre \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install signal-cli
RUN curl -L -o signal-cli.tar.gz https://github.com/AsamK/signal-cli/releases/download/v0.11.3/signal-cli-0.11.3-Linux.tar.gz && \
    tar xf signal-cli.tar.gz -C /opt && \
    ln -sf /opt/signal-cli-0.11.3/bin/signal-cli /usr/local/bin/ && \
    rm signal-cli.tar.gz

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    poetry --version

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app
COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root

COPY . .
EXPOSE 8000

# The CMD will be overridden by docker-compose.yml
