from django.http import JsonResponse
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.status import HTTP_200_OK
from rest_framework import generics
from user.serializers import UserLoginSerializer, UserSerializer


class LoginViewSet(generics.GenericAPIView):
    serializer_class = UserLoginSerializer
    permission_classes = [AllowAny, ]

    def post(self, request, *args, **kwargs):
        login_serializer = self.serializer_class(data=request.data)
        if not login_serializer.is_valid():
            raise AuthenticationFailed()
        user = login_serializer.context["user"]
        user.last_login = timezone.localtime()
        user.save()

        user_data = UserSerializer(user).data
        token, _ = Token.objects.get_or_create(user=user)
        user_data.update({"token": token.key})

        return JsonResponse(user_data, status=HTTP_200_OK)


class VerifyViewSet(generics.GenericAPIView):
    serializer_class = UserSerializer
    authentication_classes = [TokenAuthentication, ]

    def post(self, request, *args, **kwargs):
        user_data = UserSerializer(request.user).data
        user_data.update({"token": request.auth.key})

        return JsonResponse(user_data, status=HTTP_200_OK)
