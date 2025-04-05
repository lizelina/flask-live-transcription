#!/bin/bash

# Start the main web app using Gunicorn
gunicorn --worker-class eventlet -w 1 wsgi:app --bind 0.0.0.0:8000 &
MAIN_PID=$!

# Start the socket.io server using Gunicorn
gunicorn --worker-class eventlet -w 1 app_socketio:app_socketio --bind 0.0.0.0:5001 &
SOCKET_PID=$!

echo "Flask application running on http://localhost:8000"
echo "Socket.IO server running on http://localhost:5001"
echo "Press Ctrl+C to stop both servers"

# Wait for user to press Ctrl+C
wait $MAIN_PID
wait $SOCKET_PID 