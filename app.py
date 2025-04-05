import logging
import os
import sys

from dotenv import load_dotenv
from flask import Flask, render_template

# Configure logging (similar to app_socketio.py)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

def create_app():
    """Application factory function"""
    app = Flask("app_http")
    
    @app.route('/')
    def index():
        return render_template('index.html')
    
    return app

# This is used by Gunicorn
app = create_app()

if __name__ == '__main__':
    # This code only runs when you execute this file directly
    # It doesn't run when imported by Gunicorn
    logger.info("Starting Flask server.")
    # Get port from environment variable (for cloud deployment) or use default
    port = int(os.environ.get("PORT", 8000))
    # Run flask app - bind to 0.0.0.0 for cloud deployment
    app.run(host='0.0.0.0', debug=False, port=port)
