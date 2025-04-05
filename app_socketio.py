import logging
import os
import sys
from flask import Flask, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
    DeepgramClientOptions
)
import base64
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('socketio_app.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

app_socketio = Flask("app_socketio")
# Allow CORS from the main app and any production URLs
# Add socket.io config for better connection stability
socketio = SocketIO(
    app_socketio, 
    cors_allowed_origins=['http://127.0.0.1:8000', 'http://localhost:8000', 'https://*', 'http://*'],
    binary=True  # Important for binary audio data
)

API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Set up client configuration with better timeout handling
config = DeepgramClientOptions(
    verbose=logging.WARNING,  # Reduce back to WARNING from INFO
    options={
        "keepalive": "true",
        "keepalive_timeout": "30"  # 30 seconds timeout (default is 10)
    }
)

deepgram = DeepgramClient(API_KEY, config)

# Dictionary to store connections for each user session
user_connections = {}

def initialize_deepgram_connection(session_id):
    try:
        # Initialize Deepgram client and connection for a specific user
        logger.info(f"Initializing Deepgram connection for session {session_id}")
        dg_connection = deepgram.listen.websocket.v("1")
        
        def on_open(self, open, **kwargs):
            try:
                logger.info(f"Session {session_id}: Deepgram connection opened")
            except Exception as e:
                logger.error(f"Error in on_open handler: {e}")

        def on_message(self, result, **kwargs):
            try:
                transcript = result.channel.alternatives[0].transcript
                if len(transcript) > 0:
                    # Only log non-empty transcripts
                    logger.info(f"Session {session_id} transcript: {transcript}")
                    # Only emit to the specific client that sent the audio
                    socketio.emit('transcription_update', {'transcription': transcript}, room=session_id)
            except Exception as e:
                logger.error(f"Error in on_message handler: {e}", exc_info=True)

        def on_close(self, close, **kwargs):
            try:
                logger.info(f"Session {session_id}: Deepgram connection closed")
                # Clean up connection on close
                if session_id in user_connections:
                    user_connections.pop(session_id, None)
            except Exception as e:
                logger.error(f"Error in on_close handler: {e}")

        def on_error(self, error, **kwargs):
            try:
                logger.error(f"Session {session_id} error: {error}")
            except Exception as e:
                logger.error(f"Error in on_error handler: {e}")
                
        def on_metadata(self, metadata, **kwargs):
            try:
                # Only log important metadata
                logger.debug(f"Session {session_id} metadata received")
            except Exception as e:
                logger.error(f"Error in on_metadata handler: {e}")

        # Register all event handlers
        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)
        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)

        # Define the options for the live transcription
        options = LiveOptions(
            model="nova-3", 
            language="en-US",
            interim_results=False,  # Get results as they come
            punctuate=True        # Add punctuation
        )

        if dg_connection.start(options) is False:
            logger.error(f"Session {session_id}: Failed to start connection")
            return None
        
        logger.info(f"Session {session_id}: Deepgram connection started successfully")
        return dg_connection
    except Exception as e:
        logger.error(f"Error initializing Deepgram connection for session {session_id}: {e}", exc_info=True)
        return None

@socketio.on('audio_stream')
def handle_audio_stream(data):
    try:
        session_id = request.sid
        
        # Check if this session has an active connection first
        if session_id not in user_connections or not user_connections[session_id]:
            # Only log once per session to avoid log spam
            if not hasattr(handle_audio_stream, f"warned_{session_id}"):
                logger.warning(f"Session {session_id}: Received audio but no active connection exists")
                setattr(handle_audio_stream, f"warned_{session_id}", True)
                # Notify client they need to restart
                socketio.emit('connection_lost', {'message': 'No active Deepgram connection'}, room=session_id)
            return
        
        # Skip detailed logging of each audio packet
        # Only log occasional packets (once every 20 packets) to reduce noise
        if random.randint(1, 20) == 1:
            data_size = len(data) if data else 'unknown'
            logger.debug(f"Audio data from session {session_id}: {data_size} bytes")
        
        # Check if data needs to be converted from string/base64 to binary
        if isinstance(data, str):
            logger.info(f"Converting string data to binary for session {session_id}")
            try:
                # Assuming base64 encoding if it's a string
                binary_data = base64.b64decode(data)
            except Exception as e:
                logger.error(f"Error converting string to binary: {e}")
                return
        else:
            binary_data = data
        
        # Send the audio data to Deepgram API 
        user_connections[session_id].send(binary_data)
        
    except Exception as e:
        logger.error(f"Error handling audio stream: {e}", exc_info=True)

