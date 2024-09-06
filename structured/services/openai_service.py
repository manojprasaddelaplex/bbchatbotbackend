import os
import openai

openai.api_key = os.getenv('OPENAI_API_KEY')
openai.api_base = os.getenv('OPENAI_API_BASE')
openai.api_type = os.getenv('OPENAI_API_TYPE')
openai.api_version = os.getenv('OPENAI_API_VERSION')

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

def generate_sql_query(conversation_history):
    response = openai.ChatCompletion.create(
        deployment_id=os.getenv('DEPLOYMENT_ID'),
        messages=conversation_history,
        max_tokens=3000
    )
    
    return response.choices[0].message['content'].strip()