import time
from .oaitokenizer import num_tokens_from_messages

def read_input_messages(file_name: str):
    """
    Read messages from a file, each line is considered a separate message.
    Returns a list of messages.
    """
    with open(file_name, 'r', encoding='utf-8') as file:
        return file.readlines()

def _generate_messages(model: str, tokens: int, max_tokens: int = None) -> ([dict], int):
    """
    Generate `messages` array based on tokens and max_tokens.
    Returns Tuple of messages array and actual context token count.
    """
    try:
        messages = []
        input_messages = read_input_messages('prompt_inputs.txt')
        for line_number, input_message in enumerate(input_messages, start=1):
            message = f"question number: {line_number} {input_message}"
            messages.append({"role": "user", "content": str(time.time()) + message})

        messages_tokens = num_tokens_from_messages(messages, model)
    except Exception as e:
        print(e)
        messages = []
        messages_tokens = 0

    return messages, messages_tokens

# Usage example
messages, messages_tokens = _generate_messages('gpt-4-0613', 1000, 500)
print(messages)
print(messages_tokens)
