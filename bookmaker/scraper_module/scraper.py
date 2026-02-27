# scraper/scraper.py
import asyncio
import time
import re
import traceback
from datetime import datetime, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import logging
from tqdm import tqdm
from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async
from matches.models import Match, Bookmaker, Odds, Team, Market, Outcome

logger = logging.getLogger(__name__)

class XStakeScraper:
    def __init__(self):
        self.base_url = "https://gh7.bet/line/201"
        self.playwright = None
        self.browser = None
        self.page = None
        print("✅ XStakeScraper initialized with Playwright (async)")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup_driver(self):
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ]
            )
            self.page = await self.browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            print("✅ Playwright browser & page setup successfully")
            return True
        except Exception as e:
            print(f"❌ Error setting up Playwright driver: {e}")
            await self.cleanup()
            return False

    async def cleanup(self):
        cleanup_errors = []
        try:
            if self.page:
                await self.page.close()
                self.page = None
                print("✅ Page closed")
        except Exception as e:
            cleanup_errors.append(f"Page close: {e}")
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
                print("✅ Browser closed")
        except Exception as e:
            cleanup_errors.append(f"Browser close: {e}")
        try:
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                print("✅ Playwright stopped")
        except Exception as e:
            cleanup_errors.append(f"Playwright stop: {e}")
        if cleanup_errors:
            print(f"⚠️ Cleanup warnings: {', '.join(cleanup_errors)}")

    def parse_match_datetime(self, date_string, time_string):
        try:
            day, month = date_string.split('.')
            current_year = datetime.now().year
            hours, minutes = time_string.split(':')
            naive_datetime = datetime(current_year, int(month), int(day), int(hours), int(minutes))
            aware_datetime = timezone.make_aware(naive_datetime)
            return aware_datetime
        except Exception:
            return timezone.now()

    def parse_odds(self, odds_text):
        """Parse odds text to float, handling commas and invalid input."""
        try:
            if odds_text is None:
                return None
            cleaned = re.sub(r'[^\d.,-]', '', str(odds_text))
            cleaned = cleaned.replace(',', '.')
            odds_value = float(cleaned)
            return odds_value
        except (ValueError, TypeError):
            return None

    async def extract_logo_url(self, element):
        try:
            style = await element.get_attribute('style')
            if style and 'background-image' in style:
                pattern = r'url\("([^"]+)"\)'
                match = re.search(pattern, style)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    async def wait_for_selector_safe(self, selector, timeout=10000):
        try:
            return await self.page.wait_for_selector(selector, timeout=timeout)
        except PlaywrightTimeoutError:
            return None

    async def query_all(self, selector):
        try:
            elements = await self.page.query_selector_all(selector)
            return elements or []
        except Exception:
            return []

    async def monitor_main_list_persistent(self, status_check_callback=None, log_callback=None):
        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)

        url = "https://gh7.bet/line/201"
        await log(f"🟢 Opening persistent connection to Main List: {url}")

        try:
            if not self.page:
                await self.setup_driver()

            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await log("   ✅ Page loaded. Waiting for dynamic content...")

            try:
                await self.page.wait_for_selector(".accordion.league-wrap", timeout=15000)
            except:
                await log("   ⚠️ Timeout waiting for league selector, proceeding anyway...")

            heartbeat = 0
            current_match_identifiers = set()
            last_cleanup_time = timezone.now()

            while True:
                if status_check_callback:
                    should_continue = await status_check_callback()
                    if not should_continue:
                        await log("🛑 Stop signal received. Exiting monitor loop.")
                        await self.cleanup_old_matches(current_match_identifiers)
                        break

                current_match_identifiers.clear()

                # ⬇️ Updated JavaScript evaluation (fixed logo extraction)
                scraped_data = await self.page.evaluate("""() => {
                    const matches = [];
                    const leagues = document.querySelectorAll('.accordion.league-wrap, .league-wrap');

                    leagues.forEach(league => {
                        let leagueName = "Unknown";
                        const titleEl = league.querySelector('.icon-title__text');
                        if (titleEl) leagueName = titleEl.innerText.trim();

                        // League logo
                        let leagueLogo = null;
                        const lIcon = league.querySelector('.icon-title__icon');
                        if (lIcon) {
                            const bg = window.getComputedStyle(lIcon).backgroundImage;
                            if (bg && bg !== 'none') {
                                leagueLogo = bg.replace(/^url\\(["']?/, '').replace(/["']?\\)$/, '');
                            }
                        }

                        const events = league.querySelectorAll('.event');

                        events.forEach(event => {
                            const match = {
                                league_name: leagueName,
                                league_logo: leagueLogo,   // store league logo
                                match_url: null,
                                raw_date: "",
                                raw_time: "",
                                home_team: "",
                                away_team: "",
                                home_odds: null,
                                draw_odds: null,
                                away_odds: null,
                                home_logo: null,
                                away_logo: null,
                                markets: []
                            };

                            const link = event.querySelector('a.event__link') || event.querySelector('a');
                            if (link) {
                                const href = link.getAttribute('href');
                                match.match_url = href.startsWith('http') ? href : 'https://gh7.bet' + (href.startsWith('/') ? href : '/' + href);
                            }

                            const timeEl = event.querySelector('.time__hours');
                            const dateEl = event.querySelector('.time__date');
                            if (timeEl) match.raw_time = timeEl.innerText.trim();
                            if (dateEl) match.raw_date = dateEl.innerText.trim();
    
                            const opps = event.querySelectorAll('.opps__container .icon-title__text');
                            if (opps.length >= 2) {
                                match.home_team = opps[0].innerText.trim();
                                match.away_team = opps[1].innerText.trim();

                               
                            } else {
                                const teams = event.querySelectorAll('.icon-title__text');
                                if (teams.length >= 2) {
                                    match.home_team = teams[0].innerText.trim();
                                    match.away_team = teams[1].innerText.trim();
                                }
                            }
                            
                            const teamContainers = event.querySelectorAll('.opps__container .icon-title');
if (teamContainers.length >= 2) {
    // Home team
    const homeContainer = teamContainers[0];
    const homeTextEl = homeContainer.querySelector('.icon-title__text');
    if (homeTextEl) match.home_team = homeTextEl.innerText.trim();
    const homeIconEl = homeContainer.querySelector('.icon-title__icon');
    if (homeIconEl) {
        const bg = window.getComputedStyle(homeIconEl).backgroundImage;
        if (bg && bg !== 'none') {
            match.home_logo = bg.replace(/^url\(["']?/, '').replace(/["']?\)$/, '').trim();
        }
    }

    // Away team
    const awayContainer = teamContainers[1];
    const awayTextEl = awayContainer.querySelector('.icon-title__text');
    if (awayTextEl) match.away_team = awayTextEl.innerText.trim();
    const awayIconEl = awayContainer.querySelector('.icon-title__icon');
    if (awayIconEl) {
        const bg = window.getComputedStyle(awayIconEl).backgroundImage;
        if (bg && bg !== 'none') {
            match.away_logo = bg.replace(/^url\(["']?/, '').replace(/["']?\)$/, '').trim();
        }
    }
}

                            const oddsContainer = event.querySelector('.odds');
                            if (oddsContainer) {
                                const buttons = oddsContainer.querySelectorAll('.stake-button');
                                if (buttons.length >= 3) {
                                    const h = buttons[0].querySelector('.formated-odd');
                                    const d = buttons[1].querySelector('.formated-odd');
                                    const a = buttons[2].querySelector('.formated-odd');

                                    if (h) match.home_odds = h.innerText.trim();
                                    if (d) match.draw_odds = d.innerText.trim();
                                    if (a) match.away_odds = a.innerText.trim();
                                }
                            }

                            if (match.home_team && match.away_team) {
                                matches.push(match);
                            }
                        });
                    });
                    return matches;
                }""")

                if scraped_data:
                    await log(f"\n   📥 Extracted {len(scraped_data)} matches. Processing...")

                    processed_data = []
                    for m in scraped_data:
                        # Basic match info
                       # await log(f"      ⚽ {m['home_team']} vs {m['away_team']} ({m['league_name']})")

                        # ⬇️ New: log logo URLs if they exist
                        logo_info = []
                        if m.get('league_logo'):
                            logo_info.append(f"League: {m['league_logo']}")
                        if m.get('home_logo'):
                            logo_info.append(f"Home: {m['home_logo']}")
                        if m.get('away_logo'):
                            logo_info.append(f"Away: {m['away_logo']}")
                        #if logo_info:
                            #await log(f"         🖼️  Logos: {', '.join(logo_info)}")

                       # await log(
                       #     f"         🕒 {m['raw_time']} | Odds: 1: {m['home_odds']} | X: {m['draw_odds']} | 2: {m['away_odds']}")

                        # Parse odds, create datetime, etc.
                        m['home_odds'] = self.parse_odds(m['home_odds'])
                        m['draw_odds'] = self.parse_odds(m['draw_odds'])
                        m['away_odds'] = self.parse_odds(m['away_odds'])

                        try:
                            if m['raw_date'] and m['raw_time']:
                                day, month = map(int, m['raw_date'].split('.'))
                                hour, minute = map(int, m['raw_time'].split(':'))
                                year = datetime.now().year
                                dt = datetime(year, month, day, hour, minute)
                                m['match_datetime'] = timezone.make_aware(dt)
                            else:
                                m['match_datetime'] = timezone.now()
                        except:
                            m['match_datetime'] = timezone.now()

                        match_identifier = f"{m['home_team']}_{m['away_team']}_{m['match_datetime'].strftime('%Y%m%d')}"
                        current_match_identifiers.add(match_identifier)

                        processed_data.append(m)

                    saved_count = await bulk_save_scraped_data(processed_data)
                    await log(f"   💾 Saved/Updated {saved_count} matches to DB.")

                    now = timezone.now()
                    time_since_last_cleanup = (now - last_cleanup_time).total_seconds()

                    if time_since_last_cleanup > 1800:
                        await self.cleanup_old_matches(current_match_identifiers, log)
                        last_cleanup_time = now
                    elif len(scraped_data) > 0 and len(processed_data) > 0:
                        await self.check_and_cleanup_matches(processed_data, log)

                else:
                    await log("   ⚠️ No matches found on page.")

                heartbeat += 1
                if heartbeat >= 6:
                    await log("   💓 Monitor active...")
                    heartbeat = 0

                await asyncio.sleep(5)

        except Exception as e:
            await log(f"   ❌ Error monitoring main list: {e}")

    async def monitor_live_page_persistent(self, status_check_callback=None, log_callback=None):
        # Internal imports for maximum stability
        from decimal import Decimal, InvalidOperation

        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)

        await log("🚀 Starting persistent live monitor (Deep Debug Mode)...")
        url = "https://gh7.bet/live/201"

        try:
            if not self.page:
                await self.setup_driver()

            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            from matches.models import Match

            @sync_to_async
            def get_db_live_identifiers():
                identifiers = set()
                active_matches = Match.objects.filter(status='live').values_list('match_url', 'home_team__name',
                                                                                 'away_team__name')
                for match_url, home_name, away_name in active_matches:
                    if match_url:
                        identifiers.add(match_url)
                    else:
                        identifiers.add(f"{home_name.strip().lower()}|{away_name.strip().lower()}")
                return identifiers

            while True:
                if status_check_callback and not await status_check_callback():
                    break

                try:
                    db_live_identifiers = await get_db_live_identifiers()
                    current_identifiers = set()

                    scraped_data = await self.page.evaluate("""() => {
                                            const extractedMatches = [];
                                            const leagues = document.querySelectorAll('.accordion.league-wrap, .league-wrap');

                                            // ADDED leagueIndex to track the exact order on the page
                                            leagues.forEach((league, leagueIndex) => {
                                                const leagueName = league.querySelector('.icon-title__text')?.innerText.trim() || "Unknown";
                                                const events = league.querySelectorAll('.event');

                                                events.forEach(event => {
                                                    // --- TEAMS AND LOGOS ---
                                                    const oppsContainer = event.querySelector('.opps__container');
                                                    let homeTeam = "", awayTeam = "", homeLogo = null, awayLogo = null;

                                                    const getImgUrl = (el) => {
                                                        if (!el) return null;
                                                        const style = window.getComputedStyle(el).backgroundImage;
                                                        if (!style || style === 'none') return null;
                                                        let cleanUrl = style.replace(/url\\(['"]?(.*?)['"]?\\)/i, '$1').replace(/['"]/g, '').trim();
                                                        if (cleanUrl.startsWith('/')) cleanUrl = window.location.origin + cleanUrl;
                                                        return cleanUrl;
                                                    };

                                                    if (oppsContainer) {
                                                        const teamTitles = oppsContainer.querySelectorAll('.icon-title');
                                                        if (teamTitles.length >= 2) {
                                                            homeTeam = teamTitles[0].querySelector('.icon-title__text')?.innerText.trim() || "";
                                                            homeLogo = getImgUrl(teamTitles[0].querySelector('.icon-title__icon'));
                                                            awayTeam = teamTitles[1].querySelector('.icon-title__text')?.innerText.trim() || "";
                                                            awayLogo = getImgUrl(teamTitles[1].querySelector('.icon-title__icon'));
                                                        }
                                                    }

                                                    // --- MATCH SCORE ---
                                                    let hScore = null, aScore = null;
                                                    const scoreColumns = event.querySelectorAll('.opps__scores .scores__column');
                                                    if (scoreColumns.length > 0) {
                                                        const mainScoreSpans = scoreColumns[0].querySelectorAll('span');
                                                        if (mainScoreSpans.length === 2) {
                                                            const parsedH = parseInt(mainScoreSpans[0].innerText.trim());
                                                            const parsedA = parseInt(mainScoreSpans[1].innerText.trim());
                                                            if (!isNaN(parsedH)) hScore = parsedH;
                                                            if (!isNaN(parsedA)) aScore = parsedA;
                                                        }
                                                    }

                                                    // --- STATUS AND MINUTE ---
                                                    let matchPeriod = "";
                                                    let matchMinute = "";
                                                    let matchStatus = "live";

                                                    const statusLeft = event.querySelector('.status.status--left');
                                                    if (statusLeft) {
                                                        const periodEl = statusLeft.querySelector('.period');
                                                        if (periodEl) matchPeriod = periodEl.innerText.trim();

                                                        const spans = statusLeft.querySelectorAll('span');
                                                        spans.forEach(span => {
                                                            const text = span.innerText.trim();
                                                            if (text.includes("'") || /^\\d+$/.test(text)) {
                                                                matchMinute = text;
                                                            }
                                                        });
                                                    }

                                                    const pLower = matchPeriod.toLowerCase();
                                                    if (pLower.includes('half time') || pLower === 'ht') {
                                                        matchStatus = 'halftime';
                                                    } else if (pLower.includes('finished') || pLower === 'ft' || pLower === 'ended') {
                                                        matchStatus = 'finished';
                                                    }

                                                    // --- ODDS ---
                                                    const getOdd = (btnIndex) => {
                                                        const buttons = event.querySelectorAll('.odds .stake-button');
                                                        const btn = buttons[btnIndex];
                                                        if (!btn || btn.querySelector('.icon-lock')) return null;

                                                        let val = btn.querySelector('.formated-odd')?.innerText.trim();
                                                        if (!val) return null;

                                                        let numValue = parseFloat(val.replace(',', '.')); 
                                                        return isNaN(numValue) ? null : numValue.toString();
                                                    };

                                                    if (homeTeam && awayTeam) {
                                                        extractedMatches.push({
                                                            league_name: leagueName,
                                                            league_order: leagueIndex + 1, // SAVING THE ORDER HERE
                                                            home_team: homeTeam,
                                                            away_team: awayTeam,
                                                            home_logo: homeLogo,
                                                            away_logo: awayLogo,
                                                            home_score: hScore,
                                                            away_score: aScore,
                                                            match_period: matchPeriod,
                                                            match_minute: matchMinute,
                                                            match_status: matchStatus,
                                                            match_url: event.querySelector('a.event__data')?.href || event.querySelector('a')?.href || null,
                                                            home_odds: getOdd(0),
                                                            draw_odds: getOdd(1),
                                                            away_odds: getOdd(2)
                                                        });
                                                    }
                                                });
                                            });
                                            return extractedMatches;
                                        }""")

                    # --- STEP 2: PROCESS & DEEP LOG ---
                    if scraped_data:
                        processed_data = []
                        await log(f"\n--- 🛰️ Scraped {len(scraped_data)} matches. Data details: ---")

                        for m in scraped_data:
                            # Print EVERYTHING for debugging
                           # await log(f"📍 Match: {m['home_team']} vs {m['away_team']}")
                           # await log(f"   📊 Score: {m['home_score']}-{m['away_score']} | League: {m['league_name']}")
                           # await log(f"   📈 Odds: H:{m['home_odds']} D:{m['draw_odds']} A:{m['away_odds']}")
                           # await log(f"   🖼️ Logos: Home({m['home_logo']}) Away({m['away_logo']})")

                            # Identifier logic
                            home_clean = m['home_team'].strip().lower()
                            away_clean = m['away_team'].strip().lower()
                            current_identifiers.add(f"{home_clean}|{away_clean}")
                            if m.get('match_url'): current_identifiers.add(m['match_url'])

                            # CRITICAL: Double-Sanitize for Decimal
                            for key in ['home_odds', 'draw_odds', 'away_odds']:
                                raw_val = m.get(key)
                                if raw_val:
                                    try:
                                        # Convert to float first to strip any weird chars, then to Decimal
                                        clean_float = float(str(raw_val).replace(',', '.'))
                                        m[key] = Decimal(f"{clean_float:.2f}")
                                    except (ValueError, TypeError, InvalidOperation):
                                        await log(
                                            f"   ⚠️ Warning: Could not convert odd '{raw_val}' to Decimal. Setting to None.")
                                        m[key] = None
                                else:
                                    m[key] = None

                            m['scraped_at'] = timezone.now()
                            processed_data.append(m)

                        # --- STEP 3: DB SAVE WITH ERROR CATCHING ---
                        if hasattr(self, 'save_live_matches_structured'):
                            try:
                                # If the error happens HERE, the next line will catch it
                                await self.save_live_matches_structured(processed_data)
                            except Exception as e:
                                await log(f"❌ DATABASE SAVE FAILED: {e}")
                                # This helps see if it's a specific match causing the crash
                                for p_match in processed_data:
                                    if p_match['home_team'] == "Vardar":
                                        await log(f"🔍 DEBUG VARDAR DATA: {p_match}")

                        # --- STEP 4: CLEANUP ---
                        disappeared = db_live_identifiers - current_identifiers
                        for identifier in disappeared:
                            if hasattr(self, 'mark_match_as_finished_by_identifier'):
                                await self.mark_match_as_finished_by_identifier(identifier, log)

                    await asyncio.sleep(10)

                except Exception as e:
                    await log(f"❌ Iteration Error: {e}")
                    await log(traceback.format_exc())
                    await asyncio.sleep(5)

        except Exception as e:
            await log(f"❌ Critical Scraper Error: {e}")
            await log(traceback.format_exc())

    async def mark_match_as_finished_by_identifier(self, identifier, log_callback=None):
        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)

        try:
            from asgiref.sync import sync_to_async
            from matches.models import Match, Bet, ExpressBetSelection
            from django.db import transaction

            @sync_to_async
            def update_match_finished(identifier):
                with transaction.atomic():
                    if identifier.startswith('http'):
                        match_query = Match.objects.filter(match_url=identifier, status='live')
                    else:
                        parts = identifier.split('|')
                        if len(parts) == 2:
                            match_query = Match.objects.filter(
                                home_team__name__iexact=parts[0],
                                away_team__name__iexact=parts[1],
                                status='live'
                            )
                        else:
                            return {'updated': 0, 'bets_count': 0}

                    # Use iterator to handle potential corrupt matches one by one
                    matches = []
                    queryset = match_query.select_for_update().iterator()
                    while True:
                        try:
                            match = next(queryset)
                            matches.append(match)
                        except StopIteration:
                            break
                        except Exception as e:
                            print(f"⚠️ Skipping corrupt match (identifier: {identifier}): {e}")
                            continue

                    if not matches:
                        return {'updated': 0, 'bets_count': 0}

                    total_bets_settled = 0
                    for match in matches:
                        match.status = 'finished'
                        match.save()
                        try:
                            match.settle_bets()
                        except Exception as e:
                            print(f"⚠️ Error settling bets for match {match.id}: {e}")

                        total_bets_settled += match.bets.exclude(status='pending').count()
                        total_bets_settled += ExpressBetSelection.objects.filter(match=match).exclude(status='pending').count()

                    return {'updated': len(matches), 'bets_count': total_bets_settled}

            result = await update_match_finished(identifier)
            if result['updated'] > 0:
                await log(f"   -> 🏁 Finished {result['updated']} match(es) | 💰 Settled {result['bets_count']} bet(s)")
            return result

        except Exception as e:
            await log(f"      ❌ Failed to mark match as finished: {e}")
            return {'updated': 0, 'bets_count': 0}

    async def cleanup_old_live_matches(self, current_identifiers, log=None):
        async def log_msg(msg):
            if log:
                await log(msg)
            else:
                print(msg)
        try:
            await log_msg("   🧹 Cleaning up old live matches...")
            await log_msg("   ✅ Live match cleanup completed.")
        except Exception as e:
            await log_msg(f"   ❌ Error cleaning up live matches: {e}")

    async def check_and_cleanup_live_matches(self, current_matches, log=None):
        async def log_msg(msg):
            if log:
                await log(msg)
            else:
                print(msg)
        try:
            pass
        except Exception as e:
            await log_msg(f"   ❌ Error in live match check/cleanup: {e}")

    async def process_live_structured_data(self, leagues_data, log_callback):
        processed_matches = []
        if not leagues_data or not isinstance(leagues_data, list):
            return processed_matches
        for league in leagues_data:
            if not league or not isinstance(league, dict):
                continue
            league_name = league.get('league', 'Unknown League')
            league_id = league.get('league_id', '')
            events = league.get('events', [])
            if not events:
                continue
            await log_callback(f"   📋 League: {league_name} ({len(events)} matches)")
            for event in events:
                try:
                    event_type = event.get('type', '')
                    if event_type != 'live':
                        continue
                    match_data = {
                        'match_id': event.get('id', ''),
                        'league_name': league_name,
                        'league_id': league_id,
                        'home_team': event.get('opp_1', ''),
                        'away_team': event.get('opp_2', ''),
                        'home_team_id': event.get('opp_1_id', ''),
                        'away_team_id': event.get('opp_2_id', ''),
                        'home_team_icon': event.get('opp_1_icon', ''),
                        'away_team_icon': event.get('opp_2_icon', ''),
                        'status': 'live',
                        'type': event_type,
                        'sr_id': event.get('sr_id', ''),
                        'count_odds': event.get('count_odds', 0)
                    }
                    start_timestamp = event.get('start')
                    if start_timestamp:
                        try:
                            match_data['match_datetime'] = timezone.make_aware(
                                datetime.fromtimestamp(float(start_timestamp))
                            )
                        except:
                            match_data['match_datetime'] = timezone.now()
                    else:
                        match_data['match_datetime'] = timezone.now()
                    stats = event.get('stats', {})
                    if stats:
                        score = stats.get('score', {})
                        if score:
                            match_data['home_score'] = score.get('opp_1')
                            match_data['away_score'] = score.get('opp_2')
                            match_data['score'] = f"{match_data['home_score']}-{match_data['away_score']}"
                        if stats.get('period') == 0 or stats.get('pNow') == 'Finished':
                            match_data['status'] = 'finished'
                    odds_data = event.get('odds', [])
                    if odds_data:
                        for odds_market in odds_data:
                            market_name = odds_market.get('col_n', '')
                            period = odds_market.get('period', 0)
                            if period == 0:
                                if market_name == 'Winner':
                                    od_values = odds_market.get('od', [])
                                    if len(od_values) >= 3:
                                        try:
                                            match_data['home_odds'] = float(od_values[0])
                                            match_data['draw_odds'] = float(od_values[1])
                                            match_data['away_odds'] = float(od_values[2])
                                        except:
                                            match_data['home_odds'] = od_values[0]
                                            match_data['draw_odds'] = od_values[1]
                                            match_data['away_odds'] = od_values[2]
                                elif market_name == 'Double chance':
                                    od_values = odds_market.get('od', [])
                                    if len(od_values) >= 3:
                                        try:
                                            match_data['odds_1x'] = float(od_values[0])
                                            match_data['odds_12'] = float(od_values[1])
                                            match_data['odds_x2'] = float(od_values[2])
                                        except:
                                            match_data['odds_1x'] = od_values[0]
                                            match_data['odds_12'] = od_values[1]
                                            match_data['odds_x2'] = od_values[2]
                    score_display = f" ({match_data.get('score', '?-?')})" if match_data.get('score') else ""
                    status_display = f" [{match_data['status'].upper()}]"
                    await log_callback(
                        f"      ⚽ {match_data['home_team']} vs {match_data['away_team']}{score_display}{status_display}")
                    if match_data.get('home_odds') and match_data.get('away_odds'):
                        await log_callback(
                            f"         📊 Odds: 1: {match_data['home_odds']} | X: {match_data.get('draw_odds', 'N/A')} | 2: {match_data['away_odds']}")
                    processed_matches.append(match_data)
                except Exception as e:
                    await log_callback(f"         ⚠️ Error processing event: {e}")
                    continue
        return processed_matches

    async def save_live_matches_structured(self, matches_data):
        from asgiref.sync import sync_to_async
        from django.utils import timezone

        @sync_to_async
        def _process_matches_synchronously(data_list):
            from django.db import transaction, IntegrityError
            from matches.models import Match, Team, Odds, Bookmaker

            saved_count = 0
            bookmaker, _ = Bookmaker.objects.get_or_create(
                name="GStake",
                defaults={'website': 'https://gh7.bet'}
            )

            for match_data in data_list:
                try:
                    with transaction.atomic():
                        # --- ROBUST TEAM HANDLING ---
                        # We use a try/except block to handle race conditions where
                        # two matches try to create the same new team at once.
                        try:
                            home_team, _ = Team.objects.get_or_create(
                                name=match_data['home_team'],
                                defaults={'logo_url': match_data['home_logo']}
                            )
                        except IntegrityError:
                            home_team = Team.objects.get(name=match_data['home_team'])

                        try:
                            away_team, _ = Team.objects.get_or_create(
                                name=match_data['away_team'],
                                defaults={'logo_url': match_data['away_logo']}
                            )
                        except IntegrityError:
                            away_team = Team.objects.get(name=match_data['away_team'])

                        match_url = match_data.get('match_url')
                        # Check for existing matches in any active state
                        match_query = Match.objects.filter(status__in=['live', 'halftime', 'upcoming'])

                        if match_url:
                            match = match_query.filter(match_url=match_url).first()
                        else:
                            match = match_query.filter(home_team=home_team, away_team=away_team).first()

                        if match:
                            # --- EXISTING MATCH UPDATE ---
                            if match.status in ['live', 'upcoming', 'halftime']:
                                match.status = match_data.get('match_status', 'live')

                            new_h_score = match_data.get('home_score')
                            new_a_score = match_data.get('away_score')

                            # Safe overwrite: Only update score if scraper found valid numbers
                            if new_h_score is not None:
                                match.home_score = new_h_score
                            if new_a_score is not None:
                                match.away_score = new_a_score

                            # Update league ordering and live clock details
                            match.league_order = match_data.get('league_order', 999)
                            if 'match_minute' in match_data:
                                match.match_minute = match_data['match_minute']
                            if 'match_period' in match_data:
                                match.match_period = match_data['match_period']

                            match.home_odds = match_data.get('home_odds')
                            match.draw_odds = match_data.get('draw_odds')
                            match.away_odds = match_data.get('away_odds')
                            match.scraped_at = timezone.now()

                            if 'half_time_home_score' in match_data:
                                match.half_time_home_score = match_data['half_time_home_score']
                                match.half_time_away_score = match_data['half_time_away_score']

                            match.save()
                            saved_count += 1
                        else:
                            # --- NEW MATCH CREATION ---
                            match = Match.objects.create(
                                home_team=home_team,
                                away_team=away_team,
                                match_date=match_data.get('match_datetime', timezone.now()),
                                league=match_data.get('league_name', 'Unknown'),
                                league_order=match_data.get('league_order', 999),
                                status=match_data.get('match_status', 'live'),
                                match_url=match_url,
                                home_score=match_data.get('home_score'),
                                away_score=match_data.get('away_score'),
                                match_minute=match_data.get('match_minute', ''),
                                match_period=match_data.get('match_period', ''),
                                home_odds=match_data.get('home_odds'),
                                draw_odds=match_data.get('draw_odds'),
                                away_odds=match_data.get('away_odds'),
                                scraped_at=timezone.now()
                            )
                            if 'half_time_home_score' in match_data:
                                match.half_time_home_score = match_data['half_time_home_score']
                                match.half_time_away_score = match_data['half_time_away_score']
                                match.save()
                            saved_count += 1

                        # --- ODDS SAVING ---
                        if match_data.get('home_odds') and match_data.get('away_odds'):
                            Odds.objects.update_or_create(
                                match=match,
                                bookmaker=bookmaker,
                                defaults={
                                    'home_odds': match_data.get('home_odds'),
                                    'draw_odds': match_data.get('draw_odds') or 3.0,
                                    'away_odds': match_data.get('away_odds'),
                                }
                            )
                            if match.home_odds and match.away_odds:
                                try:
                                    match.calculate_derived_odds()
                                except Exception as calc_error:
                                    print(
                                        f"Warning: Failed derived odds for {match.home_team} vs {match.away_team}: {calc_error}")

                except Exception as e:
                    print(
                        f"Error saving live match {match_data.get('home_team')} vs {match_data.get('away_team')}: {e}")
                    continue
            return saved_count

        try:
            return await _process_matches_synchronously(matches_data)
        except Exception as e:
            print(f"Error in save_live_matches_structured: {e}")
            return 0

    async def update_finished_matches(self, finished_matches_data, log_callback=None):
        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)

        try:
            from asgiref.sync import sync_to_async
            from django.db import transaction
            from matches.models import Match

            @sync_to_async
            def update_and_settle(match_data):
                with transaction.atomic():
                    matches = Match.objects.filter(
                        home_team__name__iexact=match_data['home_team'],
                        away_team__name__iexact=match_data['away_team'],
                        status__in=['live', 'upcoming', 'halftime']
                    ).order_by('-match_date')
                    if not matches.exists():
                        return 0
                    match = matches.first()
                    try:
                        if match_data.get('home_score') not in [None, '', '-']:
                            match.home_score = int(match_data['home_score'])
                        if match_data.get('away_score') not in [None, '', '-']:
                            match.away_score = int(match_data['away_score'])
                    except (ValueError, TypeError):
                        pass
                    match.status = 'finished'
                    match.save()
                    try:
                        match.settle_bets()
                    except Exception as e:
                        print(f"⚠️ Error settling bets for match {match.id}: {e}")
                    return 1

            settled_count = 0
            for match_data in finished_matches_data:
                print(f"finished match_data: {match_data['home_team']} vs {match_data['away_team']}")
                try:
                    result = await update_and_settle(match_data)
                    if result:
                        settled_count += 1
                        await log(f"   ✅ Settled bets for {match_data['home_team']} vs {match_data['away_team']}")
                except Exception as e:
                    await log(f"   ❌ Failed to settle {match_data['home_team']} vs {match_data['away_team']}: {e}")
            if settled_count:
                await log(f"   🏁 Settled {settled_count} finished matches.")
        except Exception as e:
            await log(f"   ❌ Error in update_finished_matches: {e}")

    async def scrape_match_detail_page(self, match_url):
        try:
            print(f"🔍 Visiting: {match_url}")
            await self.page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            score_text = ""
            try:
                score_el = await self.page.query_selector('.score') or await self.page.query_selector('.match-score')
                if score_el:
                    score_text = (await score_el.inner_text()).strip()
            except:
                pass
            print(f"   📊 Score: {score_text if score_text else 'Not started/No score'}")
            markets_data = {}
            market_containers = await self.page.query_selector_all('.accordion-stake')
            if not market_containers:
                market_containers = await self.page.query_selector_all('.market-group')
            for container in market_containers:
                try:
                    title_el = await container.query_selector('.accordion__header') or await container.query_selector('.market-title')
                    if not title_el:
                        continue
                    market_name = (await title_el.inner_text()).strip()
                    if market_name not in markets_data:
                        markets_data[market_name] = []
                    buttons = await container.query_selector_all('.stake-button')
                    for btn in buttons:
                        name_el = await btn.query_selector('.stake__title')
                        odd_el = await btn.query_selector('.formated-odd')
                        if name_el and odd_el:
                            outcome_name = (await name_el.inner_text()).strip()
                            odd_val = (await odd_el.inner_text()).strip()
                            markets_data[market_name].append(f"{outcome_name}: {odd_val}")
                except Exception:
                    continue
            return markets_data
        except Exception as e:
            print(f"   ❌ Error scraping detail page: {e}")
            return {}

    async def update_specific_matches(self, matches_queryset):
        try:
            print(f"🚀 Starting Detail Update for {len(matches_queryset)} matches...")
            matches_list = []
            async for m in matches_queryset:
                matches_list.append(m)
            for match in tqdm(matches_list, desc="Recalculating Derived Odds", unit="match"):
                await calculate_and_save_derived_odds(match)
            print("✅ Detail update complete (derived odds recalculated).")
            return True
        except Exception as e:
            print(f"💥 Detail update error: {e}")
            return False
        finally:
            pass

    async def update_live_matches(self, matches_queryset):
        try:
            print("🚀 Starting Live Match Monitoring...")
            if not await self.setup_driver():
                return False
            matches_list = []
            async for m in matches_queryset:
                matches_list.append(m)
            for match in matches_list:
                if not match.match_url:
                    continue
                print(f"🔴 Checking Live: {match.home_team} vs {match.away_team}")
                await self.scrape_match_status_score(match)
            print("✅ Live monitoring complete.")
            return True
        except Exception as e:
            print(f"💥 Live monitoring error: {e}")
            return False
        finally:
            await self.cleanup()

    async def scrape_match_status_score(self, match):
        try:
            await self.page.goto(match.match_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            home_score = None
            away_score = None
            status = None
            score_selectors = [
                '.score', '.match-score', '.event__score',
                '.live-score', '.scoreboard', '[class*="score"]'
            ]
            score_text = ""
            for selector in score_selectors:
                try:
                    el = await self.page.query_selector(selector)
                    if el:
                        score_text = (await el.inner_text()).strip()
                        if score_text and (':' in score_text or '-' in score_text):
                            break
                except:
                    continue
            if score_text:
                clean_score = re.sub(r'[^\d:-]', '', score_text)
                parts = re.split(r'[-:]', clean_score)
                if len(parts) >= 2:
                    try:
                        h_s = int(parts[0].strip())
                        a_s = int(parts[1].strip())
                        if 0 <= h_s < 50 and 0 <= a_s < 50:
                            home_score = h_s
                            away_score = a_s
                    except ValueError:
                        pass
            content_text = await self.page.content()
            content_lower = content_text.lower()
            finished_keywords = ["full time", "finished", "ft", "ended", "final result"]
            if any(k in content_lower for k in finished_keywords):
                status = Match.STATUS_FINISHED
            elif home_score is not None:
                status = Match.STATUS_LIVE
            if home_score is not None and away_score is not None:
                await update_match_score_status(match, home_score, away_score, status)
                print(f"   📝 Updated: {home_score} - {away_score} ({status or 'Live'})")
            elif status == Match.STATUS_FINISHED:
                await update_match_status(match, status)
                print(f"   🏁 Match Finished (Score not found/changed)")
        except Exception as e:
            print(f"   ⚠️ Failed to update score: {e}")

    async def scrape_matches(self, reuse_driver=False):
        return await self.scrape_main_list_only()

    async def scrape_main_list_only(self):
        try:
            print("🚀 Starting Main List Scrape (Bulk Mode)...")
            if not await self.setup_driver():
                return False
            await self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
            print("✅ Page loaded")
            await self.wait_for_selector_safe(".accordion.league-wrap", timeout=10000)
            league_containers = await self.query_all(".accordion.league-wrap")
            if not league_containers:
                league_containers = await self.query_all(".league-wrap")
            if not league_containers:
                print("❌ No league containers found.")
                return False
            scraped_data = []
            print("🔍 Parsing page content...")
            for league_container in league_containers:
                try:
                    league_name = "Unknown League"
                    try:
                        title_el = await league_container.query_selector('.icon-title__text')
                        if title_el:
                            league_name = (await title_el.inner_text()).strip() or league_name
                    except Exception:
                        pass
                    match_containers = await league_container.query_selector_all('.event')
                    for match_container in match_containers:
                        try:
                            match_data = {
                                'league_name': league_name,
                                'match_url': None,
                                'match_datetime': timezone.now(),
                                'home_team': None,
                                'away_team': None,
                                'home_logo': None,
                                'away_logo': None,
                                'home_odds': None,
                                'draw_odds': None,
                                'away_odds': None,
                                'markets': []
                            }
                            try:
                                link_el = await match_container.query_selector('a.event__link')
                                if not link_el:
                                    link_el = await match_container.query_selector('a')
                                if link_el:
                                    href = await link_el.get_attribute('href')
                                    if href:
                                        match_data['match_url'] = href if href.startswith('http') else f"https://gh7.bet/{href.lstrip('/')}"
                            except Exception:
                                pass
                            try:
                                time_el = await match_container.query_selector('.time__hours')
                                date_el = await match_container.query_selector('.time__date')
                                match_time = (await time_el.inner_text()).strip() if time_el else ""
                                match_date_str = (await date_el.inner_text()).strip() if date_el else ""
                                if match_time and match_date_str:
                                    match_data['match_datetime'] = self.parse_match_datetime(match_date_str, match_time)
                            except Exception:
                                pass
                            try:
                                team_containers = await match_container.query_selector_all('.opps__container .icon-title')
                                if len(team_containers) >= 2:
                                    ht_el = await team_containers[0].query_selector('.icon-title__text')
                                    match_data['home_team'] = (await ht_el.inner_text()).strip() if ht_el else ""
                                    hl_el = await team_containers[0].query_selector('.icon-title__icon')
                                    if hl_el:
                                        match_data['home_logo'] = await self.extract_logo_url(hl_el)
                                    at_el = await team_containers[1].query_selector('.icon-title__text')
                                    match_data['away_team'] = (await at_el.inner_text()).strip() if at_el else ""
                                    al_el = await team_containers[1].query_selector('.icon-title__icon')
                                    if al_el:
                                        match_data['away_logo'] = await self.extract_logo_url(al_el)
                                else:
                                    team_elements = await match_container.query_selector_all('.icon-title__text')
                                    if len(team_elements) >= 3:
                                        match_data['home_team'] = (await team_elements[1].inner_text()).strip()
                                        match_data['away_team'] = (await team_elements[2].inner_text()).strip()
                            except Exception:
                                continue
                            if not match_data['home_team'] or not match_data['away_team']:
                                continue
                            try:
                                main_odds_container = await match_container.query_selector('.odds')
                                if main_odds_container:
                                    stake_buttons = await main_odds_container.query_selector_all('.stake-button')
                                    if len(stake_buttons) >= 3:
                                        h_text = await stake_buttons[0].query_selector('.formated-odd')
                                        d_text = await stake_buttons[1].query_selector('.formated-odd')
                                        a_text = await stake_buttons[2].query_selector('.formated-odd')
                                        match_data['home_odds'] = self.parse_odds((await h_text.inner_text()) if h_text else "")
                                        match_data['draw_odds'] = self.parse_odds((await d_text.inner_text()) if d_text else "")
                                        match_data['away_odds'] = self.parse_odds((await a_text.inner_text()) if a_text else "")
                            except Exception:
                                pass
                            accordions = await match_container.query_selector_all('.accordion-stake')
                            for accordion in accordions:
                                header = await accordion.query_selector('.accordion__header')
                                if not header:
                                    continue
                                market_name = (await header.inner_text()).strip()
                                market_data = {'name': market_name, 'outcomes': []}
                                stake_buttons = await accordion.query_selector_all('.stake-button')
                                for button in stake_buttons:
                                    title_el = await button.query_selector('.stake__title')
                                    odd_el = await button.query_selector('.formated-odd')
                                    if title_el and odd_el:
                                        outcome_name = (await title_el.inner_text()).strip()
                                        odd_value_text = (await odd_el.inner_text()).strip()
                                        odd_value = self.parse_odds(odd_value_text)
                                        if odd_value:
                                            market_data['outcomes'].append({'name': outcome_name, 'odds': odd_value})
                                if market_data['outcomes']:
                                    match_data['markets'].append(market_data)
                            scraped_data.append(match_data)
                            print(f"⚽ Found: {match_data['home_team']} vs {match_data['away_team']}")
                        except Exception as e:
                            print(f"⚠️ Error parsing match: {e}")
                            continue
                except Exception as e:
                    print(f"⚠️ Error parsing league: {e}")
                    continue
            print(f"💾 Saving {len(scraped_data)} matches to database...")
            await bulk_save_scraped_data(scraped_data)
            print(f"✅ Main list scrape complete.")
            return True
        except Exception as e:
            print(f"💥 Main list scrape error: {e}")
            return False
        finally:
            await self.cleanup()

    async def cleanup_old_matches(self, current_match_identifiers, log_callback=None):
        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)
        try:
            from django.db import transaction
            from matches.models import Match
            from django.utils import timezone
            await log("   🧹 Checking for old matches to clean up...")
            upcoming_matches = Match.objects.filter(
                status='upcoming',
                match_date__gte=timezone.now()
            ).select_related('home_team', 'away_team')
            matches_to_remove = []
            for match in upcoming_matches:
                match_identifier = f"{match.home_team.name}_{match.away_team.name}_{match.match_date.strftime('%Y%m%d')}"
                if match_identifier not in current_match_identifiers:
                    matches_to_remove.append(match.id)
            if matches_to_remove:
                await log(f"   🗑️  Found {len(matches_to_remove)} old matches to remove")
                batch_size = 50
                for i in range(0, len(matches_to_remove), batch_size):
                    batch = matches_to_remove[i:i + batch_size]
                    with transaction.atomic():
                        deleted_count, _ = Match.objects.filter(id__in=batch).delete()
                        await log(f"      Removed batch of {deleted_count} old matches")
                await log(f"   ✅ Total removed: {len(matches_to_remove)} old matches")
            else:
                await log("   ✅ No old matches to remove")
            return len(matches_to_remove)
        except Exception as e:
            await log(f"   ❌ Error cleaning up old matches: {e}")
            return 0

    async def check_and_cleanup_matches(self, current_matches_data, log_callback=None):
        from asgiref.sync import sync_to_async

        async def log(msg):
            if log_callback:
                await log_callback(msg)
            else:
                print(msg)

        @sync_to_async
        def cleanup_sync(matches_data):
            from django.db import transaction
            from matches.models import Match
            from django.utils import timezone
            from datetime import timedelta
            try:
                if not matches_data:
                    return 0
                db_matches = Match.objects.filter(
                    status='upcoming',
                    match_date__gte=timezone.now() - timedelta(days=1)
                ).select_related('home_team', 'away_team')
                current_identifiers = set()
                for match_data in matches_data:
                    identifier = f"{match_data['home_team']}_{match_data['away_team']}_{match_data['match_datetime'].strftime('%Y%m%d')}"
                    current_identifiers.add(identifier)
                matches_to_remove = []
                for match in db_matches:
                    db_identifier = f"{match.home_team.name}_{match.away_team.name}_{match.match_date.strftime('%Y%m%d')}"
                    if db_identifier not in current_identifiers:
                        time_until_match = (match.match_date - timezone.now()).total_seconds()
                        if time_until_match > 3600:
                            matches_to_remove.append(match.id)
                if matches_to_remove:
                    with transaction.atomic():
                        deleted_count, _ = Match.objects.filter(id__in=matches_to_remove).delete()
                        return deleted_count
                return 0
            except Exception as e:
                print(f"Error in cleanup_sync: {e}")
                return 0

        try:
            await log("   🔍 Checking for missing matches to clean up...")
            deleted_count = await cleanup_sync(current_matches_data)
            if deleted_count > 0:
                await log(f"   ✅ Removed {deleted_count} missing matches")
            else:
                await log("   ✅ No missing matches to remove")
        except Exception as e:
            await log(f"   ⚠️ Error checking for missing matches: {e}")


