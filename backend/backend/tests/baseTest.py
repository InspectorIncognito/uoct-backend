from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse


class BaseTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user({
            'username': "TestUser",
            'password': "TestPassword"
        })
        self.client = APIClient()
        login_token = self.client.get(reverse('login')).content
        return
        self.client.credentials(HTTP_AUTHORIZATION='Token {0}'.format(login_token))
