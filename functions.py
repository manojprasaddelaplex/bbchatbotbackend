from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
from sqlalchemy import create_engine, text
import openai
import os
import re
import urllib.parse
import tiktoken

load_dotenv(".env")

# OpenAI API configuration
openai.api_key = os.getenv('OPENAI_API_KEY')
openai.api_base = os.getenv('OPENAI_API_BASE')
openai.api_type = os.getenv('OPENAI_API_TYPE')
openai.api_version = os.getenv('OPENAI_API_VERSION')

#MongoDB Configurations
client = MongoClient(os.getenv('CONNECTION_STRING'))
DB = client['ChabotFeedback']
collection = DB['BBChatBotOnline']

#SQL Server Configurations
conn_str = os.getenv('SQL_CONNECTION_STRING')

if isinstance(conn_str, bytes):
    conn_str = conn_str.decode('utf-8')  # Convert bytes to string

conn_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"
engine = create_engine(conn_url)

def insertQueryLog(userQuestion, sqlQuery=None, Response=None, exceptionMessage=None, 
                     isDataFetchedFromDB=False, isCorrect=None, feedbackDateTime=None):
    
    document = {
        "UserQuestion":userQuestion,
        "SqlQuery": sqlQuery,
        "Response":Response,
        "ExceptionMessage":exceptionMessage,
        "IsDataFetchedFromDB":isDataFetchedFromDB,
        "IsCorrect":isCorrect,
        "CreatedDateTime": datetime.now().strftime('%d-%m-%Y %H:%M:%S'),
        "FeedbackDateTime":feedbackDateTime
    }
    
    insertDocument = collection.insert_one(document=document)
    return insertDocument.inserted_id


def generateSqlQuery(conversation_history):
    response = openai.ChatCompletion.create(
            deployment_id=os.getenv('DEPLOYMENT_ID'),
            messages=conversation_history,
            max_tokens=3000
        )
    
    return response.choices[0].message['content'].strip()


def readSqlDatabse(sql_query):
    with engine.connect() as connection:
        result = connection.execute(text(sql_query))
        rows = [dict(row._mapping) for row in result]
        headers = list(rows[0].keys()) if rows else []
    return headers, rows

def saveFeedback(resID,feedback):
    collection.update_one(
            {"_id": ObjectId(resID)},
            {"$set": {
                "IsCorrect": feedback,
                "FeedbackDateTime": datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                }
            }
        )


def findSqlQueryFromDB(userQuestion):
    result = collection.find_one(
        {"UserQuestion": userQuestion, "IsCorrect": True},
        sort=[("timestamp", 1)],  # Sort by timestamp in ascending order
        projection={"SqlQuery": 1}
    )
    return result['SqlQuery'] if result else None

def extractSqlQueryFromResponse(response):
    sql_pattern = r'(WITH|SELECT)[\s\S]+?;'
    matches = re.search(sql_pattern, response, re.IGNORECASE)
    if matches:
        return matches.group(0).strip()
    else:
        return None
    
def estimate_tokens(text):
    enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(enc.encode(text))


def manage_conversation_length(conversation):
    """Ensure the conversation length stays within token limits and fixed number of entries."""
    # Calculate total tokens
    total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
    # System prompt should always be preserved
    system_prompt_index = next((i for i, entry in enumerate(conversation) if entry["role"] == "system"), None)
    
    # Check if we need to pop entries to fit within the 7-entry limit
    if len(conversation) > 7:
        # Remove oldest entries until we have only 7
        conversation = [conversation[0]] + conversation[-6:]  # Keep system prompt and last 6 entries
    
    # Ensure tokens stay within limit while preserving system prompt
    while total_tokens > 1050 and system_prompt_index is not None:
        if len(conversation) > system_prompt_index + 1:  # Ensure there are entries to pop after the system prompt
            conversation.pop(system_prompt_index + 1)  # Remove the oldest user-assistant exchange
            total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
        else:
            break  # Exit if there are no more entries to remove after the system prompt
    
    return conversation


def find_best_matching_user_questions(userQuestion):
    # Perform a text search to find the best matching UserQuestion
    results = list(collection.find(
        {
            "$text": {"$search": userQuestion},  # Use text search for matching
            "IsCorrect": True,
            "ExceptionMessage": None
        },
        sort=[("createdAt", 1), ("score", {"$meta": "textScore"})],  # Sort by text score (highest first)
        projection={"score": {"$meta": "textScore"}, "UserQuestion": 1}  # Project UserQuestion and score
    ).limit(10))  # Limit to top 5 results

    # Use a set to track unique questions
    seen_questions = set()
    unique_results = []

    for res in results:
        user_question = res['UserQuestion']
        if user_question not in seen_questions:
            seen_questions.add(user_question)
            unique_results.append(user_question)
    
    return unique_results[:3] if unique_results else None