@socketio.on('toggle_transcription')
def handle_toggle_transcription(data):
    try:
        session_id = request.sid
        logger.info(f"Session {session_id}: toggle_transcription {data}")
        action = data.get("action")
        
        if action == "start":
            logger.info(f"Session {session_id}: Starting Deepgram connection")
            
            # First ensure any existing connection is closed
            if session_id in user_connections:
                if user_connections[session_id]:
                    try:
                        logger.info(f"Session {session_id}: Closing existing connection before starting new one")
                        user_connections[session_id].finish()
                    except Exception as e:
                        logger.error(f"Error closing existing connection: {e}")
                user_connections.pop(session_id, None)
            
            # Create a new connection for this user
            conn = initialize_deepgram_connection(session_id)
            if conn:
                user_connections[session_id] = conn
                logger.info(f"Session {session_id}: Deepgram connection initialized successfully")
                # Notify client that connection is ready
                socketio.emit('deepgram_ready', {'status': 'connected'}, room=session_id)
            else:
                logger.error(f"Session {session_id}: Failed to initialize Deepgram connection")
                socketio.emit('connection_error', {'message': 'Failed to connect to Deepgram'}, room=session_id)
        
        elif action == "stop":
            logger.info(f"Session {session_id}: Stopping Deepgram connection")
            # Properly close the connection
            if session_id in user_connections:
                if user_connections[session_id]:
                    try:
                        logger.info(f"Session {session_id}: Sending finish signal to Deepgram")
                        user_connections[session_id].finish()
                        logger.info(f"Session {session_id}: Deepgram connection closed successfully")
                        # Notify client about successful stop
                        socketio.emit('deepgram_stopped', {'status': 'stopped'}, room=session_id)
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")
                        # Still notify client even if there was an error
                        socketio.emit('deepgram_stopped', {'status': 'error', 'message': str(e)}, room=session_id)
                
                # Always remove from connections dictionary
                logger.info(f"Session {session_id}: Removing from active connections")
                user_connections.pop(session_id, None)
            else:
                logger.warning(f"Session {session_id}: No active connection to stop")
                socketio.emit('deepgram_stopped', {'status': 'no_connection'}, room=session_id)
    except Exception as e:
        logger.error(f"Error handling toggle_transcription: {e}")

@socketio.on('connect')
def server_connect():
    try:
        session_id = request.sid
        logger.info(f'Client connected: {session_id}')
        # Send welcome message to confirm connection
        socketio.emit('server_status', {'status': 'connected'}, room=session_id)
    except Exception as e:
        logger.error(f"Error handling connect: {e}")

@socketio.on('disconnect')
def server_disconnect():
    try:
        session_id = request.sid
        logger.info(f'Client disconnected: {session_id}')
        # Clean up the connection when user disconnects
        if session_id in user_connections:
            if user_connections[session_id]:
                try:
                    user_connections[session_id].finish()
                    logger.info(f"Session {session_id}: Deepgram connection closed successfully")
                except Exception as e:
                    logger.error(f"Error closing connection during disconnect: {e}")
            user_connections.pop(session_id, None)  # Safely remove without KeyError
    except Exception as e:
        logger.error(f"Error handling disconnect: {e}")

if __name__ == '__main__':
    try:
        logging.info("Starting SocketIO server.")
        # Get port from environment variable (for cloud deployment) or use default
        port = int(os.environ.get("PORT", 5001))
        # Run socketio app - bind to 0.0.0.0 for cloud deployment
        socketio.run(
            app_socketio, 
            host='0.0.0.0', 
            debug=False, 
            allow_unsafe_werkzeug=True, 
            port=port
        )
    except Exception as e:
        logging.error(f"Error starting SocketIO server: {e}")
        # Attempt to restart the server
        try:
            logging.info("Attempting to restart SocketIO server...")
            socketio.run(app_socketio, host='0.0.0.0', debug=False, allow_unsafe_werkzeug=True, port=5001)
        except Exception as restart_error:
            logging.error(f"Failed to restart SocketIO server: {restart_error}")
