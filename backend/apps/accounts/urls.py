from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("auth/csrf/", views.CSRFView.as_view(), name="csrf"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("auth/resend-verification/", views.RequestEmailView.as_view(), name="resend-verification"),
    path("auth/password-reset/", views.ForgotPasswordView.as_view(), name="password-reset"),
    path(
        "auth/password-reset/confirm/",
        views.ResetPasswordView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/logout-all/", views.LogoutAllView.as_view(), name="logout-all"),
    path("auth/reauthenticate/", views.ReauthenticateView.as_view(), name="reauthenticate"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/personal-data/", views.PersonalDataView.as_view(), name="personal-data"),
    path("privacy-requests/<uuid:pk>/", views.PrivacyRequestView.as_view(), name="privacy-request"),
    path("admin/account-stats/", views.AdminAccountStatsView.as_view(), name="admin-account-stats"),
]
