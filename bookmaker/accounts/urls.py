from django.urls import path
from .views import (register_view, login_view, logout_view, balance_view, crypto_deposit_view, payment_pending,
                    ajax_check_deposit, profile_view)

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile'),
    path('balance/', balance_view, name='balance'),
    path('crypto-deposit/', crypto_deposit_view, name='crypto_deposit'),
    path('deposit/pending/<int:tx_id>/', payment_pending, name='payment_pending'),
    path('deposit/check/<int:tx_id>/', ajax_check_deposit, name='ajax_check_deposit')
]
