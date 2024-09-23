import re
from datetime import datetime, timedelta

def extract_dates(bot_response):
    # Regular expression to find dates in the format YYYY-MM-DD
    date_pattern = r'\d{4}-\d{2}-\d{2}'
    
    # Find all dates in the text
    dates = re.findall(date_pattern, bot_response)
    
    if len(dates) >= 2:
        start_date = min(dates)
        end_date = max(dates)
    elif len(dates) == 1:
        start_date = dates[0]
        # If only one date is found, assume it's the start date and calculate end date
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = start_date_obj + timedelta(days=3)  # Assume 3 days duration
        end_date = end_date_obj.strftime('%Y-%m-%d')
    else:
        return None, None