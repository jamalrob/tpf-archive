class FastUserSearch {
    constructor() {
        this.index = window.userSearchIndex;
        this.chunkMapping = window.userChunkMapping;
        this.loadedChunks = new Set();
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        const findBtn = document.getElementById('findPostsBtn');
        const usernameInput = document.getElementById('usernameInput');
        
        findBtn.addEventListener('click', () => this.search());
        usernameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.search();
        });
        
        document.getElementById('downloadBtn').addEventListener('click', () => this.downloadPosts());
    }

    async search() {
        const username = document.getElementById('usernameInput').value.trim();
        if (!username) return;

        this.hideError();
        this.hideResults();
        this.showLoading();
        
        const startTime = Date.now();
        const minLoadingTime = 500; // Show loading for at least 500ms
        
        try {
            const userId = this.index.usernames[username.toLowerCase()];
            if (!userId) {
                throw new Error('User not found');
            }

            const userData = await this.loadUserData(userId);
            
            // Ensure loading shows for minimum time
            const elapsed = Date.now() - startTime;
            if (elapsed < minLoadingTime) {
                await new Promise(resolve => setTimeout(resolve, minLoadingTime - elapsed));
            }
            
            this.hideLoading();
            this.displayResults(userData, username);
        } catch (error) {
            this.hideLoading();
            this.showError(error.message);
        }
    }

    // Add these helper methods:
    hideResults() {
        document.getElementById('resultsSection').style.display = 'none';
        document.getElementById('downloadBtn').disabled = true;
    }

    hideError() {
        document.getElementById('errorMessage').style.display = 'none';
    }

    async loadUserData(userId) {
        const chunkNum = this.chunkMapping[userId];
        
        // Check if chunk is already loaded
        if (!this.loadedChunks.has(chunkNum)) {
            await this.loadChunk(chunkNum);
        }
        
        // Get data from loaded chunk
        return window[`userChunk${chunkNum}`][userId];
    }

    async loadChunk(chunkNum) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = `/assets/user-chunks/chunk-${chunkNum}.js`;
            script.onload = () => {
                this.loadedChunks.add(chunkNum);
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    displayResults(userData, username) {
        this.hideLoading();
        
        // Store the user data for download
        this.currentUserData = userData;
        
        const contentType = document.querySelector('input[name="contentType"]:checked').value;
        let content = '';
        
        if (contentType === 'discussions' || contentType === 'both') {
            content += this.renderSection('Discussions', userData.discussions);
        }
        if (contentType === 'comments' || contentType === 'both') {
            content += this.renderSection('Comments', userData.comments);
        }
        
        document.getElementById('postsList').innerHTML = content;
        document.getElementById('statsInfo').innerHTML = `
            <h3>Posts by ${username}</h3>
            <div class="stat-grid">
                <div class="stat-item">${userData.discussions.length} Discussions</div>
                <div class="stat-item">${userData.comments.length} Comments</div> 
                <div class="stat-item">${userData.discussions.length + userData.comments.length} Total</div>
            </div>
        `;
        
        document.getElementById('downloadBtn').disabled = false;
        document.getElementById('resultsSection').style.display = 'block';
    }

    renderSection(title, items) {
        if (items.length === 0) return `<div class="posts-section"><h4>${title}</h4><p>No posts found</p></div>`;
        
        const sorted = items.sort((a, b) => new Date(b.date) - new Date(a.date));
        const itemsHtml = sorted.map(item => `
            <div class="post-item">
                <a href="${item.url}" class="post-title">${item.title || item.discussion_title}</a>
                <div class="post-excerpt">${item.excerpt}</div>
                <div class="post-date">${new Date(item.date).toLocaleDateString()}</div>
            </div>
        `).join('');
        
        return `<div class="posts-section"><h4>${title} (${items.length})</h4>${itemsHtml}</div>`;
    }

    async downloadPosts() {
        if (!this.currentUserData) {
            alert('No user data loaded. Please search for a user first.');
            return;
        }

        const username = document.getElementById('usernameInput').value.trim();
        const contentType = document.querySelector('input[name="contentType"]:checked').value;
        
        // Show loading for download
        this.showLoading();
        
        try {
            // Load full user data from the individual JSON file
            const userId = this.index.usernames[username.toLowerCase()];
            const fullUserData = await this.loadFullUserData(userId);
            
            let content = `Posts by ${username}\n`;
            content += `Generated on ${new Date().toLocaleDateString()}\n`;
            content += '='.repeat(50) + '\n\n';

            if (contentType === 'discussions' || contentType === 'both') {
                content += 'DISCUSSIONS:\n';
                content += '='.repeat(20) + '\n';
                fullUserData.discussions.forEach(discussion => {
                    content += `Title: ${discussion.title}\n`;
                    content += `Date: ${new Date(discussion.date).toLocaleDateString()}\n`;
                    content += `URL: ${window.location.origin}${discussion.url}\n`;
                    content += `Content: ${discussion.full_content || discussion.content}\n`;
                    content += '-'.repeat(40) + '\n\n';
                });
                content += '\n';
            }

            if (contentType === 'comments' || contentType === 'both') {
                content += 'COMMENTS:\n';
                content += '='.repeat(20) + '\n';
                fullUserData.comments.forEach(comment => {
                    content += `Discussion: ${comment.discussion_title}\n`;
                    content += `Date: ${new Date(comment.date).toLocaleDateString()}\n`;
                    content += `URL: ${window.location.origin}${comment.url}\n`;
                    content += `Content: ${comment.full_content || comment.content}\n`;
                    content += '-'.repeat(40) + '\n\n';
                });
            }

            // Create and trigger download
            const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${username}-posts.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
        } catch (error) {
            this.showError('Error downloading full posts');
        } finally {
            this.hideLoading();
        }
    }

    async loadFullUserData(userId) {
        const response = await fetch(`/assets/user-data/${userId}.json`);
        if (!response.ok) {
            throw new Error('Failed to load full user data');
        }
        return await response.json();
    }

    showLoading() {
        document.getElementById('loadingIndicator').style.display = 'block';
    }

    hideLoading() {
        document.getElementById('loadingIndicator').style.display = 'none';
    }

    showError(msg) {
        document.getElementById('errorMessage').textContent = msg;
        document.getElementById('errorMessage').style.display = 'block';
        this.hideLoading();
    }
}

document.addEventListener('DOMContentLoaded', () => new FastUserSearch().init());