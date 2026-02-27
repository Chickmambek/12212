from rest_framework import serializers
from .models import Match, Bet, ExpressBet, ExpressBetSelection

class MatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = ['id', 'home_team', 'away_team', 'match_date', 'status', 
                 'home_score', 'away_score', 'league', 'league_order']

class BetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bet 
        fields = ['id', 'user', 'match', 'bet_type', 'odds', 'amount',
                 'potential_payout', 'status', 'created_at']

class ExpressBetSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpressBetSelection
        fields = ['id', 'express_bet', 'match', 'bet_type', 'odds']

class ExpressBetSerializer(serializers.ModelSerializer):
    selections = ExpressBetSelectionSerializer(many=True, read_only=True)

    class Meta:
        model = ExpressBet
        fields = ['id', 'user', 'selections', 'amount', 'total_odds',
                 'potential_payout', 'status', 'created_at']