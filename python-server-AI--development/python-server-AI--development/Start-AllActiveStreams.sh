#!/bin/bash

# ============================================================
# Start All Active Drone Streams (Bash/Linux)
# This script fetches all drones with streamIsOn=true and starts a detector for each
# ============================================================

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Configuration ---
API_URL="${1:-http://127.0.0.1:5000/api/v1/drones}"
PYTHON_SCRIPT="${2:-$SCRIPT_DIR/rtsp_webrtc_detector.py}"
VENV_PATH="${3:-$SCRIPT_DIR/cuda-venv}"

# Define the terminal emulator command (Change 'gnome-terminal' to 'xterm', 'konsole', etc., if needed)
TERMINAL_CMD="gnome-terminal --title"

# --- Functions ---

# Function to echo messages with colors
color_echo() {
    local color=$1
    local text=$2
    case "$color" in
        "CYAN")      echo -e "\033[36m${text}\033[0m" ;;
        "GREEN")     echo -e "\033[32m${text}\033[0m" ;;
        "YELLOW")    echo -e "\033[33m${text}\033[0m" ;;
        "RED")       echo -e "\033[31m${text}\033[0m" ;;
        "WHITE")     echo -e "\033[37m${text}\033[0m" ;;
        "GRAY")      echo -e "\033[90m${text}\033[0m" ;;
        "MAGENTA")   echo -e "\033[35m${text}\033[0m" ;;
        *)           echo "${text}" ;;
    esac
}

# Function to extract IP/Port/Credentials (Simplified Bash regex is complex, so we parse components)
parse_rtsp_url() {
    local url=$1
    local part=$2 # 'credentials', 'ip', 'port', or 'display'
    
    # Check for rtsp:// credentials@host:port/path
    if [[ $url =~ rtsp://(.+)@(.+) ]]; then
        CREDS=${BASH_REMATCH[1]}
        HOST_PATH=${BASH_REMATCH[2]}
    else
        CREDS=""
        HOST_PATH=${url#rtsp://} # Remove rtsp://
    fi

    if [[ $HOST_PATH =~ ^([^/:]+)(:([^/]+))?(/.*)? ]]; then
        IP_PORT_PATH=${BASH_REMATCH[0]}
        HOST_PORT=${BASH_REMATCH[1]}
    fi

    # Extract IP and Port from HOST_PORT
    if [[ $HOST_PORT =~ ^(.+):([0-9]+)$ ]]; then
        IP=${BASH_REMATCH[1]}
        PORT=${BASH_REMATCH[2]}
    else
        IP=$HOST_PORT
        PORT="8554"
    fi

    case "$part" in
        "credentials") echo "$CREDS" ;;
        "ip")          echo "$IP" ;;
        "port")        echo "$PORT" ;;
        "display")
            if [[ -n "$CREDS" ]]; then
                # Mask password (crude, assumes format user:pass)
                DISPLAY_URL=$(echo "$url" | sed 's/\(:[^\/]*\)@/\:****@/')
                echo "$DISPLAY_URL"
            else
                echo "$url"
            fi
            ;;
        *) echo "" ;;
    esac
}

# --- Main Script Execution ---

color_echo "CYAN" "============================================================"
color_echo "CYAN" "Starting All Active Drone Streams"
color_echo "CYAN" "============================================================"
echo "API URL: $API_URL"
echo ""

# Determine Python executable and check venv
if [ -d "$VENV_PATH" ]; then
    color_echo "GREEN" "Virtual environment found: $VENV_PATH"
    # Check for python3 first, then python
    if [ -f "$VENV_PATH/bin/python3" ]; then
        PYTHON_EXE="$VENV_PATH/bin/python3"
    elif [ -f "$VENV_PATH/bin/python" ]; then
        PYTHON_EXE="$VENV_PATH/bin/python"
    else
        color_echo "RED" "Error: No Python executable found in venv"
        exit 1
    fi
else
    color_echo "YELLOW" "Warning: Virtual environment not found at $VENV_PATH"
    color_echo "YELLOW" "Will use system Python instead. Ensure dependencies are met!"
    PYTHON_EXE="python3"
fi

# Debug output
color_echo "GRAY" "Python executable: $PYTHON_EXE"
echo ""

# Fetch all drones
color_echo "YELLOW" "Fetching active drones..."
API_RESPONSE=$(curl -s "$API_URL")
CURL_STATUS=$?

if [ $CURL_STATUS -ne 0 ]; then
    color_echo "RED" "Error: Failed to fetch API URL ($API_URL). Curl status: $CURL_STATUS"
    color_echo "YELLOW" "Make sure the drone management API is running."
    exit 1
fi

