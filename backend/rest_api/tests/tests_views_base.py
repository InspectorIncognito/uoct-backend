import json
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework.reverse import reverse


class BaseTestCase(APITestCase):
    fixtures = [
    ]

    GET_REQUEST = "get"
    POST_REQUEST = "post"
    PUT_REQUEST = "put"  # update
    PATCH_REQUEST = "patch"  # partial update
    DELETE_REQUEST = "delete"

    def setUp(self):
        self.client = APIClient()

    def _make_request(self, client, method, url, data=None, status_code=status.HTTP_200_OK, json_process=False, **additional_method_params):
        method_obj = None
        if method == self.GET_REQUEST:
            method_obj = client.get
        elif method == self.POST_REQUEST:
            method_obj = client.post
        elif method == self.PATCH_REQUEST:
            method_obj = client.patch
        elif method == self.PUT_REQUEST:
            method_obj = client.put
        elif method == self.DELETE_REQUEST:
            method_obj = client.delete
        response = method_obj(url, data, **additional_method_params)
        if response.status_code != status_code:
            print(f"error {response.status_code}: {response.content}")
            self.assertEqual(status_code, response.status_code)

        if json_process:
            return json.loads(response.content)
        return response

    @staticmethod
    def create_user(username, password):
        user_user_attributes = {
            "username": username,
            "password": password
        }
        return get_user_model().objects.create_user(**user_user_attributes)

    def login_process(self):
        user_credentials = {"username": "TestUser", "password": "TestPassword"}
        self.create_user(**user_credentials)
        login_response = self._make_request(self.client, self.POST_REQUEST, reverse('login'), data=user_credentials)
        login_token = json.loads(login_response.content.decode('utf-8'))['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token {}'.format(login_token))
