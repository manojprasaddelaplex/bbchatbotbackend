import openai
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from flasgger import Swagger, swag_from
from functions import insertQueryLog, generateSqlQuery, readSqlDatabse, saveFeedback, findSqlQueryFromDB, extractSqlQueryFromResponse, manage_conversation_length, find_best_matching_user_questions,managing_payload,gpt_4_model
from swaggerData import main_swagger, feedback_swagger
from sqlalchemy.exc import SQLAlchemyError
import re

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
swagger = Swagger(app)


@app.route("/")
def home():
    return redirect('/apidocs/')

conversation_history = [
    {
      "role": "system",
      "content": [
        {
          "type": "text",
          "text": "You are an AI assistant that helps people find correct SQL Query. give only sql query and alway end query with semicolon"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "From Friday to 0600hrs on Monday can you provide me with the number of referrals in the force area per day"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "WITH WeekendData AS (\n    SELECT \n        -- Identify each weekend by its Friday date\n        DATEADD(DAY, -((DATEPART(WEEKDAY, ReferralCreatedDateTime) + 1) % 7), CAST(ReferralCreatedDateTime AS DATE)) AS WeekendStart,\n        COUNT(*) AS ReferralCount\n    FROM Referrals\n    WHERE ReferralCreatedDateTime >= DATEADD(MONTH, -1, GETDATE()) -- Only look at the past 1 month\n      AND (\n            -- Capture Fridays through Mondays at 6 AM\n            DATEPART(WEEKDAY, ReferralCreatedDateTime) = 6 -- Friday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 7) -- Saturday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 1) -- Sunday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 2 AND DATEPART(HOUR, ReferralCreatedDateTime) < 6) -- Monday before 6 AM\n          )\n    GROUP BY \n        DATEADD(DAY, -((DATEPART(WEEKDAY, ReferralCreatedDateTime) + 1) % 7), CAST(ReferralCreatedDateTime AS DATE))\n)\n-- Calculate this weekend's referrals\n, ThisWeekend AS (\n    SELECT \n        DATEADD(DAY, -((DATEPART(WEEKDAY, GETDATE()) + 1) % 7), CAST(GETDATE() AS DATE)) AS ThisWeekendStart, \n        COUNT(*) AS TotalThisWeekendReferrals\n    FROM Referrals\n    WHERE ReferralCreatedDateTime >= DATEADD(DAY, -((DATEPART(WEEKDAY, GETDATE()) + 1) % 7), CAST(GETDATE() AS DATE)) -- Start at this Friday\n      AND ReferralCreatedDateTime < DATEADD(DAY, 3, DATEADD(DAY, -((DATEPART(WEEKDAY, GETDATE()) + 1) % 7), CAST(GETDATE() AS DATE))) -- End at Monday 23:59\n      AND (\n            DATEPART(WEEKDAY, ReferralCreatedDateTime) = 6 -- Friday\n            OR DATEPART(WEEKDAY, ReferralCreatedDateTime) = 7 -- Saturday\n            OR DATEPART(WEEKDAY, ReferralCreatedDateTime) = 1 -- Sunday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 2 AND DATEPART(HOUR, ReferralCreatedDateTime) < 6) -- Monday before 6 AM\n          )\n)\n-- Calculate the average referrals for the previous weekends\n, PreviousWeekends AS (\n    SELECT \n        AVG(ReferralCount) AS AvgPreviousWeekendReferrals,\n        SUM(ReferralCount) AS TotalPreviousWeekendReferrals\n    FROM WeekendData\n    WHERE WeekendStart < (SELECT ThisWeekendStart FROM ThisWeekend)\n)\n\n-- Combine and compare the results\nSELECT \n    ThisWeekend.TotalThisWeekendReferrals,\n    PreviousWeekends.AvgPreviousWeekendReferrals,\n    PreviousWeekends.TotalPreviousWeekendReferrals,\n    CASE \n        WHEN ThisWeekend.TotalThisWeekendReferrals > PreviousWeekends.AvgPreviousWeekendReferrals \n            THEN 'Above Average'\n        WHEN ThisWeekend.TotalThisWeekendReferrals < PreviousWeekends.AvgPreviousWeekendReferrals \n            THEN 'Below Average'\n        ELSE 'Equal to Average'\n    END AS ComparisonResult\nFROM \n    ThisWeekend,\n    PreviousWeekends;"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "then per hour please"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "WITH HourlyReferrals AS (\n  SELECT \n    CONVERT(DATE, ReferralCreatedDateTime) AS ReferralDate,\n    DATEPART(HOUR, ReferralCreatedDateTime) AS ReferralHour,\n    COUNT(*) AS NumberOfReferrals\n  FROM Referrals \n  WHERE \n    ReferralCreatedDateTime >= '2023-10-01' AND\n    ReferralCreatedDateTime < '2023-10-06'\n  GROUP BY CONVERT(DATE, ReferralCreatedDateTime), DATEPART(HOUR, ReferralCreatedDateTime)\n)\nSELECT\n  ReferralDate,\n  ReferralHour,\n  NumberOfReferrals\nFROM HourlyReferrals\nORDER BY ReferralDate, ReferralHour;"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "From the data you have how does that compare to other force areas"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "WITH DailyReferrals AS (\n  SELECT \n    CONVERT(DATE, r.ReferralCreatedDateTime) AS ReferralDate,\n    COUNT(*) AS NumberOfReferrals,\n    p.Name AS PoliceForceName,\n    pl.Name AS PoliceForceLocationName\n  FROM Referrals r\n  JOIN PoliceForceLocations pl ON r.Id = pl.Id\n  JOIN PoliceForces p ON pl.PoliceForceId = p.Id\n  WHERE \n    r.ReferralCreatedDateTime >= '2023-10-01' AND\n    r.ReferralCreatedDateTime < '2023-10-06'\n  GROUP BY \n    CONVERT(DATE, r.ReferralCreatedDateTime),\n    p.Name,\n    pl.Name\n)\nSELECT\n  ReferralDate,\n  NumberOfReferrals,\n  PoliceForceName,\n  PoliceForceLocationName\nFROM DailyReferrals\nORDER BY ReferralDate;"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Can you compare this weekend referral numbers to the previous 11 months of data please"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "WITH WeekendData AS (\n    SELECT \n        -- Identify each weekend by its Friday date\n        DATEADD(DAY, -((DATEPART(WEEKDAY, ReferralCreatedDateTime) + 1) % 7), CAST(ReferralCreatedDateTime AS DATE)) AS WeekendStart,\n        COUNT(*) AS ReferralCount\n    FROM Referrals\n    WHERE ReferralCreatedDateTime >= DATEADD(MONTH, -11, GETDATE()) -- Only look at the past 2 months\n      AND (\n            -- Capture Fridays through Mondays at 6 AM\n            DATEPART(WEEKDAY, ReferralCreatedDateTime) = 6 -- Friday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 7) -- Saturday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 1) -- Sunday\n            OR (DATEPART(WEEKDAY, ReferralCreatedDateTime) = 2 AND DATEPART(HOUR, ReferralCreatedDateTime) < 6) -- Monday before 6 AM\n          )\n    GROUP BY \n        DATEADD(DAY, -((DATEPART(WEEKDAY, ReferralCreatedDateTime) + 1) % 7), CAST(ReferralCreatedDateTime AS DATE))\n)\n-- Calculate this weekend's referrals\n, ThisWeekend AS (\n    SELECT \n        MAX(WeekendStart) AS ThisWeekendStart, \n        (SELECT TOP 1 ReferralCount FROM WeekendData ORDER BY WeekendStart DESC) AS ThisWeekendReferrals\n    FROM WeekendData\n)\n-- Calculate the average referrals for the previous weekends\n, PreviousWeekends AS (\n    SELECT \n        CAST(AVG(CAST(ReferralCount AS DECIMAL(10, 2))) AS DECIMAL(10, 2)) AS AvgPreviousWeekendReferrals\n    FROM WeekendData\n    WHERE WeekendStart < (SELECT ThisWeekendStart FROM ThisWeekend)\n)\n\n-- Combine and compare the results\nSELECT \n    ThisWeekend.ThisWeekendReferrals,\n    PreviousWeekends.AvgPreviousWeekendReferrals,\n    CASE \n        WHEN ThisWeekend.ThisWeekendReferrals > PreviousWeekends.AvgPreviousWeekendReferrals \n            THEN 'Above Average'\n        WHEN ThisWeekend.ThisWeekendReferrals < PreviousWeekends.AvgPreviousWeekendReferrals \n            THEN 'Below Average'\n        ELSE 'Equal to Average'\n    END AS ComparisonResult\nFROM \n    ThisWeekend,\n    PreviousWeekends;"
        }
      ]
    }
    ]

