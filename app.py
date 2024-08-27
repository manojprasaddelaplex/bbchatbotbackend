import openai
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from flasgger import Swagger, swag_from
from functions import insertQueryLog, generateSqlQuery, readSqlDatabse, saveFeedback
from swaggerData import main_swagger, feedback_swagger


app = Flask(__name__)
CORS(app)
swagger = Swagger(app)


@app.route("/")
def home():
    return redirect('/apidocs/')

conversation_history = [
    {
        "role": "system", 
        "content": "You are an expert assistant that converts natural language to correct SQL queries for SQL SERVER."
    }
    ]

@app.route("/query", methods=["POST"])
@swag_from(main_swagger)
def query_db():
    user_query = request.json.get('query')
    user_query_lower = user_query.lower()
    
    global conversation_history
    conversation_history.append({"role": "user", "content": user_query})
        
    try:
        sql_query = generateSqlQuery(conversation_history)
        conversation_history.append({"role": "assistant", "content": sql_query})
        
        if len(conversation_history) > 11:
            conversation_history = [conversation_history[0]] + conversation_history[-10:]
            
        #return text      
        if not any(term in sql_query for term in ['SELECT', 'WITH']):
            results = {"text":sql_query}
            id = insertQueryLog(userQuestion=user_query,Response=sql_query)
            return jsonify({"results":results, "id":str(id)}),200
        
        else:
            headers, rows = readSqlDatabse(sql_query)

            #returns data for chart and graph
            if any(word in user_query_lower for word in ('chart', 'graph')):
                chartType = 'doughnut' if 'chart' in user_query_lower else 'bar'
                results = {
                        "labels": [str(row[headers[0]]) for row in rows],
                        "data": [str(row[headers[1]]) for row in rows],
                        "type" : chartType,
                    }

                id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
                return jsonify({"results":results, "id":str(id)}),200
            
            #returns data for table
            formatted_rows = [[str(row[header]) for header in headers] for row in rows]
            results = {
                    "headers": headers,
                    "rows": formatted_rows,
                }
            id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
            return jsonify({"results":results, "id":str(id)}),200
    
    except openai.error.OpenAIError as e:
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"OpenAI API error: {str(e)}", "id":str(id)}), 500
    except Exception as e:
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"Database query error: {str(e)}", "id":str(id)}), 500
    
    

@app.route("/feedback", methods=["POST"])
@swag_from(feedback_swagger)
def submit_feedback():
    data = request.get_json()
    resID = data.get('resID')
    feedback = bool(data.get('feedback'))
    try:
        saveFeedback(resID,feedback)
        return jsonify({"message": "Feedback submitted successfully!"}), 200 
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)