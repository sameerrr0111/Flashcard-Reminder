import os
from openai import OpenAI
from dotenv import load_dotenv
import json


def _normalize_flashcards(parsed_response) -> list[dict]:
    """
    Normalize model JSON output into a validated list of {'Q': ..., 'A': ...} cards.
    Accepts common shapes:
    - {"flashcards": [{"Q": "...", "A": "..."}, ...]}
    - [{"Q": "...", "A": "..."}, ...]
    - {"Q": "...", "A": "..."} (single-card object)
    - question/answer key variants
    """
    candidates = []

    if isinstance(parsed_response, dict):
        if isinstance(parsed_response.get("flashcards"), list):
            candidates = parsed_response["flashcards"]
        elif "Q" in parsed_response and "A" in parsed_response:
            candidates = [parsed_response]
        elif "question" in parsed_response and "answer" in parsed_response:
            candidates = [{"Q": parsed_response.get("question"), "A": parsed_response.get("answer")}]
    elif isinstance(parsed_response, list):
        candidates = parsed_response

    valid_flashcards = []
    for card in candidates:
        if not isinstance(card, dict):
            continue

        question = card.get("Q") or card.get("question")
        answer = card.get("A") or card.get("answer")

        if isinstance(question, str) and isinstance(answer, str) and question.strip() and answer.strip():
            valid_flashcards.append({"Q": question.strip(), "A": answer.strip()})

    return valid_flashcards

# Load environment variables from .env file
load_dotenv()

# --- OpenAI API Initialization ---
def get_openai_client():
    """
    Initializes and returns an OpenAI client.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")
    
    try:
        client = OpenAI(api_key=api_key)
        print("OpenAI client initialized.")
        return client
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
        raise

# --- Flashcard Generation Logic ---
def generate_flashcards_from_chat(chat_text: str) -> list[dict]:
    """
    Sends the chat text to the OpenAI API to generate flashcards.
    Returns a list of dictionaries, each with a 'Q' and 'A' key.
    """
    client = get_openai_client()
    
    # Return an object with a flashcards array because response_format=json_object
    # requires the top-level JSON to be an object.
    prompt = f"""
    You are an expert educator highly skilled at extracting key information and creating concise flashcards.
    Your task is to analyze the following conversation and generate a list of flashcards.
    Each flashcard should consist of a clear, concise question (Q) and a short, direct answer (A).
    Focus on important concepts, definitions, or procedural steps.
    
    Format your output strictly as a JSON object with a single key "flashcards".
    The "flashcards" value must be a JSON array of objects, and each object must have "Q" and "A" keys.
    Do NOT include any preamble, conversational text, or explanations outside the JSON array.
    Ensure the JSON is valid and parsable.

    Example:
    {{
        "flashcards": [
            {{"Q": "What is the capital of France?", "A": "Paris"}},
            {{"Q": "Who wrote 'Romeo and Juliet'?", "A": "William Shakespeare"}}
        ]
    }}

    Conversation to convert into flashcards:
    ---
    {chat_text}
    ---
    """
    
    try:
        print("Sending chat text to OpenAI for flashcard generation...")
        chat_completion = client.chat.completions.create(
            model="gpt-3.5-turbo", # You can choose a different model like "gpt-4" for higher quality
            response_format={ "type": "json_object" }, # Instructs the model to respond with JSON
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7, # Adjust creativity; lower for more factual, higher for more varied.
        )
        
        # The model's response will be a JSON string that we need to parse.
        response_content = chat_completion.choices[0].message.content
        print("Received response from OpenAI.")
        
        parsed_response = json.loads(response_content)

        flashcards = _normalize_flashcards(parsed_response)
        if not flashcards:
            print(f"Warning: Unexpected JSON structure from OpenAI: {response_content}")
            return []

        print(f"Generated {len(flashcards)} flashcards.")
        return flashcards

    except ValueError as ve:
        print(f"Error parsing OpenAI response (likely not valid JSON): {ve}")
        print(f"Raw response content: {response_content}")
        return []
    except Exception as e:
        print(f"Error generating flashcards with OpenAI API: {e}")
        return []