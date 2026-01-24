# XStake Changelog

All notable changes to this project will be documented in this file.

## [v1.1.0] - 2024-05-23 (Infrastructure & Automation)

### Added
- **Background Tasks (Celery)**: Integrated Celery with Redis as a message broker to handle asynchronous tasks.
- **Auto-Settlement**: Implemented a Celery task (`settle_finished_matches`) to automatically settle bets for finished matches without manual intervention.
- **Scraper Optimization**:
    - Added progress bar (`tqdm`) to scraper output.
    - Implemented driver reuse to significantly reduce resource usage during continuous scraping.
    - Added detailed request logging for debugging.
    - Added logic to extract and save match URLs.
    - Added logic to scrape detailed odds (Markets/Outcomes) from individual match pages.
- **Betting Enhancements**:
    - Added "Both Teams To Score" (BTTS) market support.
    - Implemented logic to calculate derived odds (Double Chance, Totals, Handicap, BTTS) if not scraped.
    - Added "Place Bet" button and modal to Match Detail page.
    - Added "My Bets" page with betting history and statistics.
- **Admin Panel Redesign**: Completely overhauled the Django Admin interface with a modern, dark-themed, responsive design.

### Changed
- **Scraper Target**: Updated default scraper URL to `https://gstake.net/line/201`.
- **Payment Logic**: Added automatic cancellation for crypto deposit requests older than 20 minutes.
- **Dashboard**: Added "Live" matches tab and fixed tab switching logic.
- **Balance Page**: Redesigned with a modern grid layout, integrated deposit form, and transaction history.
- **Database**: Reverted to SQLite for simplicity in the current deployment phase (PostgreSQL migration rolled back).

### Security
- **Rate Limiting**: Increased rate limit cache timeout to 30 seconds.
- **Fee Tolerance**: Added 95-105% tolerance check for crypto deposits to account for network fees.

### Deployment Steps (v1.1.0)
1.  **Install Dependencies**: `pip install -r bookmaker/requirements.txt`
2.  **Migrate Database**: `python manage.py migrate`
3.  **Run Redis**: Ensure Redis server is running on `localhost:6379`.
4.  **Start Celery Worker**: `celery -A bookmaker worker -l info`
5.  **Start Celery Beat (Optional)**: `celery -A bookmaker beat -l info` (for scheduled tasks).

---

## [v1.0.0] - 2024-05-22 (MVP Release)

### Added
- **Core Functionality**:
    - User Registration and Login system.
    - Dashboard displaying Live, Today, Upcoming, and Finished matches.
    - Match Detail page with detailed odds and betting interface.
    - "My Bets" page for tracking user betting history.
- **Betting System**:
    - Support for Match Winner (1X2), Double Chance, Total Goals, Handicap, and BTTS markets.
    - Bet Slip modal with stake input and potential return calculation.
    - "Always agree to odds changes" compliance checkbox.
    - Real-time balance deduction upon placing a bet.
- **Crypto Payments**:
    - HD Wallet integration for generating unique deposit addresses (BTC, ETH, USDT, LTC).
    - Real-time deposit monitoring via external APIs (Etherscan, Blockchain.info).
    - Automatic balance crediting upon transaction confirmation.
    - Rate limiting and transaction expiration (20 mins) for security.
- **Scraper**:
    - Automated Playwright-based scraper for `gstake.net`.
    - Fetches match data, live status, and detailed odds (Markets/Outcomes).
    - Calculates derived odds (Double Chance, Totals) if not explicitly scraped.
- **Admin Panel**:
    - Custom dark-themed, responsive admin interface.
    - Management for Matches, Teams, Odds, Markets, and Bets.
    - Bulk actions to mark matches as Live/Finished and settle bets.
- **Notifications**:
    - Telegram bot integration for real-time alerts on:
        - New User Registrations.
        - New Deposit Requests.
        - Confirmed Deposits.
        - Site Visits (Analytics).

### Security
- **Environment Variables**: Sensitive keys (Mnemonic, API Keys) moved to `.env`.
- **Atomic Transactions**: Used `transaction.atomic()` to prevent race conditions in balance updates.
- **Rate Limiting**: Implemented caching-based rate limiting for API endpoints.
- **CSRF Protection**: Enforced CSRF checks on AJAX requests.
- **Input Validation**: Added strict checks for deposit amounts and bet stakes.

### UI/UX
- **Modern Design**: Implemented a consistent dark theme with glassmorphism effects.
- **Responsiveness**: Fully responsive layout for Dashboard, Match Detail, and Balance pages.
- **Interactive Elements**: Used Alpine.js for tab switching, modals, and mobile menus.

---

## [v0.9.0] - 2024-05-21 (Beta)

### Added
- Basic match listing and detail views.
- Initial scraper implementation.
- Simple user profile and balance model.

### Fixed
- Fixed issue with match links redirecting incorrectly.
- Resolved "Invalid language for mnemonic" error in wallet generation.
- Fixed "No odds available" display issue by adding fallback calculations.

---

## [v0.1.0] - 2024-05-20 (Alpha)

### Added
- Project initialization with Django.
- Basic models for Match, Team, and Bookmaker.
- Setup of static files and templates structure.
