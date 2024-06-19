"""backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from user.views import VerifyViewSet, LoginViewSet

urlpatterns = [
    path("api/login", LoginViewSet.as_view(), name="login"),
    path("api/verify", VerifyViewSet.as_view(), name="verify"),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('admin/', admin.site.urls),
    path('api/gps/', include(('gps.urls', 'gps'), namespace='gps')),
    path('api/geo/', include(('rest_api.urls', 'geo'), namespace='geo')),
    path('api/gtfs_rt/', include(('gtfs_rt.routers', 'gtfs_rt'), namespace='gtfs_rt')),
]

urlpatterns += [
    path('django-rq/', include('django_rq.urls'))
]
