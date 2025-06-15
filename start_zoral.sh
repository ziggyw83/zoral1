#!/bin/bash

OLLAMA_HOST="127.0.0.1"
OLLAMA_PORT=11434
FLASK_SCRIPT="zoral_chat.py"
MODEL_FILE="modelfile.zoral"
OLLAMA_LOG="ollama.log"
FLASK_LOG="flask.log"
MODEL_NAME="zoral"

echo "Starting Zoral setup..."

# Function to clean up processes
cleanup() {
    echo "Stopping Zoral..."
    [ -n "$FLASK_PID" ] && kill $FLASK_PID 2>/dev/null
    [ -n "$OLLAMA_PID" ] && kill -TERM -- -$OLLAMA_PID 2>/dev/null
    echo "Done."
    exit 0
}

# Trap Ctrl+C and SIGTERM
trap cleanup INT TERM

# Kill existing Ollama instances
echo "Killing existing Ollama processes..."
OLLAMA_PIDS=$(pgrep -f "ollama serve")
if [ -n "$OLLAMA_PIDS" ]; then
    for PID in $OLLAMA_PIDS; do
        kill -TERM $PID 2>/dev/null
    done
    sleep 1
fi

# Check if Ollama port is free
if nc -z $OLLAMA_HOST $OLLAMA_PORT 2>/dev/null; then
    echo "Error: Port $OLLAMA_PORT still in use after killing Ollama. Check for other services."
    exit 1
fi

# Verify Ollama is installed
if ! command -v ollama >/dev/null 2>&1; then
    echo "Error: Ollama not found. Install Ollama or check PATH."
    exit 1
fi

# Check if modelfile exists
if [ ! -f "$MODEL_FILE" ]; then
    echo "Error: $MODEL_FILE not found in current directory."
    exit 1
fi

# Create or update the zoral model
echo "Ensuring $MODEL_NAME model is created..."
if ! ollama list | grep -q "^$MODEL_NAME\s"; then
    echo "Creating $MODEL_NAME model..."
    if ! ollama create $MODEL_NAME -f "$MODEL_FILE" >> "$OLLAMA_LOG" 2>&1; then
        echo "Error: Failed to create $MODEL_NAME model. Check $OLLAMA_LOG:"
        tail -n 10 "$OLLAMA_LOG"
        exit 1
    fi
fi

# Start Ollama server
echo "Starting Ollama server on $OLLAMA_HOST:$OLLAMA_PORT..."
ollama serve >> "$OLLAMA_LOG" 2>&1 &
OLLAMA_PID=$!
for i in {1..15}; do
    if nc -z $OLLAMA_HOST $OLLAMA_PORT 2>/dev/null; then
        echo "Ollama server started (PID: $OLLAMA_PID)."
        break
    fi
    sleep 1
done
if [ $i -eq 15 ]; then
    echo "Error: Ollama failed to start. Check $OLLAMA_LOG:"
    tail -n 10 "$OLLAMA_LOG"
    kill -TERM -- -$OLLAMA_PID 2>/dev/null
    exit 1
fi

# Check Flask port
echo "Checking Flask port (127.0.0.1:5000)..."
if nc -z 127.0.0.1 5000 2>/dev/null; then
    echo "Error: Port 5000 in use. Stop other Flask instances."
    kill -TERM -- -$OLLAMA_PID 2>/dev/null
    exit 1
fi

# Verify Flask script exists
if [ ! -f "$FLASK_SCRIPT" ]; then
    echo "Error: $FLASK_SCRIPT not found in current directory."
    kill -TERM -- -$OLLAMA_PID 2>/dev/null
    exit 1
fi

# Start Flask app
echo "Starting Zoral Flask app..."
python3 "$FLASK_SCRIPT" >> "$FLASK_LOG" 2>&1 &
FLASK_PID=$!
sleep 2
if ! ps -p $FLASK_PID >/dev/null; then
    echo "Error: Flask failed to start. Check $FLASK_LOG:"
    tail -n 10 "$FLASK_LOG"
    kill -TERM -- -$OLLAMA_PID 2>/dev/null
    exit 1
fi
echo "Flask app started (PID: $FLASK_PID)."

# Wait for Flask to exit
wait $FLASK_PID
cleanup