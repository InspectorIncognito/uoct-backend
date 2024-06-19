import decouple
from decouple import config

try:
    PROTO_URL = config('PROTO_URL')
except decouple.UndefinedValueError:
    PROTO_URL = None
