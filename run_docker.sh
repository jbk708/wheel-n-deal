#!/bin/bash

# Function to start the docker compose services
start_services() {
  echo "Starting Docker Compose services..."
  docker compose up --build -d
}

# Function to stop the docker compose services
stop_services() {
  echo "Stopping Docker Compose services..."
  docker compose down
}

# Function to restart the docker compose services
restart_services() {
  echo "Restarting Docker Compose services..."
  docker compose down
  docker compose up --build -d
}

# Function to view logs
view_logs() {
  echo "Displaying Docker logs..."
  docker compose logs -f
}

# Function to display usage instructions
usage() {
  echo "Usage: $0 {start|stop|restart|logs}"
  exit 1
}

# Check if any argument is provided
if [ $# -eq 0 ]; then
  usage
fi

# Main case to handle different script options
case "$1" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    restart_services
    ;;
  logs)
    view_logs
    ;;
  *)
    usage
    ;;
esac



