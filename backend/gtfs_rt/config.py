from pathlib import Path

import decouple
from decouple import config
from django.utils.timezone import get_current_timezone


ROOT_PATH = Path(__file__).parent
try:
    PROTO_URL = config('PROTO_URL')
except decouple.UndefinedValueError:
    PROTO_URL = None
TIMEZONE = get_current_timezone()
