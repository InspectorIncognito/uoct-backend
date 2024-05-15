from pathlib import Path
from decouple import config


ROOT_PATH = Path(__file__).parent
PROTO_URL = config('PROTO_URL')
