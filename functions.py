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
import spacy
from collections import defaultdict


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
Schema_Collection = DB['DataBaseSchema']

#SQL Server Configurations
conn_str = os.getenv('SQL_CONNECTION_STRING')

if isinstance(conn_str, bytes):
    conn_str = conn_str.decode('utf-8')  # Convert bytes to string

# conn_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"
# engine = create_engine(conn_url)
# Replace with your actual connection details
server = "SHREYASH\\SQLEXPRESS"  # Your SQL Server name
database = 'DataPortal'  # Your database name
username = 'sa'  # Your SQL Server username
password = 'root'  # Your SQL Server password

# Create the connection string
connection_string = f'mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server'

# Create the engine
engine = create_engine(connection_string)

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
    # Extract token usage information
    prompt_tokens = response['usage']['prompt_tokens']
    completion_tokens = response['usage']['completion_tokens']
    total_tokens = response['usage']['total_tokens']
    
    # Print token usage information
    print(f"\nPrompt tokens: {prompt_tokens}")
    print(f"Response tokens: {completion_tokens}")
    print(f"Total tokens: {total_tokens}\n")
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
    enc = tiktoken.get_encoding("cl100k_base")
    enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(enc.encode(text))


def manageConversationLength(conversation):
    """Ensure the conversation length stays within token limits and fixed number of entries."""
    # Calculate total tokens
    total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
    print(total_tokens)
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
    

def get_db_metadata(collection):
    metadata = {}
    for doc in collection.find():
        table_name = doc['TableName']
        metadata[table_name] = {
            'columns': doc['columns'],
            'relations': doc.get('relations', {}),
            'description': f"Table containing information about {table_name.replace('_', ' ')}."
        }
    return metadata


def analyze_question(question, db_metadata):
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(question.lower())
    
    # Extract important words (nouns, verbs, adjectives)
    important_words = [token.lemma_ for token in doc if token.pos_ in ['NOUN', 'VERB', 'ADJ']]
    
    # Calculate relevance scores
    scores = defaultdict(float)
    for table, info in db_metadata.items():
        table_doc = nlp(table.lower() + ' ' + info['description'].lower())
        for word in important_words:
            if word in table_doc.text:
                scores[table] += 1
        
        for column in info['columns']:
            column_doc = nlp(column.lower())
            for word in important_words:
                if word in column_doc.text:
                    scores[table] += 0.5

    # Normalize scores
    max_score = max(scores.values()) if scores else 1
    normalized_scores = {table: score / max_score for table, score in scores.items()}
    
    # Filter tables with a relevance score above a threshold
    threshold = 0.3  # Adjust this value to control precision
    relevant_tables = [table for table, score in normalized_scores.items() if score > threshold]
    
    return relevant_tables


def get_relevant_schemas(question, collection=Schema_Collection):
    db_metadata = get_db_metadata(collection)
    relevant_tables = analyze_question(question, db_metadata)
    relevant_schemas = {table: {
            'columns': db_metadata[table]['columns'], 
            'relations': db_metadata[table]['relations']
        }
        for table in relevant_tables}
    
    # Join all the data into a single string
    data = "\n".join([f"TableName: {table}\nColumns: {schema['columns']}\nRelations(SecondaryTable : ForeignKey): {schema['relations']}\n" 
                      for table, schema in relevant_schemas.items()])
    return data


def get_system_prompt(schema):
    return {
        "role": "system",
        "content": f'''
        You are Sonar Chatbot, an expert at converting natural language into SQL queries for SQL Server.
        Only use this schema:
        {schema}
        End all SQL queries with a semicolon. You are strictly prohibited from performing data modification tasks; only fetch data.
        For non-SQL-related questions, keep your responses brief and relevant to your purpose.
        '''
    }