# ------------------------
# DB wrappers (sync_to_async)
# ------------------------

@sync_to_async
def bulk_update_live_data(scraped_data):
    from matches.models import Match, Team

    team_names = set()
    for m in scraped_data:
        team_names.add(m['home_team'])
        team_names.add(m['away_team'])

    teams = {t.name: t for t in Team.objects.filter(name__in=team_names)}

    for m_data in scraped_data:
        home_team = teams.get(m_data['home_team'])
        away_team = teams.get(m_data['away_team'])

        if not home_team or not away_team:
            continue

        # --- UPDATE LOGOS FOR LIVE TEAMS IF MISSING ---
        if m_data.get('home_logo') and home_team.logo_url != m_data.get('home_logo'):
            home_team.logo_url = m_data.get('home_logo')
            home_team.save()

        if m_data.get('away_logo') and away_team.logo_url != m_data.get('away_logo'):
            away_team.logo_url = m_data.get('away_logo')
            away_team.save()

        try:
            match = Match.objects.get(home_team=home_team, away_team=away_team, status=Match.STATUS_LIVE)
            match.home_score = m_data.get('home_score')
            match.away_score = m_data.get('away_score')

            # Update league logo if it somehow changed or was missing
            if m_data.get('league_logo') and match.league_logo_url != m_data.get('league_logo'):
                match.league_logo_url = m_data.get('league_logo')

            # Note: I safely used .get() for 'odds' in case a match comes without it
            for odd_name, odd_value in m_data.get('odds', {}).items():
                if odd_value:
                    setattr(match, odd_name, odd_value)

            match.save()

        except Match.DoesNotExist:
            pass
        except Exception as e:
            print(f"Error updating match {m_data['home_team']} vs {m_data['away_team']}: {e}")


