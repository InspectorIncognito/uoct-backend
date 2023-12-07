from django.urls import reverse
from rest_framework import status

from rest_api.tests.tests_views_base import BaseTestCase
from user.serializers import UserSerializer


class UserRequestViewSetTest(BaseTestCase):

    def setUp(self) -> None:
        super(UserRequestViewSetTest, self).setUp()

        self.username = 'username'
        self.password = 'password123'
        self.user_obj = self.create_user(self.username, self.password)

    # =================================================================================
    # Helpers
    # =================================================================================

    def user_login(self, client, username, password, status_code=status.HTTP_200_OK):
        url = reverse('login')
        data = dict(username=username, password=password)
        return self._make_request(client, self.POST_REQUEST, url, data, status_code, json_process=True)

    def user_verify_session(self, client, username, token, status_code=status.HTTP_200_OK):
        url = reverse('verify')
        client.credentials(HTTP_AUTHORIZATION='Token {0}'.format(token))
        data = dict(username=username)
        return self._make_request(client, self.POST_REQUEST, url, data, status_code)

    # =================================================================================
    # Tests
    # =================================================================================

    def test_login_user_pass(self):
        json_response = self.user_login(self.client, self.username, self.password)

        user_data = UserSerializer(self.user_obj).data
        self.assertIsNotNone(json_response.pop('token'))
        self.assertDictEqual(json_response, user_data)

    def test_login_user_does_not_exist(self):
        self.user_login(self.client, 'wrong_user_name', 'wrong_password', status_code=status.HTTP_403_FORBIDDEN)

    def test_login_user_wrong_password(self):
        self.user_login(self.client, self.username, 'wrong_password', status_code=status.HTTP_403_FORBIDDEN)

    def test_verify_token(self):
        json_response = self.user_login(self.client, self.username, self.password)
        token = json_response['token']
        self.user_verify_session(self.client, self.username, token)

    def test_verify_wrong_token(self):
        wrong_token = 'asdasdasdasdasdasdasdasdasd'
        self.user_verify_session(self.client, self.username, wrong_token, status_code=status.HTTP_401_UNAUTHORIZED)
