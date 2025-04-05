@echo off
echo Starting Flask application in production mode...

start cmd /k "gunicorn --worker-class eventlet -w 1 wsgi:app --bind 0.0.0.0:8000"
start cmd /k "gunicorn --worker-class eventlet -w 1 app_socketio:app_socketio --bind 0.0.0.0:5001"

echo Flask application running on http://localhost:8000
echo Socket.IO server running on http://localhost:5001
echo Two command windows have been opened. Close them to stop the servers. 