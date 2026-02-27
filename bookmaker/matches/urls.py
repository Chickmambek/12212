from django.urls import path
from . import views

urlpatterns = [
    path('', views.matches_dashboard, name='dashboard'),
    path('<int:match_id>/', views.match_detail, name='match_detail'),
    path('bet/<int:match_id>/', views.place_bet, name='place_bet'),
    path('express_bet/', views.place_express_bet, name='place_express_bet'),
    path('my_bets/', views.my_bets, name='my_bets'),
    path('teams/', views.teams_list, name='teams_list'),
    
    # API endpoints
    path('api/search/', views.search_matches, name='search_matches'),
    path('api/leagues/', views.get_leagues, name='get_leagues'),
]