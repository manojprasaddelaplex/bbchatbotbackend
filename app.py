import openai
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from flasgger import Swagger, swag_from
from functions import insertQueryLog, generateSqlQuery, readSqlDatabse, saveFeedback, findSqlQueryFromDB, extractSqlQueryFromResponse
from swaggerData import main_swagger, feedback_swagger

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
swagger = Swagger(app)


@app.route("/")
def home():
    return redirect('/apidocs/')

conversation_history = [
    {
        "role": "system",
        "content": '''
        You are an assistant that converts natural language into SQL queries for a SQL Server database. The database has the following schema (table_name:column_names_list):
            PresentingComplaintHistory: [id(int), ReferralId(int), ComplaintOther(nvarchar), HistoryOfPresentingComplaint(nvarchar), CreatedDate(datetimeoffset), CreatedByUserId(nvarchar), PresentingComplaintId(int)].
            DetainedPersons: [Id(int), Forename(nvarchar), MiddleName(nvarchar), Surname(nvarchar), DateOfBirth(datetimeoffset), Gender(int), Postcode(nvarchar), Address1(nvarchar), Address2(nvarchar), Town(nvarchar), City(nvarchar), County(nvarchar), SexualOrientation(int), IsGenderSameAsRegisteredAtBirth(bit), SexualOrientationOther(nvarchar), Archived(bit), IsHcpSide(bit), Address3(nvarchar), Maintenance_GenderTypeId(int)].
            Referrals: [id(int), ReferralDateTime(datetimeoffset), ReferredBy(nvarchar), CustodyNumber(nvarchar), RegistrationType(int), ReasonOfArrestOther(nvarchar), FmeRequired(bit), VerballyPhysicallyAbusive(bit), ThreatToFemaleStaff(bit), DateAddedToWaitingList(datetimeoffset), State(int), CreatedByUserId(nvarchar), RecipientDetails(nvarchar), ReferralDetails(nvarchar), ReferralCreatedDateTime(datetimeoffset), CustodyLocationId(int), DetainedPersonId(int), RequestedAssessmentOther(nvarchar), ReferralFrom(int), ProcessedByHCP(bit), CompletedByUserId(nvarchar), ReferralFromOther(nvarchar), PresentingComplaintId(int), DischargeDateTime(datetimeoffset), Discharged(bit), Intervention(int), LocationAfterDischarge(int), DischargeCompletedByUserId(nvarchar), ProcessedByUserId(nvarchar), LastAction(nvarchar), LastKpiCalculationValue(int), ReferralStatusUpdateDateTime(datetimeoffset), BreachReasonOther(nvarchar), IsHcpSide(bit), BreachReasonDateTime(datetimeoffset), WaitingListCompleteDateTime(datetimeoffset), RejectionDate(datetimeoffset), RejectionReason(int), RejectionReasonOther(nvarchar), ReferralInUpdatedByUserId(nvarchar), ReferralInUpdatedDateTime(datetimeoffset), OtherConcern(nvarchar), OtherLocation(nvarchar), Maintenance_RegistrationTypeId(int), LastKpiAssessmentCalculationValue(int), Maintenance_HcpRequiredTypeId(int), BreachReasonId(int), Maintenance_ReasonOfArrestTypeId(int), Maintenance_CellTypeId(int)].
            PresentingComplaints: [Id(int), ReferralId(int), ComplaintOther(nvarchar), HistoryOfPresentingComplaint(nvarchar), CreatedDate(datetimeoffset)].
            Maintenance_BreachReasonType: [Id(int), Name(nvarchar), Value(int)].            
        Please provide only SQL query, Always end SQL query with a semicolon.
        '''
    }
    ]

@app.route("/query", methods=["POST"])
@swag_from(main_swagger)
def query_db():
    user_query = request.json.get('query')
    user_query_lower = user_query.lower()
    
    global conversation_history
    conversation_history.append({"role": "user", "content": user_query})
    
    if len(conversation_history) > 11:
        conversation_history = [conversation_history[0]] + conversation_history[-10:]
        
    try:
        sql_query = findSqlQueryFromDB(userQuestion=user_query)
        if sql_query==None:
            response = generateSqlQuery(conversation_history)
            sql_query = extractSqlQueryFromResponse(response=response)
            
            conversation_history.append({"role": "assistant", "content": response if sql_query==None else sql_query})
            
            #return text
            if sql_query == None:
                results = {"text":response}
                id = insertQueryLog(userQuestion=user_query,Response=response)
                return jsonify({"results":results, "id":str(id)}),200
                
        
        conversation_history.append({"role": "assistant", "content": sql_query})
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