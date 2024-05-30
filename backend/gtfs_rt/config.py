from pathlib import Path

import pytz
from decouple import config
from django.utils.timezone import get_current_timezone


ROOT_PATH = Path(__file__).parent
PROTO_URL = config('PROTO_URL')
TIMEZONE = get_current_timezone()
