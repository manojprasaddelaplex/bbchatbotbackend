import re
import tiktoken

def extract_sql_query_from_response(response):
    sql_pattern = r'(WITH|SELECT)[\s\S]+?;'
    matches = re.search(sql_pattern, response, re.IGNORECASE)
    if matches:
        return matches.group(0).strip()
    else:
        return None

def estimate_tokens(text):
    enc = tiktoken.get_encoding("cl100k_base")
    enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(enc.encode(text))

def manage_conversation_length(conversation):
    total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
    system_prompt_index = next((i for i, entry in enumerate(conversation) if entry["role"] == "system"), None)
    
    if len(conversation) > 7:
        conversation = [conversation[0]] + conversation[-6:]
    
    while total_tokens > 1050 and system_prompt_index is not None:
        if len(conversation) > system_prompt_index + 1:
            conversation.pop(system_prompt_index + 1)
            total_tokens = sum(estimate_tokens(entry["content"]) for entry in conversation)
        else:
            break
    
    return conversation