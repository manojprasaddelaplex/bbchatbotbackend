import re

def extractSqlQueryFromResponse(response):
    code_block_pattern = r'```(?:sql)?\s*([\s\S]+?)\s*```'
    code_block_match = re.search(code_block_pattern, response, re.IGNORECASE)
    
    if code_block_match:
        sql_content = code_block_match.group(1)
    else:
        sql_content = response
    
    sql_pattern = r'(WITH|SELECT)[\s\S]+?;'
    sql_match = re.search(sql_pattern, sql_content, re.IGNORECASE | re.MULTILINE)
    
    if sql_match:
        return sql_match.group(0).strip()
    else:
        return None