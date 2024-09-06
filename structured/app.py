from flask import Flask
from flask_cors import CORS
from flasgger import Swagger
from routes import api_bp

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    Swagger(app)
    
    app.register_blueprint(api_bp)
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)