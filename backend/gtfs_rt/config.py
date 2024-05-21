from pathlib import Path

import pytz
from decouple import config


ROOT_PATH = Path(__file__).parent
PROTO_URL = config('PROTO_URL')
SANTIAGO_TIMEZONE = pytz.timezone('America/Santiago')
