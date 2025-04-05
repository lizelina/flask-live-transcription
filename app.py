import logging
import os

from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

app = Flask("app_http")


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    logging.info("Starting Flask server.")
    # Get port from environment variable (for cloud deployment) or use default
    port = int(os.environ.get("PORT", 8000))
    # Run flask app - bind to 0.0.0.0 for cloud deployment
    app.run(host='0.0.0.0', debug=False, port=port)
