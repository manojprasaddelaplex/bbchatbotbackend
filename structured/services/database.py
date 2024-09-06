from pymongo import MongoClient
from sqlalchemy import create_engine, text
from bson.objectid import ObjectId
import os
import urllib.parse
from models import QueryLog
from datetime import datetime

client = MongoClient(os.getenv('CONNECTION_STRING'))
DB = client['ChabotFeedback']
collection = DB['BBChatBotOnline']

conn_str = os.getenv('SQL_CONNECTION_STRING')
if isinstance(conn_str, bytes):
    conn_str = conn_str.decode('utf-8')
conn_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"
engine = create_engine(conn_url)

def insert_query_log(query_log: QueryLog):
    document = query_log.to_dict()
    inserted_doc = collection.insert_one(document=document)
    return inserted_doc.inserted_id

def read_sql_database(sql_query):
    with engine.connect() as connection:
        result = connection.execute(text(sql_query))
        rows = [dict(row._mapping) for row in result]
        headers = list(rows[0].keys()) if rows else []
    return headers, rows

def save_feedback(res_id, feedback):
    collection.update_one(
        {"_id": ObjectId(res_id)},
        {"$set": {
            "IsCorrect": feedback,
            "FeedbackDateTime": datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        }}
    )

def find_sql_query_from_db(user_question):
    result = collection.find_one(
        {"UserQuestion": user_question, "IsCorrect": True},
        sort=[("timestamp", 1)],
        projection={"SqlQuery": 1}
    )
    return result['SqlQuery'] if result else None

def find_best_matching_user_questions(user_question):
    try:
        results = list(collection.find(
            {
                "$text": {"$search": user_question},
                "IsCorrect": True,
                "ExceptionMessage": None
            },
            sort=[("score", {"$meta": "textScore"}), ("createdAt", 1)],
            projection={"UserQuestion": 1, "score": {"$meta": "textScore"}, "_id": 0}
        ).limit(10))

        seen_questions = set()
        unique_results = []

        for res in results:
            user_question = res['UserQuestion']
            if user_question not in seen_questions:
                seen_questions.add(user_question)
                unique_results.append(user_question)

        return unique_results[:3] if unique_results else None
    except Exception:
        return None