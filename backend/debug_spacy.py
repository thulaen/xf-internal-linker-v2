import spacy

try:
    nlp = spacy.load("en_core_web_sm")
    print("Success")
except Exception as e:
    print(f"Error: {e}")
