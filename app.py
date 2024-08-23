import openai
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, text
import pandas as pd
from flasgger import Swagger, swag_from
import csv
import os
import json
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing if needed
swagger = Swagger(app)

# OpenAI API configuration
openai.api_key = "34a6fe8ffcfa4b92ab4b6db1b959356d"
openai.api_base = "https://blueberrysonar-open-ai.openai.azure.com/"
openai.api_type = 'azure'
openai.api_version = '2024-05-01-preview'
deployment_id = "delaplexmodeldeploy"
#deployment_id = "NNCPModel"

# Database For Storing QueryLog
client = MongoClient("mongodb+srv://adminuser:adminuser@chatbotfeedbackcluster.4eg40h5.mongodb.net/?retryWrites=true&w=majority&appName=ChatBotFeedbackCluster")
DB = client['ChabotFeedback']
collection = DB['QueryLogs1']


def insert_query_log(userQuestion, sqlQuery=None, Response=None, exceptionMessage=None, 
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


server = "DPLAP156\\SQLEXPRESS"  # Your SQL Server name
database = 'custody-portal'  # Your database name
username = 'sa'  # Your SQL Server username
password = 'Delaplex#1234'  # Your SQL Server password

connection_string = f'mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server'
engine = create_engine(connection_string)

@app.route("/", methods=["GET"])
def home():
    return '''
    <html>
        <head>
            <style>
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                h1 {
                    font-family: Arial, sans-serif;
                    color: #333;
                }
            </style>
        </head>
        <body>
            <h1>Server is running</h1>
        </body>
    </html>
    '''

conversation_history = [
    {
        "role": "system", 
        "content": "You are an assistant that converts natural language to SQL queries for SQL SERVER. give me SQL query only if user_query contains chart, table, or graph in it, else give a normal answer). Use 'HcpPatients' as the table name (do not use the LIMIT clause, use its SQL Server alternative)."
    },
    {
        "role": "system", 
        "content": "If asked about your purpose or similar question, state that you assist in providing data in various formats (charts, graphs, tables, or text) for easy and accessible understanding. and your name will be 'Sonar Chatbot'"
    }
    ]

def tableDataGeneration(headers, rows):
    formatted_rows = [[str(row[header]) for header in headers] for row in rows]
    results = {
            "headers": headers,
            "rows": formatted_rows,
            }
    
    return results

@app.route("/query", methods=["POST"])
@swag_from({
    'summary': 'Process user query to generate SQL and retrieve results.',
    'description': 'This endpoint processes the user query to generate an SQL statement using OpenAI, executes it against the database, and returns results in various formats such as text, table, chart, or graph.',
    'parameters': [
        {
            'name': 'query',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'The user query to be processed into an SQL query and then fetching data from database.',
                        'default': 'user_question'  # Set default value here
                    }
                },
                'example': {
                    'query': 'user_question'  # This sets the default example in Swagger UI
                }
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Successful response with query results',
            'examples': {
                'application/json': {
                    "results": {
                        "text": "SELECT * FROM HcpPatients"
                    }
                }
            }
        },
        500: {
            'description': 'Internal Server Error',
            'examples': {
                'application/json': {
                    "error": "OpenAI API error: ..."
                }
            }
        }
    }
})
def query_db():
    user_query = request.json.get('query')
    user_query_lower = user_query.lower()
    
    global conversation_history
    conversation_history.append({"role": "user", "content": f"user_query: {user_query}"})
        
    try:
        # Use OpenAI Chat API to convert user query to SQL query    
        response = openai.ChatCompletion.create(
            deployment_id=deployment_id,
            messages=conversation_history
            ,max_tokens=150
        )
        sql_query = response.choices[0].message['content'].strip()
        conversation_history.append({"role": "assistant", "content": sql_query})
        
        if len(conversation_history) > 15:
            conversation_history = conversation_history[-15:]
            
            
        if not any(term in sql_query for term in ['SELECT', 'WITH']):
            results = {"text":sql_query}
            id = insert_query_log(userQuestion=user_query,Response=sql_query)
            return jsonify({"results":results, "id":str(id)}),200
        
        else:
            with engine.connect() as connection:
                result = connection.execute(text(sql_query))
                rows = [dict(row._mapping) for row in result]
                headers = list(rows[0].keys()) if rows else []

            if any(word in user_query_lower for word in ('chart', 'graph')):
                chartType = 'doughnut' if 'chart' in user_query_lower else 'bar'
                results = {
                        "labels": [str(row[headers[0]]) for row in rows],
                        "data": [str(row[headers[1]]) for row in rows],
                        "type" : chartType,
                    }

                id = insert_query_log(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
                return jsonify({"results":results, "id":str(id)}),200
            

            formatted_rows = [[str(row[header]) for header in headers] for row in rows]
            results = {
                    "headers": headers,
                    "rows": formatted_rows,
                }
            id = insert_query_log(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
            return jsonify({"results":results, "id":str(id)}),200
    
    except openai.error.OpenAIError as e:
        id = insert_query_log(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"OpenAI API error: {str(e)}", "id":str(id)}), 500
    except Exception as e:
        id = insert_query_log(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"Database query error: {str(e)}", "id":str(id)}), 500
    
    

@app.route("/feedback", methods=["POST"])
def submit_feedback():
    data = request.get_json()
    resID = data.get('resID')
    feedback = bool(data.get('feedback'))
    try:
        collection.update_one(
            {"_id": ObjectId(resID)},
            {"$set": {
                "IsCorrect": feedback,
                "FeedbackDateTime": datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                }
            }
        )
        return jsonify({"message": "Feedback submitted successfully!"}), 200 
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500



# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)
