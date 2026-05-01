"""URL routes for API endpoints."""

from django.urls import path

from api.views import RouteAPIView

urlpatterns = [
    path("route/", RouteAPIView.as_view(), name="route"),
]
