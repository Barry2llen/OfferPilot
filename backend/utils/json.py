import json
from typing import Any

def jsonify(obj: Any) -> str:
    return json.dumps(obj, default=lambda o: o.__dict__, indent=2, ensure_ascii=False)