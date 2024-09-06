import openai
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from flasgger import Swagger, swag_from
from functions import insertQueryLog, generateSqlQuery, readSqlDatabse, saveFeedback, findSqlQueryFromDB, extractSqlQueryFromResponse, manage_conversation_length, find_best_matching_user_questions
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
        "content": '''
        You are Sonar Chatbot, an expert at converting natural language into SQL queries for SQL Server.Only Use this schema (table_name:column_names_list):
            Referrals: [Id, ReferralDateTime, ReferredBy, CustodyNumber, RegistrationType, ReasonOfArrestOther, FmeRequired, VerballyPhysicallyAbusive, ThreatToFemaleStaff, DateAddedToWaitingList, State, CreatedByUserId, RecipientDetails, ReferralDetails, ReferralCreatedDateTime, CustodyLocationId, DetainedPersonId, RequestedAssessmentOther, ReferralFrom, ProcessedByHCP, CompletedByUserId, ReferralFromOther, PresentingComplaintId, DischargeDateTime, Discharged, Intervention, LocationAfterDischarge, DischargeCompletedByUserId, ProcessedByUserId, LastAction, LastKpiCalculationValue, ReferralStatusUpdateDateTime, BreachReasonOther, IsHcpSide, BreachReasonDateTime, WaitingListCompleteDateTime, RejectionDate, RejectionReason, RejectionReasonOther, ReferralInUpdatedByUserId, ReferralInUpdatedDateTime, OtherConcern, OtherLocation, Maintenance_RegistrationTypeId, LastKpiAssessmentCalculationValue, Maintenance_HcpRequiredTypeId, BreachReasonId, Maintenance_ReasonOfArrestTypeId, Maintenance_CellTypeId]
            HcpPatients: [Id, DetainedPersonId, RegisteredByUserId, DateOfRegistration, Forename, MiddleName, Surname, DateOfBirth, Gender, NhsNumber, Postcode, Address1, Address2, Town, County, TelephoneNumber, MobileNumber, SmartPhone, OtherNumber, Disability, Language, OtherLanguage, SexualOrientation, NhsPdsRawPatientData, ManualPdsUpdateDateTime, AddressAge, ChangeOfAddressCompletedByUserId, ChangeOfAddressDateTime, CorrespondenceAddressOnly, Email, PreferredContact, UseAddressInPatientSearches, IsGenderSameAsRegisteredAtBirth, SexualOrientationOther, Address3, GeneralPractitionerId, LastUpdatedDateTime, LastUpdatedUserId, WorkPhoneNumber, Maintenance_MaritalStatusTypeId, Maintenance_OccupationTypeId, Maintenance_ReligionTypeId, Maintenance_TitleTypeId, Maintenance_EnglishSpeakerTypeId, ArmedForcesTypeId, PlaceOfDetentionTypeId, Maintenance_EthnicityTypeId, Maintenance_DisabilityTypeId, Maintenance_GenderTypeId, Maintenance_LanguageTypeId]
        End all SQL queries with a semicolon. You are strictly prohibited from performing data modification tasks; only fetch data.
        For non-SQL-related questions, keep your responses brief and relevant to your purpose.
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
    
    conversation_history = manage_conversation_length(conversation_history)
    
    try:
        sql_query = findSqlQueryFromDB(userQuestion=user_query)
        if sql_query==None:
            response = generateSqlQuery(conversation_history)
            sql_query = extractSqlQueryFromResponse(response=response)
            
            conversation_history.append({"role": "assistant", "content": response if sql_query==None else sql_query})
            
            #return text
            if sql_query == None:
                results = {"text":response}
                # id = insertQueryLog(userQuestion=user_query,Response=results)
                return jsonify({"results":results}),200
                
                
        conversation_history.append({"role": "assistant", "content": sql_query})
        headers, rows = readSqlDatabse(sql_query)
        
        if((len(headers) or len(rows)) == 0):
            results = {"text":"Unfortunately, I found 0 records matching your search. Please try asking different question or adjust your search criteria."}
            id = insertQueryLog(userQuestion=user_query,sqlQuery=sql_query,Response=results)
            return jsonify({"results":results, "id":str(id)}),200
        
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
        return jsonify({"error":f"I apologize for the inconvenience. It seems there was an error in the response, Please try some other questions.", "id":str(id), "sql_query":str(sql_query)}), 500
    
    

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