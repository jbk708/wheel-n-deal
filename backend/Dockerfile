FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

# Install system dependencies
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

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false

# Set working directory
WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry install --no-root --without dev

# Copy application code
COPY . .

# Create log directory
RUN mkdir -p /app/logs && \
    touch /app/logs/wheel_n_deal.log && \
    touch /app/logs/errors.log && \
    chmod -R 777 /app/logs

# Expose port
EXPOSE 8000

# Set default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
