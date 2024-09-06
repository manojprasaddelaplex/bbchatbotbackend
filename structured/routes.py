from flask import Blueprint, jsonify, request, redirect
from .services.query_service import process_query, submit_feedback
from .utils.helpers import manage_conversation_length
from .services.openai_service import conversation_history
from swaggerData import main_swagger, feedback_swagger
from flasgger import swag_from

api_bp = Blueprint('api', __name__)

@api_bp.route("/")
def home():
    return redirect('/apidocs/')

@api_bp.route("/query", methods=["POST"])
@swag_from(main_swagger)
def query_db():
    user_query = request.json.get('query')
    global conversation_history
    conversation_history.append({"role": "user", "content": user_query})
    conversation_history = manage_conversation_length(conversation_history)
    
    return process_query(user_query, conversation_history)

@api_bp.route("/feedback", methods=["POST"])
@swag_from(feedback_swagger)
def feedback():
    data = request.get_json()
    res_id = data.get('resID')
    feedback = bool(data.get('feedback'))
    
    return submit_feedback(res_id, feedback)