# Filter active drones using jq
ACTIVE_DRONES=$(echo "$API_RESPONSE" | jq '.data.drones[] | select(.streamIsOn == true)')
DRONE_COUNT=$(echo "$ACTIVE_DRONES" | jq -s 'length')

if [ "$DRONE_COUNT" -eq 0 ]; then
    color_echo "YELLOW" "No active drones found (streamIsOn=true)"
    exit 0
fi

color_echo "GREEN" "Found $DRONE_COUNT active drone(s)"
echo ""

# Store process info for summary
STARTED_PROCESSES=()

# Process each drone one by one using jq stream
echo "$ACTIVE_DRONES" | jq -c '.' | while IFS=$'\n' read -r DRONE_JSON; do
    
    SERIAL=$(echo "$DRONE_JSON" | jq -r '.deviceSerialNumber')
    ALIAS=$(echo "$DRONE_JSON" | jq -r '.metadata.alias // empty')
    NAME=$( [ -n "$ALIAS" ] && echo "$ALIAS" || echo "$DRONE_JSON" | jq -r '.deviceName' )
    STREAM_URL=$(echo "$DRONE_JSON" | jq -r '.streamUrl // empty')
    
    # Determine RTSP URL
    if [ -n "$STREAM_URL" ] && [ "$STREAM_URL" != "null" ]; then
        RTSP_URL="$STREAM_URL"
    else
        # Fallback logic (less reliable, relies on credentials fields)
        USERNAME=$(echo "$DRONE_JSON" | jq -r '.streamCredentials.userName // empty')
        PASSWORD=$(echo "$DRONE_JSON" | jq -r '.streamCredentials.password // empty')
        PORT=$(echo "$DRONE_JSON" | jq -r '.streamCredentials.port // "8554"')
        IP="UNKNOWN" # No easy way to guess IP on Linux fallback

        if [ -n "$USERNAME" ] && [ -n "$PASSWORD" ]; then
            RTSP_URL="rtsp://${USERNAME}:${PASSWORD}@${IP}:${PORT}/streaming/live/1"
        else
            RTSP_URL="rtsp://${IP}:${PORT}/streaming/live/1"
        fi
    fi
    
    # Calculate WebRTC Port (Using Bash arithmetic, similar to hash modulo)
    # This is a simple hash approximation; might not exactly match the PS GetHashCode()
    HASH=$(echo "$SERIAL" | od -An -tx1 | tr -d ' \n') # Get hex representation
    DECIMAL_HASH=$((16#${HASH:0:8} % 1000)) # Use first 8 hex chars to avoid overflow
    AUTO_PORT=$((6000 + DECIMAL_HASH))

    DISPLAY_URL=$(parse_rtsp_url "$RTSP_URL" "display")
    RTSP_URL_SHORT=${DISPLAY_URL:0:70}
    
    color_echo "GRAY" "------------------------------------------------------------"
    color_echo "WHITE" "Drone: $NAME"
    color_echo "CYAN" "  Serial Number: $SERIAL"
    color_echo "YELLOW" "  RTSP URL: ${RTSP_URL_SHORT}..."
    color_echo "MAGENTA" "  WebRTC Port: $AUTO_PORT"
    color_echo "GRAY" "------------------------------------------------------------"

    # Start Python process in new terminal window with proper quoting
    # All paths and arguments are properly quoted to handle spaces
    $TERMINAL_CMD "Detector - $SERIAL ($NAME)" -- bash -c "\"$PYTHON_EXE\" \"$PYTHON_SCRIPT\" --drone-serial \"$SERIAL\" --api-url \"$API_URL\"; echo 'Detector finished. Press Enter to close.'; read;" &
    
    PID=$!
    color_echo "GREEN" "Started detector in new window (launcher PID: $PID)"
    echo ""

    # Small delay to avoid overwhelming the system
    sleep 2

done

color_echo "CYAN" "============================================================"
color_echo "GREEN" "Summary - Detector Launch Sequence Complete"
color_echo "CYAN" "============================================================"
echo
color_echo "YELLOW" "Note: Due to how Linux spawns terminal windows, PIDs of the child Python processes"
color_echo "YELLOW" "are not easily captured by this script's summary."
color_echo "YELLOW" "Please refer to the new terminal windows for detector output."
echo

color_echo "YELLOW" "Commands:"
color_echo "WHITE" "  Stop all detectors (by script name):"
color_echo "GRAY" "    pkill -f rtsp_webrtc_detector.py"
color_echo "WHITE" "  Monitor processes:"
color_echo "GRAY" "    ps aux | grep 'rtsp_webrtc_detector.py'"
echo
color_echo "CYAN" "============================================================"