@app.route("/query", methods=["POST"])
@swag_from(main_swagger)
def query_db():
    user_query = request.json.get('query')
    user_query_lower = user_query.lower()
    
    global conversation_history
    conversation_history.append({
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": f"{user_query}"
        }
      ]
    },)
    
    conversation_history = managing_payload(conversation_history)
    
    try:
        sql_query = None #findSqlQueryFromDB(userQuestion=user_query)
        if sql_query==None:
            response = gpt_4_model(conversation_history)
            sql_query = extractSqlQueryFromResponse(response=response)
            
            #return text
            if sql_query == None:
                results = {"text":response}
                id = insertQueryLog(userQuestion=user_query,Response=results)
                return jsonify({"results":results, "id":str(id)}),200
                
        conversation_history.append({"role": "assistant", "content": [{"type":"text", "text":f"{sql_query}"}]})
        
        headers, rows = readSqlDatabse(sql_query)
        if((len(headers) or len(rows)) == 0):
            results = {"text":"I found 0 records in database on your search. Please try asking different question or adjust your search criteria."}
            id = insertQueryLog(userQuestion=user_query,sqlQuery=sql_query,Response=results)
            return jsonify({"results":results, "id":str(id), "sql_query":str(sql_query)}),200
        
        if re.search(r'\b(chart|graph)\b', user_query_lower):
            chartType = 'doughnut' if 'chart' in user_query_lower else 'bar'
            results = {
                    "labels": [str(row[headers[0]]) for row in rows],
                    "data": [str(row[headers[1]]) for row in rows],
                    "type" : chartType,
                }
            id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
            return jsonify({"results":results, "id":str(id), "sql_query":str(sql_query)}),200
        #returns data for table
        formatted_rows = [[str(row[header]) for header in headers] for row in rows]
        results = {
                "headers": headers,
                "rows": formatted_rows,
            }
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, Response=results,isDataFetchedFromDB=True)
        return jsonify({"results":results, "id":str(id), "sql_query":str(sql_query)}),200
    
    except openai.error.OpenAIError as e:
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"OpenAI Model Error: {str(e)}", "id":str(id), "sql_query":str(sql_query)}), 500
    except SQLAlchemyError as e:
        base_err = "I apologize for the confusion. It seems I misunderstood your question, leading to a response that is not related to the database tables and columns I have access to. "
        similar_questions = find_best_matching_user_questions(userQuestion=user_query)
    
        err = base_err + ("Here are some similar questions that might be helpful for you. " if similar_questions else "") + "Is there anything else I can assist you with?"
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        
        results = {
            "error": err,
            "similar_questions":similar_questions,
            "id": str(id),
            "sql_query":str(sql_query)
        }
        
        return jsonify(results), 500
    except Exception as e:
        id = insertQueryLog(userQuestion=user_query, sqlQuery=sql_query, exceptionMessage=str(e))
        return jsonify({"error":f"I apologize for the inconvenience. It seems there was an error in the response, Please try some other questions.{e}", "id":str(id), "sql_query":str(sql_query)}), 500
    
    

@app.route("/feedback", methods=["POST"])
@swag_from(feedback_swagger)
def submit_feedback():
    data = request.get_json()
    resID = data.get('resID')
    feedback = bool(data.get('feedback'))
    userQuestion = data.get('userQuestion')

    try:
        saveFeedback(resID,feedback,userQuestion)
        return jsonify({"message": "Feedback submitted successfully!"}), 200 
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)