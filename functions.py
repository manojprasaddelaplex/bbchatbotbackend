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

endpoint = os.getenv("ENDPOINT_URL")
deployment = os.getenv("DEPLOYMENT_NAME")
search_endpoint = os.getenv("SEARCH_ENDPOINT")
search_key = os.getenv("SEARCH_KEY")
search_index = os.getenv("SEARCH_INDEX_NAME")
cognitive_service = os.getenv("COGNITIVE_SERVICE")
api_version = os.getenv("API_VERSION")
asure_openai_api_key = os.environ.get("AZURE_OPENAI_API_KEY")


     
client = openai.AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=asure_openai_api_key,
    api_version=api_version,
)


#MongoDB Configurations
clientMongo = MongoClient(os.getenv('CONNECTION_STRING'))
DB = clientMongo['ChabotFeedback']
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
    


def azure_search_openai(conversation_history):
    completion = client.chat.completions.create(
        model=deployment,
        messages= conversation_history,
        max_tokens=3000,
        temperature=0.3,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
        stream=False,
        extra_body={
          "data_sources": [{
              "type": "azure_search",
              "parameters": {
                "endpoint": f"{search_endpoint}",
                "index_name": f"{search_index}",
                "semantic_configuration": "default",
                "query_type": "vector_semantic_hybrid",
                "in_scope": True,
                "role_information": "You are an AI assistant specialized in helping users with SQL queries. Your goal is to make only the necessary changes to the SQL query based on the user's question, without altering the overall structure of the query. Always provide the complete, modified SQL query in your response. Ensure your answers are concise and relevant to this purpose.",
                "filter": None,
                "strictness": 3,
                "top_n_documents": 5,
                "authentication": {
                    "type": "api_key",
                    "key": f"{search_key}"
                },
                "embedding_dependency": {
                    "type": "deployment_name",
                    "deployment_name": "text-embedding-ada-002-standard"
                }
              }
            }]
        }
    )
    return completion.choices[0].message.content


def readSqlDatabse(sql_query):
    with engine.connect() as connection:
        result = connection.execute(text(sql_query))
        rows = [dict(row._mapping) for row in result]
        headers = list(rows[0].keys()) if rows else []
    return headers, rows

def saveFeedback(resID,feedback,userQuestion):
    existing_correct = collection.find_one({
        "UserQuestion": userQuestion,
        "IsCorrect": feedback
    })

    if not existing_correct:
        collection.update_one(
            {"_id": ObjectId(resID)},
            {"$set": {
                "IsCorrect": feedback,
                "FeedbackDateTime": datetime.now().strftime('%d-%m-%Y %H:%M:%S')
            }}
        )


def findSqlQueryFromDB(userQuestion):
    result = collection.find_one(
        {"UserQuestion": userQuestion, "IsCorrect": True},
        sort=[("timestamp", 1)],  # Sort by timestamp in ascending order
        projection={"SqlQuery": 1}
    )
    return result['SqlQuery'] if result else None


def extractSqlQueryFromResponse(response):
    # First, try to extract content from code blocks
    code_block_pattern = r'```(?:sql)?\s*([\s\S]+?)\s*```'
    code_block_match = re.search(code_block_pattern, response, re.IGNORECASE)
    
    if code_block_match:
        sql_content = code_block_match.group(1)
    else:
        sql_content = response
    
    sql_pattern = r'(WITH|SELECT)[\s\S]+?;'
    sql_match = re.search(sql_pattern, sql_content, re.IGNORECASE | re.MULTILINE)
    
    if sql_match:
        return sql_match.group(0).strip()
    else:
        return None
    
def estimate_tokens(text):
    enc = tiktoken.get_encoding("cl100k_base")
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
    while total_tokens > 2000 and system_prompt_index is not None:
        if len(conversation) > system_prompt_index + 1:  # Ensure there are entries to pop after the system prompt
            conversation.pop(system_prompt_index + 1)  # Remove the oldest user-assistant exchange
            total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
        else:
            break  # Exit if there are no more entries to remove after the system prompt
    
    return conversation


def find_best_matching_user_questions(userQuestion):
    try:
        # Perform a text search to find the best matching UserQuestion
        results = list(collection.find(
            {
                "$text": {"$search": userQuestion},  # Use text search for matching
                "IsCorrect": True,
                "ExceptionMessage": None
            },
            sort=[("score", {"$meta": "textScore"}), ("createdAt", 1)],  # Sort by text score (highest first)
            projection={"UserQuestion": 1, "score": {"$meta": "textScore"}, "_id": 0}  # Project UserQuestion and score
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
    except Exception as e:
        return None

    
def find_best_matching_user_question_with_sql(userQuestion):
    try:
        # Perform a text search to find the best matching UserQuestion
        result = collection.find_one(
            {
                "$text": {"$search": userQuestion},  # Use text search for matching
                "IsCorrect": True,
                "ExceptionMessage": None
            },
            sort=[("score", {"$meta": "textScore"}), ("createdAt", 1)],  # Sort by text score (highest first)
            projection={"UserQuestion": 1, "SqlQuery": 1, "_id": 0}  # Project UserQuestion and SqlQuery
        )

        return result if result else None
    except Exception as e:
        return None