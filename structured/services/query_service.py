import re
from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError
import openai
from database import insert_query_log, read_sql_database, save_feedback, find_sql_query_from_db, find_best_matching_user_questions
from openai_service import generate_sql_query
from utils.helpers import extract_sql_query_from_response
from models import QueryLog

def process_query(user_query, conversation_history):
    user_query_lower = user_query.lower()
    
    try:
        sql_query = find_sql_query_from_db(user_query)
        if sql_query is None:
            response = generate_sql_query(conversation_history)
            sql_query = extract_sql_query_from_response(response)
            
            conversation_history.append({"role": "assistant", "content": response if sql_query is None else sql_query})
            
            if sql_query is None:
                results = {"text": response}
                query_log = QueryLog(user_question=user_query, response=results)
                id = insert_query_log(query_log)
                return jsonify({"results": results, "id": str(id)}), 200
                
        conversation_history.append({"role": "assistant", "content": sql_query})
        headers, rows = read_sql_database(sql_query)
        
        if not headers and not rows:
            results = {"text": "Unfortunately, I found 0 records matching your search. Please try asking a different question or adjust your search criteria."}
            query_log = QueryLog(user_question=user_query, sql_query=sql_query, response=results)
            id = insert_query_log(query_log)
            return jsonify({"results": results, "id": str(id), "sql_query": str(sql_query)}), 200
        
        if re.search(r'\b(chart|graph)\b', user_query_lower):
            chart_type = 'doughnut' if 'chart' in user_query_lower else 'bar'
            results = {
                "labels": [str(row[headers[0]]) for row in rows],
                "data": [str(row[headers[1]]) for row in rows],
                "type": chart_type,
            }
        else:
            formatted_rows = [[str(row[header]) for header in headers] for row in rows]
            results = {
                "headers": headers,
                "rows": formatted_rows,
            }
        
        query_log = QueryLog(user_question=user_query, sql_query=sql_query, response=results, is_data_fetched_from_db=True)
        id = insert_query_log(query_log)
        return jsonify({"results": results, "id": str(id), "sql_query": str(sql_query)}), 200
    
    except openai.error.OpenAIError as e:
        query_log = QueryLog(user_question=user_query, sql_query=sql_query, exception_message=str(e))
        id = insert_query_log(query_log)
        return jsonify({"error": f"OpenAI Model Error: {str(e)}", "id": str(id), "sql_query": str(sql_query)}), 500
    except SQLAlchemyError as e:
        base_err = "I apologize for the confusion. It seems I misunderstood your question, leading to a response that is not related to the database tables and columns I have access to. "
        similar_questions = find_best_matching_user_questions(user_query)
    
        err = base_err + ("Here are some similar questions that might be helpful for you. " if similar_questions else "") + "Is there anything else I can assist you with?"
        query_log = QueryLog(user_question=user_query, sql_query=sql_query, exception_message=str(e))
        id = insert_query_log(query_log)
        
        results = {
            "error": err,
            "similar_questions": similar_questions,
            "id": str(id),
            "sql_query": str(sql_query)
        }
        
        return jsonify(results), 500
    except Exception as e:
        query_log = QueryLog(user_question=user_query, sql_query=sql_query, exception_message=str(e))
        id = insert_query_log(query_log)
        return jsonify({"error": "I apologize for the inconvenience. It seems there was an error in the response. Please try some other questions.", "id": str(id), "sql_query": str(sql_query)}), 500

def submit_feedback(res_id, feedback):
    try:
        save_feedback(res_id, feedback)
        return jsonify({"message": "Feedback submitted successfully!"}), 200 
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500