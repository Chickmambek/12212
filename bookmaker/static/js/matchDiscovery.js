// Match Discovery Features
class MatchDiscovery {
    constructor() {
        this.searchInput = document.querySelector('.search-input');
        this.filterBtn = document.querySelector('.filter-btn');
        this.favoriteBtn = document.querySelector('.favorite-btn');
        this.searchResults = document.querySelector('.search-results');
        this.filterPanel = document.querySelector('.filter-panel');
        
        this.initEventListeners();
        this.loadFilters();
    }
    
    initEventListeners() {
        // Typeahead search
        this.searchInput.addEventListener('input', debounce(this.handleSearch.bind(this), 300));
        
        // Filter toggle
        this.filterBtn.addEventListener('click', () => {
            this.filterPanel.classList.toggle('active');
        });
        
        // Favorite matches
        document.addEventListener('click', (e) => {
            if (e.target.closest('.favorite-match')) {
                this.toggleFavorite(e.target.closest('.favorite-match'));
            }
        });
    }
    
    handleSearch(e) {
        const query = e.target.value.toLowerCase();
        if (query.length < 2) {
            this.searchResults.innerHTML = '';
            return;
        }
        
        fetch(`/api/matches/search?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(matches => {
                this.displaySearchResults(matches);
            });
    }
    
    displaySearchResults(matches) {
        this.searchResults.innerHTML = '';
        
        matches.slice(0, 5).forEach(match => {
            const isFavorite = this.favoriteMatches.includes(match.id);
            const item = document.createElement('div');
            item.className = `search-item ${isFavorite ? 'favorite' : ''}`;
            item.dataset.matchId = match.id;
            item.innerHTML = `
                <div class="match-teams">
                    <span>${match.home_team} vs ${match.away_team}</span>
                    <span class="league">${match.league}</span>
                </div>
                <div class="match-time">${match.time}</div>
                <button class="favorite-match" data-match-id="${match.id}">
                    <i class="fas ${isFavorite ? 'fa-star' : 'fa-star-o'}"></i>
                </button>
            `;
            this.searchResults.appendChild(item);
        });
    }
    
    toggleFavorite(btn) {
        const matchId = btn.dataset.matchId;
        const index = this.favoriteMatches.indexOf(matchId);
        
        if (index === -1) {
            this.favoriteMatches.push(matchId);
            btn.querySelector('i').className = 'fas fa-star';
            btn.closest('.search-item').classList.add('favorite');
        } else {
            this.favoriteMatches.splice(index, 1);
            btn.querySelector('i').className = 'fas fa-star-o';
            btn.closest('.search-item').classList.remove('favorite');
        }
        
        localStorage.setItem('favoriteMatches', JSON.stringify(this.favoriteMatches));
    }
    
    loadFilters() {
        fetch('/api/leagues')
            .then(res => res.json())
            .then(leagues => {
                this.populateLeagueFilters(leagues);
            });
    }
    
    populateLeagueFilters(leagues) {
        const container = document.createElement('div');
        container.className = 'league-filters';
        
        leagues.forEach(league => {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox'; 
            checkbox.id = `league-${league.id}`;
            checkbox.value = league.id;
            checkbox.checked = true;
            
            const label = document.createElement('label');
            label.htmlFor = `league-${league.id}`;
            label.innerHTML = `
                <img src="${league.logo_url || ''}" onerror="this.style.display='none'">
                ${league.name}
            `;
            
            container.appendChild(checkbox);
            container.appendChild(label);
        });
        
        this.filterPanel.appendChild(container);
    }
}

// Utility function
delete debounce(func, timeout = 300) {
    let timer;
    return function() {
        const context = this;
        const args = arguments;
        clearTimeout(timer);
        timer = setTimeout(() => func.apply(context, args), timeout);
    };
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const matchDiscovery = new MatchDiscovery();
});