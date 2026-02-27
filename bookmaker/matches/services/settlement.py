import logging
from django.db import transaction
from matches.models import Match, Bet
from accounts.models import Profile

logger = logging.getLogger(__name__)

def settle_bets_for_match(match):
    """
    Settles all pending bets for a given match if the match is finished.
    """
    if match.status != Match.STATUS_FINISHED:
        logger.info(f"Match {match} is not finished. Skipping settlement.")
        return

    # Ensure we have a result
    if match.home_score is None or match.away_score is None:
        logger.warning(f"Match {match} is finished but has no score. Skipping.")
        return

    pending_bets = Bet.objects.filter(match=match, status=Bet.STATUS_PENDING)
    
    if not pending_bets.exists():
        logger.info(f"No pending bets for match {match}.")
        return

    logger.info(f"Settling {pending_bets.count()} bets for match {match} (Score: {match.home_score}-{match.away_score})")

    for bet in pending_bets:
        try:
            with transaction.atomic():
                # Re-fetch bet to lock it
                bet = Bet.objects.select_for_update().get(id=bet.id)
                
                # Double check status inside lock
                if bet.status != Bet.STATUS_PENDING:
                    continue

                is_winner = False

                # --- 1X2 (Match Winner) ---
                if bet.bet_type == Bet.BET_TYPE_HOME:
                    if match.home_score > match.away_score:
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_DRAW:
                    if match.home_score == match.away_score:
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_AWAY:
                    if match.away_score > match.home_score:
                        is_winner = True
                
                # --- Double Chance ---
                elif bet.bet_type == Bet.BET_TYPE_1X:
                    if match.home_score >= match.away_score: # Home win or Draw
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_12:
                    if match.home_score != match.away_score: # Home win or Away win
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_X2:
                    if match.away_score >= match.home_score: # Away win or Draw
                        is_winner = True

                # --- Total Goals (Over/Under 2.5) ---
                elif bet.bet_type == Bet.BET_TYPE_OVER_25:
                    if (match.home_score + match.away_score) > 2.5:
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_UNDER_25:
                    if (match.home_score + match.away_score) < 2.5:
                        is_winner = True

                # --- Handicap (Home -1.5 / Away +1.5) ---
                # Assuming standard handicap value of 1.5 for now as per model default
                elif bet.bet_type == Bet.BET_TYPE_HANDICAP_HOME:
                    # Home team starts with -1.5 goals
                    if (match.home_score - 1.5) > match.away_score:
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_HANDICAP_AWAY:
                    # Away team starts with +1.5 goals
                    if (match.away_score + 1.5) > match.home_score:
                        is_winner = True

                # --- Both Teams To Score (BTTS) ---
                elif bet.bet_type == Bet.BET_TYPE_BTTS_YES:
                    if match.home_score > 0 and match.away_score > 0:
                        is_winner = True
                elif bet.bet_type == Bet.BET_TYPE_BTTS_NO:
                    if match.home_score == 0 or match.away_score == 0:
                        is_winner = True

                # --- Settlement ---
                if is_winner:
                    bet.status = Bet.STATUS_WON
                    # Credit User
                    profile = Profile.objects.select_for_update().get(user=bet.user)
                    profile.balance += bet.potential_payout
                    profile.save()
                    logger.info(f"Bet #{bet.id} WON. User {bet.user} credited {bet.potential_payout}")
                else:
                    bet.status = Bet.STATUS_LOST
                    logger.info(f"Bet #{bet.id} LOST.")
                
                bet.save()

        except Exception as e:
            logger.error(f"Error settling bet #{bet.id}: {e}")
