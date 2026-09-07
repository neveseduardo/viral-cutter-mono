from django.urls import path

from . import views

app_name = "auth"

urlpatterns = [
    path("login", views.GuestLoginView.as_view(), name="login"),
    path("refresh", views.GuestRefreshView.as_view(), name="refresh"),
]