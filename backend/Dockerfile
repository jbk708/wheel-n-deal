# Use the official Python image as the base image
FROM python:3.10-slim

# Install dependencies and signal-cli
RUN apt-get update && \
    apt-get install -y openjdk-11-jre curl && \
    curl -sSL https://github.com/AsamK/signal-cli/releases/download/v0.11.11/signal-cli-0.11.11-Linux.tar.gz | tar xz -C /opt/ && \
    ln -s /opt/signal-cli-0.11.11/bin/signal-cli /usr/local/bin/signal-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Set the working directory inside the container
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files into the container
COPY pyproject.toml poetry.lock ./

# Install dependencies using Poetry
RUN poetry install --no-root

# Copy the rest of the application code into the container
COPY . .

# Expose the port that FastAPI will run on
EXPOSE 8000

# Start the FastAPI server using Uvicorn
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

