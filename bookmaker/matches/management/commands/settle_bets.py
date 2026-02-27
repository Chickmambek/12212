from django.core.management.base import BaseCommand
from matches.models import Match
from matches.services.settlement import settle_bets_for_match
import logging

class Command(BaseCommand):
    help = 'Settles pending bets for finished matches'

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        self.stdout.write("Starting bet settlement...")

        # Find all matches that are finished but might have pending bets
        # We check matches finished in the last 24 hours to be safe, or just all finished matches
        # Ideally, we should have a flag 'bets_settled' on the Match model, but for now we query bets.
        
        finished_matches = Match.objects.filter(status=Match.STATUS_FINISHED)
        
        count = 0
        for match in finished_matches:
            # Optimization: Only call settlement if there are actually pending bets
            if match.bets.filter(status='pending').exists():
                self.stdout.write(f"Settling bets for {match}...")
                settle_bets_for_match(match)
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f"Settlement complete. Processed {count} matches."))
