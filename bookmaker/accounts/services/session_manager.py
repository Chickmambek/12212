import asyncio
import datetime
import os
import random
import re
import time
import json
import pproxy
from decimal import Decimal, InvalidOperation
from typing import Tuple, Dict, Optional

from datetime import datetime

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from playwright.async_api import async_playwright, BrowserContext, Page
import aiohttp  # Add this import
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Tuple, Dict

# Import your custom modules
from .webDriver import HumanBehavior, FingerprintManager

# Try to import stealth, fallback gracefully if not available
try:
    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


    async def stealth_async(page):
        print("⚠️ playwright-stealth not installed – skipping stealth")

from ..models import OneWinSession, CardTransaction, Profile


class OneWinSessionManager:
    """
    Manages persistent Chromium sessions for 1Win accounts using ONLY Playwright.
    Full state persistence (cookies, storage, scroll, forms) via database JSONField.
    """

    def __init__(self):
        # Active in‑memory sessions: key = f"session_{session.id}"
        self.active_sessions = {}

    # ----------------------------------------------------------------------
    # PROXY CONFIGURATION
    # ----------------------------------------------------------------------
    def _clear_profile_lock(self, profile_path: str):
        """Forcefully remove Chromium lock files that prevent re-launching."""
        lock_files = [
            'SingletonLock',
            'SingletonCookie',
            'SingletonSocket'
        ]
        for lock_file in lock_files:
            full_path = os.path.join(profile_path, lock_file)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    print(f"🔓 Released profile lock: {lock_file}")
                except Exception as e:
                    print(f"⚠️ Could not remove {lock_file}: {e}")


    async def _get_proxy_config(self, session_id: int) -> Optional[Dict]:
        """Build Playwright proxy dict from the account's proxy."""

        def get_config():
            try:
                s = OneWinSession.objects.select_related('account__proxy').get(id=session_id)
                proxy = s.account.proxy
                if not proxy or not proxy.is_active:
                    return None

                ip = proxy.ip.strip()
                port = proxy.port
                username = proxy.username.strip() if proxy.username else None
                password = proxy.password.strip() if proxy.password else None
                proxy_type = proxy.type.lower()

                config = {'bypass': 'localhost,127.0.0.1'}

                if proxy_type in ('http', 'https'):
                    config['server'] = f"{proxy_type}://{ip}:{port}"
                    if username and password:
                        config['username'] = username
                        config['password'] = password
                elif proxy_type == 'socks5':
                    config['server'] = f"socks5://{ip}:{port}"
                else:
                    return None

                return config
            except Exception as e:
                print(f"Error in proxy config: {e}")
                return None

        return await sync_to_async(get_config)()

    # ----------------------------------------------------------------------
    # BROWSER LIVENESS & CLEANUP
    # ----------------------------------------------------------------------
    async def _is_browser_alive(self, session_data: Dict) -> bool:
        """Check if the Playwright page is still responsive."""
        try:
            page = session_data.get('page')
            if not page or page.is_closed():
                return False
            await page.evaluate("1", timeout=2000)
            return True
        except Exception:
            return False

    async def _cleanup_session_data(self, session_key: str):
        data = self.active_sessions.get(session_key)
        if not data:
            return

        print(f"🧹 Force cleaning session: {session_key}")

        try:
            # 1. Try to close the context/browser first
            browser = data.get('browser')
            if browser:
                # We use a shorter timeout to avoid hanging the loop
                await asyncio.wait_for(browser.close(), timeout=5.0)
        except Exception as e:
            # Ignore 'NoneType' or 'Event loop closed' errors here
            pass

        try:
            # 2. Stop the Playwright engine - THIS is what kills the process
            pw = data.get('playwright')
            if pw:
                await asyncio.wait_for(pw.stop(), timeout=5.0)
                print(f"🛑 Playwright engine stopped for {session_key}")
        except Exception as e:
            # If the loop is closed, we can't do much more anyway
            pass
        finally:
            # 3. Always remove from our local tracking
            self.active_sessions.pop(session_key, None)
    # ----------------------------------------------------------------------
    # STATE PERSISTENCE (database JSONField)
    # ----------------------------------------------------------------------
    async def _save_session_state(self, session, page: Page) -> None:
        """Capture browser state safely with liveness checks."""
        try:
            # 1. Check if the page/context is physically still there
            if not page or page.is_closed():
                print("⚠️ Cannot save: Page is already closed or None.")
                return

            context = page.context

            # 2. Capture cookies with try/except to catch 'NoneType' send errors
            cookies = []
            try:
                cookies = await context.cookies()
            except Exception as e:
                print(f"⚠️ Cookie capture skipped (browser connection closing): {e}")

            # 3. Capture Storage & URL
            storage = {'localStorage': [], 'sessionStorage': []}
            url = session.session_state.get('url') if session.session_state else 'https://1wuswz.com/'

            try:
                url = page.url
                # No 'timeout' argument here; use asyncio.wait_for if you need a timeout
                storage = await page.evaluate("""() => ({
                    localStorage: Object.entries(localStorage || {}),
                    sessionStorage: Object.entries(sessionStorage || {})
                })""")
            except Exception as e:
                print(f"⚠️ Storage capture failed: {e}")

            state = {
                'url': url,
                'cookies': cookies,
                'localStorage': storage.get('localStorage', []),
                'sessionStorage': storage.get('sessionStorage', []),
                'timestamp': time.time()
            }

            session.session_state = state
            session.last_used = timezone.now()

            await sync_to_async(session.save)(update_fields=['session_state', 'last_used'])
            print(f"💾 State successfully pushed to DB for session {session.id}")

        except Exception as e:
            print(f"❌ _save_session_state critical error: {e}")

    async def _restore_session_state(self, session: OneWinSession, context: BrowserContext, page: Page) -> bool:
        """Restore state safely without triggering the auth popup."""
        if not session.session_state:
            print("ℹ️ No saved state to restore")
            return False

        try:
            state = session.session_state
            print(f"🔄 Restoring state from {time.ctime(state.get('timestamp', 0))}")

            # --- STEP 1: AUTH HANDSHAKE (The Secret Sauce) ---
            # We visit a non-target page to 'wake up' the proxy extension auth
            try:
                print("🔍 Establishing Proxy Handshake...")
                await page.goto('https://api.ipify.org', wait_until='commit', timeout=20000)
            except Exception as e:
                print(f"⚠️ Handshake failed, but continuing: {e}")

            # --- STEP 2: RESTORE COOKIES ---
            if state.get('cookies'):
                try:
                    # Sanitize
                    valid_keys = {'name', 'value', 'url', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'}
                    sanitized_cookies = []
                    for c in state['cookies']:
                        clean_cookie = {k: v for k, v in c.items() if k in valid_keys}
                        # Force domain-level security if missing
                        if 'domain' not in clean_cookie and 'url' not in clean_cookie:
                            clean_cookie['url'] = 'https://1wuswz.com/'
                        sanitized_cookies.append(clean_cookie)

                    await context.add_cookies(sanitized_cookies)
                    print(f"🍪 Restored {len(sanitized_cookies)} cookies")
                except Exception as e:
                    print(f"⚠️ Cookie restoration failed: {e}")

            # --- STEP 3: NAVIGATE TO DOMAIN ---
            # We MUST be on the domain to avoid 'Access Denied' for localStorage
            target_url = state.get('url', 'https://1wuswz.com/')
            print(f"🌐 Navigating to {target_url}...")

            try:
                await page.goto(target_url, wait_until='domcontentloaded', timeout=60000)
            except Exception as e:
                print(f"⚠️ Navigation failed: {e}")

            # --- STEP 4: RESTORE STORAGE (After Navigation) ---
            if state.get('localStorage') or state.get('sessionStorage'):
                try:
                    await page.evaluate("""(s) => {
                        localStorage.clear();
                        (s.localStorage || []).forEach(([k, v]) => localStorage.setItem(k, v));
                        sessionStorage.clear();
                        (s.sessionStorage || []).forEach(([k, v]) => sessionStorage.setItem(k, v));
                    }""", state)
                    print("💾 Restored storage data")
                except Exception as e:
                    print(f"⚠️ Storage denied (likely on about:blank): {e}")

            print(f"✅ State restoration complete for session {session.id}")
            return True

        except Exception as e:
            print(f"❌ Failed to restore state: {e}")
            return False

    # ----------------------------------------------------------------------
    # CLOUDFLARE HANDLING (Unified)
    # ----------------------------------------------------------------------
    async def _handle_cloudflare(self, page: Page, max_wait: int = 30) -> bool:
        """Robustly handle Cloudflare challenges with human-like interactions."""
        try:
            content = await page.content()
            url = page.url

            # Explicitly catch the 1015 IP ban
            if "Error 1015" in await page.title() or "Rate limited" in content:
                print("🚫 IP Rate Limited (1015). Must wait or rotate proxy.")
                return False

            patterns = ['cf-browser-verification', 'cloudflare', 'checking your browser', '请稍候']
            is_cf = any(p in content.lower() for p in patterns) or 'cf' in url.lower()

            if is_cf:
                print("☁️ Cloudflare detected, waiting for verification...")
                start_time = asyncio.get_event_loop().time()

                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    await asyncio.sleep(2)
                    current_content = await page.content()
                    current_url = page.url

                    if '1wuswz.com' in current_url and 'cf' not in current_url.lower() and not any(
                            p in current_content.lower() for p in patterns):
                        elapsed = asyncio.get_event_loop().time() - start_time
                        print(f"✅ Cloudflare passed after {elapsed:.1f} seconds")
                        await asyncio.sleep(random.uniform(2, 4))
                        return True

                    # Human-like behavior while waiting
                    try:
                        vp = page.viewport_size
                        if vp and random.random() > 0.6:
                            x = random.randint(100, vp['width'] - 100)
                            y = random.randint(100, vp['height'] - 100)
                            await page.mouse.move(x, y, steps=random.randint(5, 15))

                            if random.random() > 0.8:
                                await page.evaluate(f"window.scrollBy(0, {random.randint(50, 150)})")
                    except:
                        pass

                print("⚠️ Cloudflare timeout")
                return False

            return True

        except Exception as e:
            print(f"⚠️ Error handling Cloudflare: {e}")
            return False

    # ----------------------------------------------------------------------
    # TAB INSPECTOR
    # ----------------------------------------------------------------------
    async def _print_all_pages(self, context: BrowserContext, session_id: int):
        """Log all open tabs and their titles/URLs."""
        try:
            pages = context.pages
            print(f"\n📑 Session {session_id} – {len(pages)} open tab(s):")
            for i, page in enumerate(pages, 1):
                try:
                    url = page.url
                    title = await page.title()
                    print(f"   Tab {i}: {title} – {url}")
                except:
                    print(f"   Tab {i}: <error retrieving page info>")
        except Exception as e:
            pass

    # ----------------------------------------------------------------------
    # MANUAL SESSION (HEADLESS = FALSE)
    # ----------------------------------------------------------------------
    async def open_session_browser(self, session: OneWinSession) -> Tuple[bool, str, Dict]:
        """Open a visible Chromium window with health check and stability fixes."""
        try:
            username = await sync_to_async(lambda: session.account.username)()
            session_id = await sync_to_async(lambda: session.id)()
            session_key = f"session_{session_id}"

            profile_path = await sync_to_async(session.get_or_create_profile_path)()
            self._clear_profile_lock(profile_path)

            print(f"\n🖥️ Opening Chromium for {username}")

            # 1. Extension Setup
            ext_path = self._create_proxy_extension(
                proxy_ip='194.104.238.184',
                proxy_port='63038',
                proxy_user='XYdXiTD9',
                proxy_pass='jhYPnmZn'
            )

            # 2. Optimized Arguments to prevent 30-second stalls
            args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-gpu',
                '--disable-software-rasterizer',
                # --- AGGRESSIVE STABILITY FLAGS ---
                '--disable-dev-shm-usage',  # Prevents crashes in Docker/Linux
                '--disable-features=IsolateOrigins,site-per-process',  # Speeds up proxies
                '--disable-site-isolation-trials',
                '--proxy-bypass-list=localhost,127.0.0.1',
                f'--disable-extensions-except={ext_path}',
                f'--load-extension={ext_path}',
            ]

            playwright = await async_playwright().start()

            # 3. Launch Persistent Context
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                args=args,
                ignore_https_errors=True,
                viewport={'width': random.choice([1366, 1440, 1536]), 'height': 768}
            )

            await asyncio.sleep(2)

            page = context.pages[0] if context.pages else await context.new_page()

            # ---------------------------------------------------------
            # 🛡️ PROXY HEALTH CHECK (Add it right here!)
            # ---------------------------------------------------------
            print("🔍 Verifying Proxy Connection...")
            try:
                # We use a 15-second timeout. If api.ipify.org doesn't load, the proxy is dead.
                await page.goto('https://api.ipify.org', wait_until='load', timeout=15000)
                current_ip = (await page.inner_text('body')).strip()

                if current_ip == '194.104.238.184':
                    print(f"✅ PROXY ACTIVE: {current_ip}")
                else:
                    print(f"⚠️ PROXY FAILED: Showing Real IP ({current_ip})")
                    # Optional: await context.close(); return False, "Proxy not active", {}
            except Exception as e:
                print(f"❌ PROXY TIMEOUT: Internet is not working through this proxy. {e}")
                # This explains your "internet disappeared" issue
            # ---------------------------------------------------------

            if STEALTH_AVAILABLE:
                await stealth_async(page)

            # 4. Inject your database cookies/storage
            await self._restore_session_state(session, context, page)

            # 5. Navigate to Target
            print(f"🌐 Navigating to 1wuswz.com...")
            await page.goto('https://1wuswz.com/', wait_until='domcontentloaded', timeout=90000)

            session.last_used = timezone.now()
            await sync_to_async(session.save)(update_fields=['last_used'])

            async def on_disconnect():
                await self._save_session_state(session, page)

            context.on('close', lambda: asyncio.create_task(on_disconnect()))

            self.active_sessions[session_key] = {
                'browser': context,
                'context': context,
                'page': page,
                'playwright': playwright,
                'session_id': session_id,
            }

            await sync_to_async(session.mark_active)()
            return True, "Browser opened", {'session_id': session_key, 'url': page.url}

        except Exception as e:
            print(f"❌ open_session_browser failed: {e}")
            if 'playwright' in locals():
                try:
                    await playwright.stop()
                except:
                    pass
            return False, str(e), {}

    # ----------------------------------------------------------------------
    # AUTOMATED SESSION (HEADLESS = TRUE)
    # ----------------------------------------------------------------------
    async def _get_or_create_browser_session(self, session: OneWinSession) -> Optional[Dict]:
        """Get existing live session or launch a headless Playwright instance."""
        session_id = await sync_to_async(lambda: session.id)()
        session_key = f"session_{session_id}"

        if session_key in self.active_sessions:
            if await self._is_browser_alive(self.active_sessions[session_key]):
                session.last_used = timezone.now()
                await sync_to_async(session.save)(update_fields=['last_used'])
                return self.active_sessions[session_key]
            else:
                await self._cleanup_session_data(session_key)

        try:
            profile_path = await sync_to_async(lambda: session.profile_path)()
            if not profile_path or not os.path.exists(profile_path):
                profile_path = await sync_to_async(session.get_or_create_profile_path)()
                session.profile_path = profile_path
                await sync_to_async(session.save)(update_fields=['profile_path'])

            ext_path = self._create_proxy_extension(
                proxy_ip='194.104.238.184',
                proxy_port='63038',
                proxy_user='XYdXiTD9',
                proxy_pass='jhYPnmZn'
            )

            args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-gpu',
                '--disable-software-rasterizer',
                # --- CRITICAL PROXY STABILITY FLAGS ---
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-breakpad',
                '--disable-component-update',
                '--disable-domain-reliability',
                '--disable-ipc-flooding-protection',
                '--disable-renderer-backgrounding',
                '--proxy-bypass-list=localhost,127.0.0.1',  # Corrected bypass
                '--disable-dev-shm-usage',
                f'--disable-extensions-except={ext_path}',
                f'--load-extension={ext_path}',
                '--headless=new'
            ]

            playwright = await async_playwright().start()

            # We launch persistent context WITHOUT the proxy argument
            # The extension will handle all routing and auth
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                ignore_https_errors=True,
                args=args,
                viewport={'width': 1366, 'height': 768},
            )
            await asyncio.sleep(2)

            page = context.pages[0] if context.pages else await context.new_page()
            await stealth_async(page)

            # Block heavy resources in headless to save bandwidth
            await page.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,svg,css}", lambda route: route.abort())

            await stealth_async(page)
            print("🕵️ Launched headless Playwright browser")

            await self._restore_session_state(session, context, page)

            session.last_used = timezone.now()
            await sync_to_async(session.save)(update_fields=['last_used'])

            session_data = {
                'browser': context,
                'page': page,
                'playwright': playwright,
                'session_id': session_id,
            }
            self.active_sessions[session_key] = session_data
            return session_data

        except Exception as e:
            print(f"❌ Headless browser launch failed: {e}")
            return None

    def _create_proxy_extension(self, proxy_ip, proxy_port, proxy_user, proxy_pass) -> str:
        extension_dir = os.path.abspath(f"proxy_auth_{proxy_user}")
        os.makedirs(extension_dir, exist_ok=True)

        manifest = {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auth",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest",
                            "webRequestBlocking"],
            "background": {"scripts": ["background.js"]}
        }

        background_js = f"""
                var config = {{
                    mode: "fixed_servers",
                    rules: {{
                        singleProxy: {{
                            scheme: "http",
                            host: "{proxy_ip}",
                            port: parseInt({proxy_port})
                        }},
                        bypassList: ["localhost", "127.0.0.1"]
                    }}
                }};

                // Set the proxy immediately
                chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

                // Handle the authentication popup internally
                chrome.webRequest.onAuthRequired.addListener(
                    function(details) {{
                        return {{
                            authCredentials: {{
                                username: "{proxy_user}",
                                password: "{proxy_pass}"
                            }}
                        }};
                    }},
                    {{urls: ["<all_urls>"]}},
                    ['blocking']
                );

                // EXTRA: Prevent the extension from going idle
                chrome.webRequest.onErrorOccurred.addListener(
                    function(details) {{ console.error("Proxy Error: ", details.error); }},
                    {{urls: ["<all_urls>"]}}
                );
                """
        with open(os.path.join(extension_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f)
        with open(os.path.join(extension_dir, "background.js"), "w") as f:
            f.write(background_js)
        return extension_dir
    # ----------------------------------------------------------------------
    # CLOSE SESSION
    # ----------------------------------------------------------------------
    async def close_session_browser(self, session: OneWinSession) -> bool:
        """Saves state and ensures browser processes are killed."""
        session_id = await sync_to_async(lambda: session.id)()
        session_key = f"session_{session_id}"

        if session_key not in self.active_sessions:
            return False

        data = self.active_sessions[session_key]
        page = data.get('page')

        try:
            # Try to save state only if the loop is still healthy
            if page and not page.is_closed():
                print(f"💾 Saving state for session {session_id}...")
                await self._save_session_state(session, page)
        except Exception as e:
            print(f"⚠️ State save skipped during close: {e}")
        finally:
            # This MUST run to kill the chrome.exe process
            print(f"✅ Session {session_id} resources released.")

        return True

    # ----------------------------------------------------------------------
    # CHECK SESSION STATUS
    # ----------------------------------------------------------------------
    async def check_session_status(self, session: OneWinSession) -> Dict:
        """Quick check if session is logged in."""
        try:
            profile_path = await sync_to_async(lambda: session.profile_path)()
            if not profile_path:
                return {'is_logged_in': False, 'status': 'no_profile'}

            playwright = await async_playwright().start()
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path, headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )

            page = context.pages[0] if context.pages else await context.new_page()
            await stealth_async(page)
            await page.goto('https://1wuswz.com/', wait_until='domcontentloaded', timeout=30000)

            is_logged_in = await self._is_logged_in(page)

            await context.close()
            await playwright.stop()

            if is_logged_in:
                await sync_to_async(session.mark_active)()
            else:
                await sync_to_async(session.mark_needs_login)()

            return {'is_logged_in': is_logged_in, 'status': await sync_to_async(lambda: session.session_status)()}

        except Exception as e:
            return {'is_logged_in': False, 'status': 'error', 'error': str(e)}

    @staticmethod
    async def _is_logged_in(page: Page) -> bool:
        """Heuristic: check for logout button, balance, etc."""
        try:
            content = await page.content()
            lower = content.lower()
            if any(w in lower for w in ['logout', 'выйти', 'balance', 'баланс', 'my account']): return True
            if '/login' in page.url.lower(): return False
            return True
        except:
            return False

    # ----------------------------------------------------------------------
    # DEPOSIT METHODS
    # ----------------------------------------------------------------------
    async def perform_deposit(
            self,
            session: OneWinSession,
            amount: Decimal,
            card_number: str,
            card_tx: CardTransaction,
            user_profile: Profile
    ) -> Tuple[bool, str, Dict]:
        browser_data = None
        try:
            account = await sync_to_async(lambda: session.account)()
            proxy = await sync_to_async(lambda: account.proxy)()

            try:
                user_amount = Decimal(card_tx.amount)
            except (InvalidOperation, TypeError):
                print("❌ Invalid Amount entered")
                return False, "Invalid Amount entered", {}

            # -------------------------------------------------------------
            # 💱 ASYNC CURRENCY CONVERSION TO EUR
            # -------------------------------------------------------------
            # Fallback to 'EUR' if your model doesn't have a currency field yet
            original_currency = getattr(card_tx, 'currency', 'EUR').upper()
            amount_in_eur = user_amount
            exchange_rate = Decimal('1.0')

            if original_currency != 'MDL':
                print(f"🔄 Fetching live exchange rate for {original_currency} to MDL...")
                try:
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.get(f"https://open.er-api.com/v6/latest/{original_currency}",
                                                    timeout=5) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("result") == "success":
                                    rate_to_eur = data['rates']['MDL']
                                    exchange_rate = Decimal(str(rate_to_eur))

                                    # Convert and round to 2 decimal places
                                    amount_in_mdl = (user_amount * exchange_rate).quantize(Decimal('0.01'),
                                                                                           rounding=ROUND_HALF_UP)
                                else:
                                    print(f"⚠️ API error fetching rate for {original_currency}")
                            else:
                                print(f"⚠️ HTTP {response.status} fetching exchange rate.")
                except Exception as e:
                    print(f"⚠️ Currency conversion network error: {e}")

            # -------------------------------------------------------------

            print("\n" + "═" * 60)
            print("📥 DEPOSIT EXECUTION DATA")
            print("═" * 60)
            print(f"🆔 TRANSACTION ID:  #{card_tx.id}")
            print(f"👤 SITE USER:       {user_profile.full_name} (@{user_profile.user.username})")
            print(f"💰 ORIGINAL AMOUNT: {user_amount} {original_currency}")
            if original_currency != 'MDL':
                print(f"💶 DEPOSIT IN MDL:  {amount_in_mdl} MDL (Rate: {exchange_rate})")
            print(f"💳 CARD USED:       {card_tx.card_number} {getattr(card_tx, 'card_type', '')}")
            print(f"🤖 1WIN TARGET:     {session.account.username} (ID: {session.account.id})")

            if session.account.proxy:
                print(f"🌐 VIA PROXY:       {session.account.proxy.ip}:{session.account.proxy.port}")
                print(f"🌍 PROXY COUNTRY:   {session.account.proxy.country}")

            print("═" * 60 + "\n")

            browser_data = await self._get_or_create_browser_session(session)
            if not browser_data:
                return False, "Failed to obtain browser session", {}

            page = browser_data['page']

            # Allow images to load for the screenshot
            try:
                await page.unroute("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,svg,css}")
            except:
                pass

            await asyncio.sleep(random.uniform(2, 5))
            await page.goto('https://1wuswz.com/', wait_until='domcontentloaded')
            await self._handle_cloudflare(page)
            await page.wait_for_timeout(random.uniform(3000, 5000))

            # --- Extract and Print Data to Terminal ---
            print("\n🔍 EXTRACTING ACCOUNT DETAILS FROM PAGE...")
            try:
                view_name = await page.inner_text('.view_name-2qtZk', timeout=5000)
                view_id = await page.inner_text('.view_id-2qtZk', timeout=5000)

                print("----------------------------------------")
                print(f"👤 Account Name: {view_name.strip()}")
                print(f"🆔 Account ID:   {view_id.strip()}")
                print("----------------------------------------\n")
            except Exception as e:
                print(f"⚠️ Could not find account details on page: {e}")

            rounded_amount_in_mdl = (user_amount * exchange_rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

            profile_info = await self._extract_profile_info_with_retry(
                page=page,
                card_tx=card_tx,
                amount_in_mdl=rounded_amount_in_mdl
            )

            payment_link = profile_info.get('payment_link')

            if payment_link:
                print(f"✅ Success! Closing headless session for {account.username}...")

                # --- THE CLOSE & SAVE LOGIC ---
                # 1. Capture the current cookies/storage so we stay logged in
                await self._save_session_state(session, page)

                # 2. Kill the browser process
                await self._cleanup_session_data(f"session_{session.id}")

                return True, "Payment link generated successfully", {
                    'payment_link': payment_link,
                    'account_id': account.id,
                    'amount_in_eur': str(amount_in_eur)
                }
            else:
                filename = f"deposit_{account.id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot_path = os.path.join(settings.MEDIA_ROOT, 'screenshots', filename)
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                await page.screenshot(path=screenshot_path, full_page=True)

                return False, "Screenshot captured", {
                    'account_id': account.id,
                    'profile_name': profile_info.get('profileName'),
                    'profile_id': profile_info.get('profileId'),
                    'screenshot': os.path.join('screenshots', filename),
                    'amount_in_eur': str(amount_in_eur)  # Pass the converted amount back if needed!
                }

        except Exception as e:
            if browser_data: await self._cleanup_session_data(f"session_{session.id}")
            return False, str(e), {}

    async def _extract_profile_info_with_retry(
            self,
            page,
            card_tx,
            amount_in_mdl: Optional[float] = None,
            max_retries: int = 3
    ) -> Dict[str, str]:
        """
        Attempts to perform a deposit and returns the resulting paybase.top payment link.
        Takes a screenshot on timeout for debugging.

        Args:
            page: Playwright page object.
            card_tx: Transaction object with a 'card_type' attribute (Visa/Mastercard).
            amount_in_mdl: Deposit amount in MDL (must be a positive number).
            max_retries: Number of retry attempts.

        Returns:
            Dict with a single key 'payment_link' if successful, otherwise
            raises an exception after max retries.
        """
        if amount_in_mdl is None or amount_in_mdl <= 0:
            raise ValueError("amount_in_mdl must be a positive number")

        # Create screenshots directory if it doesn't exist
        screenshot_dir = "media/screenshots"
        os.makedirs(screenshot_dir, exist_ok=True)

        for attempt in range(1, max_retries + 1):
            try:
                print(f"🔄 Attempt {attempt}/{max_retries}")

                # ---- Step 1: Click main deposit button ----
                deposit_btn = 'button[data-testid="header-balance-deposit-button"]'
                await page.wait_for_selector(deposit_btn, state="visible", timeout=10000)
                await asyncio.sleep(random.uniform(0.5, 1.2))
                await page.click(deposit_btn)
                print("✅ Deposit button clicked")

                # ---- Step 2: Select card type ----
                card_type = getattr(card_tx, 'card_type', 'Unknown').lower()
                if card_type == "visa":
                    selector = 'button[data-testid="payment-method-115-card_visa-caption"]'
                elif card_type == "mastercard":
                    selector = 'button[data-testid="payment-method-116-card_mastercard-caption"]'
                else:
                    selector = 'button[data-testid="payment-method-115-card_visa-caption"]'
                    raise ValueError(f"Unsupported card type: {card_type}")
                print(f'selector: {selector}')
                await page.wait_for_selector(selector, state="visible", timeout=10000)
                await page.click(selector)
                print(f"✅ {card_type.capitalize()} selected")

                # ---- Step 3: Enter amount and submit ----
                amount_input = 'input[data-testid="amount-input"]'
                deposit2_btn = 'button[data-testid="deposit-button"]'

                await page.wait_for_selector(amount_input, state="visible", timeout=10000)
                await page.fill(amount_input, str(amount_in_mdl))

                await page.wait_for_selector(deposit2_btn, state="visible", timeout=10000)
                async with page.context.expect_page() as new_page_info:
                    await page.click(deposit2_btn)
                print("💰 Deposit form submitted")

                new_page = await new_page_info.value
                print("🆕 New tab opened! Waiting for redirects...")

                # ---- Step 4: Wait for redirect to paybase.top ----
                await new_page.wait_for_url(re.compile(r"https://paybase\.top"), timeout=300000)

                # Wait 1 extra second for the page to fully settle (as you requested earlier)
                await asyncio.sleep(1.0)

                payment_link = new_page.url
                print("\n" + "🔗" * 30)
                print(f"✅ PAYBASE PAYMENT LINK OBTAINED:")
                print(payment_link)
                print("🔗" * 30 + "\n")

                # Success – return the result
                return {"payment_link": payment_link}

            except Exception as e:
                error_msg = str(e)
                print(f"❌ Attempt {attempt} failed: {error_msg}")

                # Take a screenshot if it's a timeout error
                if "Timeout" in error_msg and "30000ms" in error_msg:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = os.path.join(
                        screenshot_dir,
                        f"attempt_{attempt}_timeout_{timestamp}.png"
                    )
                    try:
                        await page.screenshot(path=screenshot_path)
                        print(f"📸 Screenshot saved to: {screenshot_path}")
                    except Exception as ss_err:
                        print(f"⚠️ Failed to take screenshot: {ss_err}")

                if attempt == max_retries:
                    raise  # Re-raise after last attempt

                # Reset page state before retry (reload to a clean state)
                print("🔄 Reloading page for next attempt...")
                await page.reload()
                await asyncio.sleep(random.uniform(2, 4))

        # Should never reach here
        return {"payment_link": None}

    async def cleanup_all(self):
        for key in list(self.active_sessions.keys()):
            await self._cleanup_session_data(key)