
from backend.analyzer import ai_json

result = ai_json(
    "Return a JSON object with pong set to true.",
    {"test": "ping"}
)

print(result)