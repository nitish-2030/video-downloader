import json
import sys

from app.engine import get_info, EngineError

url = sys.argv[1]
try:
    print(json.dumps(get_info(url), indent=2))
except EngineError as error:
    print("FRIENDLY MESSAGE:", error.friendly)
    if error.details:
        print("DETAILS:", error.details[:300])