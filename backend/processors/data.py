import requests
from config.environment import PROTO_URL
from requests import Response


class ProtoFileProcessor:
    def __init__(self):
        self.url = PROTO_URL

    def download_proto_file(self) -> Response:
        return requests.get(self.url)


class ShapeProcessor:
    def __init__(self):
        pass