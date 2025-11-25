  let currentUserData = null;
  let currentUserId = null;
  let currentUsername = null;
  let currentContentType = 'both';

  // Find user ID by username
  async function findUserIdByUsername(username) {
      try {
          // Load the user lookup data
          if (!window.userLookup) {
              const response = await fetch('/assets/js/user-lookup.js');
              if (response.ok) {
                  // Execute the JavaScript to populate window.userLookup
                  const scriptContent = await response.text();
                  eval(scriptContent);
              } else {
                  console.warn('User lookup file not found');
                  return null;
              }
          }
          
          // Look up the user ID
          const userId = window.userLookup[username.toLowerCase()];
          console.log(`Looking up username "${username}" (lowercase: "${username.toLowerCase()}") -> ${userId}`);
          
          return userId || null;
          
      } catch (error) {
          console.error('Error finding user ID:', error);
          return null;
      }
  }

  // Load user data
  async function loadUserData(userId) {
      try {
          const response = await fetch(`/assets/user-data/${userId}.json`);
          if (!response.ok) throw new Error('User data not found');
          return await response.json();
      } catch (error) {
          console.error('Error loading user data:', error);
          return null;
      }
  }

  // Display posts based on content type
  function displayPosts(userData, contentType = 'both') {
      const postsList = document.getElementById('postsList');
      let posts = [];
      
      if (contentType === 'both') {
          // Combine and sort by date
          posts = [...userData.discussions, ...userData.comments];
          posts.sort((a, b) => new Date(b.date) - new Date(a.date));
      } else if (contentType === 'discussions') {
          posts = userData.discussions;
      } else if (contentType === 'comments') {
          posts = userData.comments;
      }
      
      if (posts.length === 0) {
          let message = 'No posts found.';
          if (contentType === 'discussions') message = 'No discussions found.';
          if (contentType === 'comments') message = 'No comments found.';
          postsList.innerHTML = `<p>${message}</p>`;
          return;
      }
      
      let html = '';
      posts.forEach(post => {
          const postType = post.discussion_title ? 'comment' : 'discussion';
          const typeDisplay = postType === 'discussion' ? 'Discussion' : 'Comment';
          const title = post.title || `Comment in: ${post.discussion_title}`;
          
          html += `
              <div class="post-item">
                  <div class="post-header">
                      <span class="post-type type-${postType}">${typeDisplay}</span>
                      <span class="post-meta">${formatDate(post.date)}</span>
                  </div>
                  <div class="post-title">
                      <a href="${post.url}" target="_blank">${escapeHtml(title)}</a>
                  </div>
                  <div class="post-content">${escapeHtml(post.content)}</div>
              </div>
          `;
      });
      
      postsList.innerHTML = html;
  }

  // Find posts
  async function findPosts() {
      const usernameInput = document.getElementById('usernameInput');
      const username = usernameInput.value.trim();
      const contentType = document.querySelector('input[name="contentType"]:checked').value;
      const loadingIndicator = document.getElementById('loadingIndicator');
      const resultsSection = document.getElementById('resultsSection');
      const errorMessage = document.getElementById('errorMessage');
      const statsInfo = document.getElementById('statsInfo');
      const downloadBtn = document.getElementById('downloadBtn');
      const downloadDescription = document.getElementById('downloadDescription');
      const findPostsBtn = document.getElementById('findPostsBtn');
      
      if (!username) {
          showError('Please enter your username.');
          return;
      }
      
      // Clear previous results
      errorMessage.style.display = 'none';
      resultsSection.style.display = 'none';
      downloadBtn.disabled = true;
      currentContentType = contentType;
      
      // Show loading state on button
      findPostsBtn.disabled = true;
      findPostsBtn.innerHTML = '<span class="spinner"></span> Searching...';
      findPostsBtn.classList.add('button-loading');
      
      // Show loading indicator
      loadingIndicator.style.display = 'block';
      
      try {
          // Find user ID
          const userId = await findUserIdByUsername(username);
          console.log(`Found user ID for "${username}": ${userId}`);
          
          if (!userId) {
              showError(`User "${escapeHtml(username)}" not found. Please check your username and try again.`);
              resetButtonState();
              loadingIndicator.style.display = 'none';
              return;
          }
          
          // Load user data
          currentUserData = await loadUserData(userId);
          currentUserId = userId;
          currentUsername = username;
          
          if (!currentUserData) {
              showError('No posts found for this user.');
              resetButtonState();
              loadingIndicator.style.display = 'none';
              return;
          }
          
          // Update stats based on content type
          let totalPosts, statsText, badgeHtml;
          
          if (contentType === 'both') {
              totalPosts = currentUserData.discussions.length + currentUserData.comments.length;
              statsText = `Found <strong>${totalPosts}</strong> posts by <strong>${escapeHtml(username)}</strong>`;
              badgeHtml = `<span class="content-type-badge badge-both">Both</span>`;
              downloadDescription.textContent = 'Download all your discussions and comments as a simple text file.';
          } else if (contentType === 'discussions') {
              totalPosts = currentUserData.discussions.length;
              statsText = `Found <strong>${totalPosts}</strong> discussions by <strong>${escapeHtml(username)}</strong>`;
              badgeHtml = `<span class="content-type-badge badge-discussions">Discussions Only</span>`;
              downloadDescription.textContent = 'Download your discussions as a simple text file.';
          } else if (contentType === 'comments') {
              totalPosts = currentUserData.comments.length;
              statsText = `Found <strong>${totalPosts}</strong> comments by <strong>${escapeHtml(username)}</strong>`;
              badgeHtml = `<span class="content-type-badge badge-comments">Comments Only</span>`;
              downloadDescription.textContent = 'Download your comments as a simple text file.';
          }
          
          statsInfo.innerHTML = statsText; // + badgeHtml;
          
          // Always display posts based on selected content type (no pagination needed)
          displayPosts(currentUserData, contentType);
          
          // Enable download button
          downloadBtn.disabled = false;
          
          // Show results and reset button
          loadingIndicator.style.display = 'none';
          resultsSection.style.display = 'block';
          resetButtonState();
          
      } catch (error) {
          loadingIndicator.style.display = 'none';
          resetButtonState();
          showError('Error loading posts. Please try again.');
          console.error(error);
      }
      
      function resetButtonState() {
          findPostsBtn.disabled = false;
          findPostsBtn.innerHTML = 'Find My Posts';
          findPostsBtn.classList.remove('button-loading');
      }
  }

  // Download posts
  async function downloadPosts() {
      if (!currentUserData || !currentUserId) {
          showError('No posts to download. Please find your posts first.');
          return;
      }
      
      try {
          // Load full content for download
          const fullResponse = await fetch(`/assets/user-data/${currentUserId}.json`);
          const fullData = await fullResponse.json();
          
          let content = `Posts by ${currentUsername}\\n`;
          content += `Content type: ${currentContentType === 'both' ? 'Discussions and Comments' : currentContentType}\\n`;
          content += `Downloaded from Philosophy Forum Archive on ${new Date().toLocaleDateString()}\\n`;
          
          let totalPosts = 0;
          
          if (currentContentType === 'both' || currentContentType === 'discussions') {
              totalPosts += fullData.discussions.length;
          }
          if (currentContentType === 'both' || currentContentType === 'comments') {
              totalPosts += fullData.comments.length;
          }
          
          content += `Total posts: ${totalPosts}\\n`;
          content += '='.repeat(50) + '\\n\\n';
          
          // Add discussions if selected
          if ((currentContentType === 'both' || currentContentType === 'discussions') && fullData.discussions.length > 0) {
              content += `DISCUSSIONS (${fullData.discussions.length})\\n`;
              content += '='.repeat(30) + '\\n';
              fullData.discussions.forEach((post, index) => {
                  content += `\\nDISCUSSION ${index + 1}/${fullData.discussions.length}\\n`;
                  content += `Date: ${formatDate(post.date)}\\n`;
                  content += `Title: ${post.title}\\n`;
                  content += `URL: ${window.location.origin}${post.url}\\n`;
                  content += '-'.repeat(40) + '\\n';
                  content += (post.full_content || post.content) + '\\n';
                  content += '='.repeat(50) + '\\n\\n';
              });
          }
          
          // Add comments if selected
          if ((currentContentType === 'both' || currentContentType === 'comments') && fullData.comments.length > 0) {
              content += `COMMENTS (${fullData.comments.length})\\n`;
              content += '='.repeat(30) + '\\n';
              fullData.comments.forEach((post, index) => {
                  content += `\\nCOMMENT ${index + 1}/${fullData.comments.length}\\n`;
                  content += `Date: ${formatDate(post.date)}\\n`;
                  content += `In discussion: ${post.discussion_title}\\n`;
                  content += `URL: ${window.location.origin}${post.url}\\n`;
                  content += '-'.repeat(40) + '\\n';
                  content += (post.full_content || post.content) + '\\n';
                  content += '='.repeat(50) + '\\n\\n';
              });
          }
          
          const blob = new Blob([content], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          
          let filename = `philosophy-forum-posts-${currentUsername.replace(/[^a-z0-9]/gi, '_')}`;
          if (currentContentType === 'discussions') filename += '-discussions';
          if (currentContentType === 'comments') filename += '-comments';
          filename += `-${new Date().toISOString().split('T')[0]}.txt`;
          
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          
      } catch (error) {
          showError('Error downloading posts. Please try again.');
          console.error(error);
      }
  }

  // Utility functions
  function showError(message) {
      const errorMessage = document.getElementById('errorMessage');
      errorMessage.textContent = message;
      errorMessage.style.display = 'block';
  }

  function formatDate(dateString) {
      return new Date(dateString).toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
      });
  }

  function escapeHtml(unsafe) {
      return unsafe
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
  }

  // Initialize
  document.addEventListener('DOMContentLoaded', function() {
      document.getElementById('findPostsBtn').addEventListener('click', findPosts);
      document.getElementById('downloadBtn').addEventListener('click', downloadPosts);
      
      // Allow Enter key to trigger search
      document.getElementById('usernameInput').addEventListener('keypress', function(e) {
          if (e.key === 'Enter') {
              findPosts();
          }
      });
      
      // Update content type badge when selection changes
      document.querySelectorAll('input[name="contentType"]').forEach(radio => {
          radio.addEventListener('change', function() {
              // This will update the display when they search again
          });
      });
  });