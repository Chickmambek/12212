// Betting functionality
function placeQuickBet(matchId, betType, odds) {
    return fetch(`/matches/bet/${matchId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-Quick-Bet': 'true',
            'X-Bet-Type': betType,
            'X-Odds': odds
        },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Bet placed successfully!');
            updateBalance(data.new_balance);
        } else {
            showNotification(data.error || 'Failed to place bet', 'error');
        }
        return data;
    });
}

function updateBalance(newBalance) {
    const balanceElements = document.querySelectorAll('.user-balance');
    balanceElements.forEach(el => {
        el.textContent = newBalance.toFixed(2);
    });
}

function setupQuickBetListeners() {
    document.addEventListener('click', (e) => {
        if (e.shiftKey && e.target.closest('.bet-btn')) {
            e.preventDefault();
            const btn = e.target.closest('.bet-btn');
            const matchId = btn.dataset.matchId;
            const betType = btn.dataset.betType;
            const odds = btn.dataset.odds;
            
            placeQuickBet(matchId, betType, odds);
        }
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    setupQuickBetListeners();
});