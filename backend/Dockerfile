# Use the official Python image as the base image
FROM python:3.10-slim

# Install system dependencies, Chrome, ChromeDriver, and utilities
RUN apt-get update && \
    apt-get install -y wget curl unzip gnupg --no-install-recommends && \
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable \
    chromium-driver \
    openjdk-17-jre \
    --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Poetry for dependency management
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    /root/.local/bin/poetry --version  # Use the full path to check Poetry installation

# Set Poetry path
ENV PATH="/root/.local/bin:$PATH"

# Set the working directory inside the container
WORKDIR /app

# Copy dependency files first to leverage Docker cache
COPY pyproject.toml poetry.lock ./

# Install Python dependencies using Poetry
RUN /root/.local/bin/poetry install --no-root

# Copy the rest of the application code into the container
COPY . .

# Expose the port that FastAPI will run on
EXPOSE 8000

# Start the FastAPI server using Uvicorn
CMD ["/root/.local/bin/poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
