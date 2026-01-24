"""
URL configuration for bookmaker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.views.generic import RedirectView
from django.conf.urls.static import static
from matches import views

from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.matches_dashboard, name='dashboard'),
    path('dashboard/', views.matches_dashboard, name='dashboard'),
    path('match/<int:match_id>/', views.match_detail, name='match_detail'),
    path('match/<int:match_id>/bet/', views.place_bet, name='place_bet'),
    path('my-bets/', views.my_bets, name='my_bets'),
    path('matches/', views.matches_dashboard, name='matches_dashboard'),


    path("accounts/", include("accounts.urls")),

    # Redirect root to dashboard
    path('', RedirectView.as_view(pattern_name='dashboard', permanent=False)),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)