@sync_to_async
def bulk_save_scraped_data(matches_data):
    try:
        from django.db import transaction
        from matches.models import Match, Team, Odds, Bookmaker
        from django.utils import timezone
        from datetime import timedelta

        if not matches_data:
            return 0

        saved_count = 0

        # 1. ONE TRANSACTION TO RULE THEM ALL
        # This prevents the database from locking up the rest of your website
        with transaction.atomic():
            bookmaker, _ = Bookmaker.objects.get_or_create(
                name="GStake",
                defaults={'website': 'https://gh7.bet'}
            )

            # 2. BULK FETCH AND CREATE TEAMS
            # Extract all unique team names from the scraped data
            team_names = set()
            for m in matches_data:
                team_names.add(m['home_team'])
                team_names.add(m['away_team'])

            # Fetch all existing teams in one single query
            existing_teams = {t.name: t for t in Team.objects.filter(name__in=team_names)}

            # Find and create missing teams in bulk
            missing_teams = [Team(name=name) for name in team_names if name not in existing_teams]
            if missing_teams:
                Team.objects.bulk_create(missing_teams, ignore_conflicts=True)
                # Re-fetch to guarantee we have their database IDs
                existing_teams = {t.name: t for t in Team.objects.filter(name__in=team_names)}

            # Optional: Bulk update team logos if they changed
            teams_to_update = []
            for m in matches_data:
                h_team = existing_teams.get(m['home_team'])
                a_team = existing_teams.get(m['away_team'])

                if h_team and m.get('home_logo') and h_team.logo_url != m.get('home_logo'):
                    h_team.logo_url = m.get('home_logo')
                    teams_to_update.append(h_team)

                if a_team and m.get('away_logo') and a_team.logo_url != m.get('away_logo'):
                    a_team.logo_url = m.get('away_logo')
                    teams_to_update.append(a_team)

            if teams_to_update:
                Team.objects.bulk_update(set(teams_to_update), ['logo_url'])

            # 3. PROCESS MATCHES
            matches_to_update = []

            # Fetch existing upcoming matches in a dictionary to avoid N+1 queries
            time_threshold_low = timezone.now() - timedelta(hours=24)
            time_threshold_high = timezone.now() + timedelta(days=14)

            db_matches = Match.objects.filter(
                status='upcoming',
                match_date__range=(time_threshold_low, time_threshold_high)
            ).select_related('home_team', 'away_team')

            # Create a lookup key: "HomeTeam_AwayTeam"
            match_map = {f"{m.home_team.name}_{m.away_team.name}": m for m in db_matches}

            for match_data in matches_data:
                h_team = existing_teams.get(match_data['home_team'])
                a_team = existing_teams.get(match_data['away_team'])

                if not h_team or not a_team:
                    continue

                match_key = f"{h_team.name}_{a_team.name}"
                existing_match = match_map.get(match_key)

                match_date = match_data['match_datetime']

                if existing_match:
                    # PREPARE FOR BULK UPDATE
                    existing_match.home_odds = match_data.get('home_odds')
                    existing_match.draw_odds = match_data.get('draw_odds')
                    existing_match.away_odds = match_data.get('away_odds')
                    existing_match.match_url = match_data.get('match_url', existing_match.match_url)
                    existing_match.scraped_at = timezone.now()

                    if match_data.get('league_logo') and existing_match.league_logo_url != match_data.get(
                            'league_logo'):
                        existing_match.league_logo_url = match_data.get('league_logo')

                    # Calculate derived odds in memory before saving
                    if existing_match.home_odds and existing_match.away_odds:
                        try:
                            existing_match.calculate_derived_odds()
                        except Exception:
                            pass

                    matches_to_update.append(existing_match)
                    saved_count += 1

                    # Update Odds model (Keeping this simple as bulk_upsert on related models gets complex)
                    if match_data.get('home_odds') and match_data.get('away_odds'):
                        Odds.objects.update_or_create(
                            match=existing_match,
                            bookmaker=bookmaker,
                            defaults={
                                'home_odds': match_data.get('home_odds'),
                                'draw_odds': match_data.get('draw_odds', 3.0),
                                'away_odds': match_data.get('away_odds'),
                            }
                        )

                else:
                    # STANDARD CREATE
                    if match_date > timezone.now():
                        new_match = Match.objects.create(
                            home_team=h_team,
                            away_team=a_team,
                            match_date=match_date,
                            league=match_data.get('league_name', 'Unknown'),
                            league_logo_url=match_data.get('league_logo'),
                            match_url=match_data.get('match_url'),
                            home_odds=match_data.get('home_odds'),
                            draw_odds=match_data.get('draw_odds'),
                            away_odds=match_data.get('away_odds'),
                            scraped_at=timezone.now(),
                            status='upcoming'
                        )
                        saved_count += 1

                        if match_data.get('home_odds') and match_data.get('away_odds'):
                            Odds.objects.create(
                                match=new_match,
                                bookmaker=bookmaker,
                                home_odds=match_data.get('home_odds'),
                                draw_odds=match_data.get('draw_odds', 3.0),
                                away_odds=match_data.get('away_odds')
                            )
                            try:
                                new_match.calculate_derived_odds()
                                new_match.save()  # Save the derived odds
                            except Exception:
                                pass

            # 4. EXECUTE BULK UPDATE
            if matches_to_update:
                Match.objects.bulk_update(
                    matches_to_update,
                    ['home_odds', 'draw_odds', 'away_odds', 'match_url', 'scraped_at', 'league_logo_url']
                )

        return saved_count

    except Exception as e:
        print(f"Error in bulk_save_scraped_data: {e}")
        return 0

@sync_to_async
def calculate_and_save_derived_odds(match_obj):
    match_obj.calculate_derived_odds()

@sync_to_async
def update_match_score_status(match, home_score, away_score, status=None):
    try:
        match.home_score = int(home_score)
        match.away_score = int(away_score)
        if status:
            match.status = status
        match.save()
    except (ValueError, TypeError):
        pass

@sync_to_async
def update_match_status(match, status):
    match.status = status
    match.save()