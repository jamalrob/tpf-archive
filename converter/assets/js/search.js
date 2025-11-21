
    // Simplified search functionality for titles and authors only
    let currentResults = [];

    function getSearchData() {
        if (typeof window.searchData !== 'undefined' && Array.isArray(window.searchData)) {
            return window.searchData;
        } else {
            console.warn('searchData not found, using empty array');
            return [];
        }
    }

    function performSearch() {
        const searchInput = document.getElementById('searchInput');
        const authorFilter = document.getElementById('authorFilter');
        const dateSort = document.getElementById('dateSort');
        
        if (!searchInput || !authorFilter || !dateSort) {
            console.error('Search elements not found');
            return;
        }
        
        const query = searchInput.value.trim().toLowerCase();
        const authorFilterValue = authorFilter.value.trim().toLowerCase();
        const sortBy = dateSort.value;
        
        const resultsContainer = document.getElementById('searchResults');
        const statsContainer = document.getElementById('searchStats');
        
        if (!resultsContainer || !statsContainer) return;
        
        resultsContainer.innerHTML = '';
        statsContainer.innerHTML = '';
        
        if (!query && !authorFilterValue) {
            resultsContainer.innerHTML = '<div class="no-results">Please enter a search term or author name.</div>';
            return;
        }
        
        const searchData = getSearchData();
        if (searchData.length === 0) {
            resultsContainer.innerHTML = '<div class="no-results">Search data not available.</div>';
            return;
        }
        
        const searchTerms = query.split(/\s+/).filter(term => term.length > 0);
        
        // Score and filter results
        currentResults = searchData
            .map(item => {
                const score = calculateRelevanceScore(item, searchTerms, authorFilterValue);
                return { ...item, score };
            })
            .filter(item => {
                // Apply author filter if specified
                if (authorFilterValue && !item.author.toLowerCase().includes(authorFilterValue)) {
                    return false;
                }
                
                return item.score > 0 || authorFilterValue;
            });
        
        // Sort results
        if (sortBy === 'relevance') {
            currentResults.sort((a, b) => b.score - a.score);
        } else if (sortBy === 'newest') {
            currentResults.sort((a, b) => new Date(b.date) - new Date(a.date));
        } else if (sortBy === 'oldest') {
            currentResults.sort((a, b) => new Date(a.date) - new Date(b.date));
        }
        
        // Display results
        if (currentResults.length === 0) {
            resultsContainer.innerHTML = `
                <div class="no-results">
                    <h3>No results found</h3>
                    <p>Try different search terms or adjust your filters.</p>
                </div>`;
            return;
        }
        
        let statsText = `Found ${currentResults.length} discussion${currentResults.length === 1 ? '' : 's'}`;
        if (authorFilterValue) {
            statsText += ` by authors containing "${authorFilterValue}"`;
        }
        statsContainer.innerHTML = statsText;
        
        currentResults.forEach((result, index) => {
            const resultElement = document.createElement('div');
            resultElement.className = 'search-result';
            resultElement.innerHTML = `
                <div>
                    <span class="result-type type-${result.type}">${result.type}</span>
                    <h3><a href="${result.url}">${highlightMatches(result.title, searchTerms)}</a></h3>
                </div>
                <div class="result-meta">
                    By <strong>${highlightMatches(result.author, [authorFilterValue])}</strong> • ${new Date(result.date).toLocaleDateString()}
                    • ${result.comment_count || 0} comments
                </div>
            `;
            resultsContainer.appendChild(resultElement);
        });
    }

    function calculateRelevanceScore(item, searchTerms, authorFilter) {
        let score = 0;
        const title = item.title.toLowerCase();
        const author = item.author.toLowerCase();
        
        // If we're filtering by author, give a base score to all matching items
        if (authorFilter && author.includes(authorFilter)) {
            score += 20; // Base score for author matches
        }
        
        searchTerms.forEach(term => {
            // Title matches are most important
            if (title.includes(term)) {
                score += 10;
            }
            
            // Author matches (additional bonus if also searching by author)
            if (author.includes(term)) {
                score += 8;
            }
            
            // Exact phrase match bonus
            const exactPhrase = searchTerms.join(' ');
            if (title.includes(exactPhrase)) {
                score += 15;
            }
        });
        
        return score;
    }

    function highlightMatches(text, searchTerms) {
        if (!searchTerms || searchTerms.length === 0) return text;
        
        let highlighted = text;
        searchTerms.forEach(term => {
            if (term && term.length > 0) {
                const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                highlighted = highlighted.replace(regex, '<span class="highlighted">$1</span>');
            }
        });
        return highlighted;
    }

    function initializeSearch() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                setupSearch();
            });
        } else {
            setupSearch();
        }
    }

    function setupSearch() {
        const searchButton = document.getElementById('searchButton');
        if (searchButton) {
            searchButton.addEventListener('click', performSearch);
        }
        
        const searchInput = document.getElementById('searchInput');
        const authorFilter = document.getElementById('authorFilter');
        
        if (searchInput) {
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    performSearch();
                }
            });
        }
        
        if (authorFilter) {
            authorFilter.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    performSearch();
                }
            });
        }
    }

    // Initialize search when script loads
    initializeSearch();

    // Make performSearch available globally if needed
    window.performSearch = performSearch;
    