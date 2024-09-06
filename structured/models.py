from datetime import datetime

class QueryLog:
    def __init__(self, user_question, sql_query=None, response=None, exception_message=None, 
                 is_data_fetched_from_db=False, is_correct=None, feedback_date_time=None):
        self.user_question = user_question
        self.sql_query = sql_query
        self.response = response
        self.exception_message = exception_message
        self.is_data_fetched_from_db = is_data_fetched_from_db
        self.is_correct = is_correct
        self.created_date_time = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        self.feedback_date_time = feedback_date_time

    def to_dict(self):
        return {
            "UserQuestion": self.user_question,
            "SqlQuery": self.sql_query,
            "Response": self.response,
            "ExceptionMessage": self.exception_message,
            "IsDataFetchedFromDB": self.is_data_fetched_from_db,
            "IsCorrect": self.is_correct,
            "CreatedDateTime": self.created_date_time,
            "FeedbackDateTime": self.feedback_date_time
        }