#!/usr/bin/env python3
"""
PlushForums to Static HTML Converter
"""

import json
import os
import re
import csv
import hashlib
from datetime import datetime
from pathlib import Path
import html
from urllib.parse import urljoin

class PlushForumsConverter:
    def __init__(self, config_path=None):

        #self._build_version = int(time.time())
        import time  # if not already
        self.buildversion = str(int(time.time()))

        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        
        # Load config directly - will crash if file missing (good for visibility)
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.excluded_users = set(
            username.lower()
            for username in self.config.get("excluded_users", [])
        )
    
        
        self.export_path = Path(self.config['export_path']).resolve()
        self.output_path = Path(self.config['output_path']).resolve()
        self.site_url = self.config["site_url"].rstrip("/") + "/"
        
        # Initialize other attributes
        self.discussions = {}
        self.comments = {}
        self.members = {}
        self.member_profiles = {}
        self.categories = {}
        self._cssversion = None
        self._template_cache = {}  # ← Store templates here
        
        print(f"Export path: {self.export_path}")
        print(f"Output path: {self.output_path}")


    def generate_comments_pagination_html(self, disc_id, slug, current_page, total_pages):
        """Generate pagination HTML for comments - follows same pattern as homepage"""
        if total_pages <= 1:
            return ""
        
        def page_url(page):
            if page == 1:
                return f"/discussions/{disc_id}-{slug}.html"
            else:
                return f"/discussions/{disc_id}-{slug}-page-{page}.html"
        
        pagination_html = '<div class="pagination comments-pagination">'
        
        # Previous button
        if current_page > 1:
            prev_url = page_url(current_page - 1)
            pagination_html += f'<a href="{prev_url}" class="pagination-arrow">← Previous</a> '
        else:
            pagination_html += '<span class="pagination-arrow disabled">← Previous</span> '
        
        # Page numbers
        pagination_html += f'<span class="page-info">Page {current_page} of {total_pages}</span>'
        
        # Next button
        if current_page < total_pages:
            next_url = page_url(current_page + 1)
            pagination_html += f' <a href="{next_url}" class="pagination-arrow">Next →</a>'
        else:
            pagination_html += ' <span class="pagination-arrow disabled">Next →</span>'
        
        pagination_html += '</div>'
        return pagination_html


    def generate_user_search_index(self, discussions_meta):
        """Generate a lightweight search index for fast username lookup"""
        print("Building user search index...")
        
        # Build username -> user_id mapping and count posts per user
        user_post_counts = {}
        
        # Count discussions per user
        for disc in discussions_meta:
            user_id = disc['author_id']
            user_post_counts[user_id] = user_post_counts.get(user_id, 0) + 1
        
        # Count comments per user  
        for disc_id, comments in self.comments.items():
            for comment in comments:
                user_id = comment['InsertUserID']
                user_post_counts[user_id] = user_post_counts.get(user_id, 0) + 1
        
        # Build the index
        search_index = {
            'usernames': {},  # lowercase_username -> user_id
            'post_counts': user_post_counts,
            'total_users': 0
        }
        
        # Add username mappings
        for user_id, username in self.members.items():
            search_index['usernames'][username.lower()] = user_id
        
        search_index['total_users'] = len(search_index['usernames'])
        
        # Write the index file
        index_file = self.output_path / "assets" / "js" / "user-search-index.js"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(f"window.userSearchIndex = {json.dumps(search_index, ensure_ascii=False)};")
        
        print(f"✅ Created search index with {search_index['total_users']} users")


    def generate_user_data_chunks(self, discussions_meta):
        """Generate user data chunks efficiently"""
        print("Building user data chunks efficiently...")
        
        # Pre-organize data by user_id for O(1) lookups
        user_discussions = {}
        user_comments = {}
        
        # Build discussions by user (O(n) instead of O(n×m))
        for disc in discussions_meta:
            user_id = disc['author_id']
            if user_id not in user_discussions:
                user_discussions[user_id] = []
            
            discussion = self.discussions[disc['id']]
            user_discussions[user_id].append({
                'id': disc['id'],
                'title': disc['title'], 
                'date': disc['date'],
                'url': disc['url'],
                'excerpt': self.make_excerpt(discussion.get('Body', ''), 200)
            })
        
        # Build comments by user (O(n) instead of O(n×m))
        comments_per_page = self.config.get('comments_per_page', 1000)
        for disc_id, comments in self.comments.items():
            for idx, comment in enumerate(comments):
                user_id = comment['InsertUserID']
                if user_id not in user_comments:
                    user_comments[user_id] = []

                disc_title = self.discussions[disc_id]['Name'] if disc_id in self.discussions else "Unknown Discussion"
                slug = self.generate_slug(disc_title)
                page = (idx // comments_per_page) + 1
                if page == 1:
                    url = f"/discussions/{disc_id}-{slug}.html#comment-{comment['CommentID']}"
                else:
                    url = f"/discussions/{disc_id}-{slug}-page-{page}.html#comment-{comment['CommentID']}"
                user_comments[user_id].append({
                    'id': comment['CommentID'],
                    'discussion_id': disc_id,
                    'discussion_title': disc_title,
                    'date': comment['DateInserted'],
                    'url': url,
                    'excerpt': self.make_excerpt(comment.get('Body', ''), 150)
                })
        
        # Now chunk users (this part is fast)
        chunk_size = 50
        all_users = list(self.members.keys())
        user_chunks = {}
        
        for chunk_num, i in enumerate(range(0, len(all_users), chunk_size)):
            chunk_user_ids = all_users[i:i + chunk_size]
            chunk_data = {}
            
            for user_id in chunk_user_ids:
                username = self.get_username(user_id)
                user_data = {
                    'username': username,
                    'discussions': user_discussions.get(user_id, []),
                    'comments': user_comments.get(user_id, [])
                }
                chunk_data[user_id] = user_data
                
                # Store chunk mapping
                user_chunks[user_id] = chunk_num
            
            # Write chunk file
            chunk_file = self.output_path / "assets" / "user-chunks" / f"chunk-{chunk_num}.js"
            chunk_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(chunk_file, 'w', encoding='utf-8') as f:
                f.write(f"window.userChunk{chunk_num} = {json.dumps(chunk_data, ensure_ascii=False)};")
            
            print(f"Created chunk {chunk_num} with {len(chunk_user_ids)} users")
        
        # Write chunk mapping
        mapping_file = self.output_path / "assets" / "js" / "user-chunk-mapping.js"
        with open(mapping_file, 'w', encoding='utf-8') as f:
            f.write(f"window.userChunkMapping = {json.dumps(user_chunks, ensure_ascii=False)};")
        
        print(f"✅ Created {len(user_chunks)} user mappings across {(len(all_users) + chunk_size - 1) // chunk_size} chunks")


    def make_excerpt(self, text, length):
        """Strip BBCode and truncate text for use as an excerpt."""
        if not text:
            return ''
        # Remove quote blocks entirely (including their quoted content)
        text = re.sub(r'\[quote[^\]]*\].*?\[/quote\]', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove reply tags
        text = re.sub(r'\[reply[^\]]*\]', '', text, flags=re.IGNORECASE)
        # Remove all remaining BBCode tags
        text = re.sub(r'\[[^\]]+\]', '', text)
        # Normalise whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > length:
            return text[:length] + '...'
        return text

    def fix_windows_1252_encoding(self, text):
        """Fix Windows-1252 encoded characters in JSON data"""
        if not text:
            return text
        
        # Mapping of Windows-1252 byte values to proper Unicode characters
        windows_1252_mapping = {
            '\u0080': '€', '\u0081': '', '\u0082': '‚', '\u0083': 'ƒ', '\u0084': '„', 
            '\u0085': '…', '\u0086': '†', '\u0087': '‡', '\u0088': 'ˆ', '\u0089': '‰',
            '\u008A': 'Š', '\u008B': '‹', '\u008C': 'Œ', '\u008D': '', '\u008E': 'Ž',
            '\u008F': '', '\u0090': '', '\u0091': '‘', '\u0092': '’', '\u0093': '“',
            '\u0094': '”', '\u0095': '•', '\u0096': '–', '\u0097': '—', '\u0098': '˜',
            '\u0099': '™', '\u009A': 'š', '\u009B': '›', '\u009C': 'œ', '\u009D': '',
            '\u009E': 'ž', '\u009F': 'Ÿ'
        }
        
        # Replace Windows-1252 encoded characters
        for win_char, unicode_char in windows_1252_mapping.items():
            text = text.replace(win_char, unicode_char)
        
        return text


    def get_category_name(self, category_id):
        """Get category name from ID, fallback to 'Uncategorized' if not found"""
        if category_id in self.categories:
            return self.categories[category_id]['Name']
        else:
            print(f"DEBUG: Category ID {category_id} not found in categories data")
            return "Uncategorized"


    def load_template(self, template_name):
        # Check if we already loaded this template
        if template_name in self._template_cache:
            return self._template_cache[template_name]  # ← Return cached version
        
        # If not cached, read from disk
        template_path = Path(__file__).parent / "templates" / template_name
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        template = template.replace('{cssversion}', str(self.get_cssversion()))
        
        # Store in cache for next time
        self._template_cache[template_name] = template
        return template

    def get_cssversion(self):
        """Get CSS version (cached per conversion run)"""
        if self._cssversion is None:
            css_file = Path(__file__).parent / "assets" / "css" / "style.css"
            if css_file.exists():
                self._cssversion = int(css_file.stat().st_mtime)
            else:
                self._cssversion = 1
        return self._cssversion

    def load_category_data(self):
        """Load category data from categories/all.json"""
        categories_path = self.export_path / "categories" / "all.json"
        if categories_path.exists():
            with open(categories_path, 'r', encoding='utf-8') as f:
                categories = json.load(f)
            self.categories = {cat['CategoryID']: cat for cat in categories}
            print(f"Loaded {len(self.categories)} categories")
        else:
            print("No categories file found")
            self.categories = {}

    def copy_assets(self):
        """Copy static assets from source to build directory"""
        source_assets = Path(__file__).parent / "assets"
        target_assets = self.output_path / "assets"
        
        if source_assets.exists():
            import shutil
            # Copy CSS, JS, and IMG folders
            for item in source_assets.iterdir():
                if item.is_dir():
                    shutil.copytree(item, target_assets / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target_assets / item.name)
            print(f"✅ Copied assets from {source_assets} to {target_assets}")
        else:
            print("⚠️  No source assets directory found")

        # Copy robots.txt to root
        robots_source = Path(__file__).parent / "robots.txt"
        if robots_source.exists():
            shutil.copy2(robots_source, self.output_path / "robots.txt")
            print("✅ Copied robots.txt to root")

        # Copy favicons and OG image to root
        assets_img = Path(__file__).parent / "assets" / "img"
        for filename in ["favicon.ico", "favicon-64.png", "og-image.png"]:
            src = assets_img / filename
            if src.exists():
                shutil.copy2(src, self.output_path / filename)
        print("✅ Copied favicons and OG image to root")


    def load_member_data(self):
        """Load member data from JSON files in members directory and subdirectories - only ID and Name"""
        print("Loading member data from JSON files...")
        
        members_path = self.export_path / "members"
        if not members_path.exists():
            print(f"ERROR: Members path not found: {members_path}")
            return
        
        # Search for JSON files in all subdirectories
        member_files = list(members_path.rglob("*.json"))
        print(f"Found {len(member_files)} member JSON files in {members_path} and subdirectories")
        
        if not member_files:
            print(f"No JSON files found in {members_path} or its subdirectories")
            return
        
        loaded_count = 0
        error_count = 0
        
        for json_file in member_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    member_data = json.load(f)
                
                # Check if we have the required fields
                if 'UserID' not in member_data:
                    print(f"WARNING: No UserID in {json_file}")
                    error_count += 1
                    continue
                    
                if 'Name' not in member_data:
                    print(f"WARNING: No Name in {json_file}")
                    error_count += 1
                    continue
                
                user_id = member_data['UserID']
                username = member_data['Name']

                # Store the ID and username
                self.members[user_id] = username

                # Store extended profile data
                meta = member_data.get('Meta', {}) or {}
                self.member_profiles[user_id] = {
                    'username': username,
                    'location': self.fix_windows_1252_encoding(meta.get('Location', '') or ''),
                    'bio': self.fix_windows_1252_encoding(meta.get('BioInfo', '') or ''),
                    'fav_philosopher': self.fix_windows_1252_encoding(meta.get('bm_favourite-philosopher', '') or ''),
                    'fav_quotations': self.fix_windows_1252_encoding(meta.get('bm_favourite-quotations', '') or ''),
                    'roles': member_data.get('Roles', ''),
                    'date_joined': member_data.get('DateFirstVisit', ''),
                    'date_last_active': member_data.get('DateLastActive', ''),
                    'deleted': bool(member_data.get('Deleted', False)),
                    'banned': bool(member_data.get('Banned', False)),
                    'count_discussions': member_data.get('CountDiscussions', 0),
                    'count_comments': member_data.get('CountComments', 0),
                }

                loaded_count += 1
                
            except Exception as e:
                print(f"Error loading member file {json_file}: {e}")
                error_count += 1
        
        print(f"Successfully loaded {loaded_count} members")
        if error_count > 0:
            print(f"Encountered errors with {error_count} member files")
        
        # Debug: show first few members
        if self.members:
            print("Sample members loaded:")
            for user_id, username in list(self.members.items())[:10]:
                print(f"  UserID {user_id} -> '{username}'")
        else:
            print("WARNING: No members were loaded!")

    def get_display_username(self, username):
        """Apply excluded-user rules to a raw username string"""
        if not username:
            return username

        if username.lower() in self.excluded_users:
            return "Deleted user"

        return username


    def get_username(self, user_id):
        """Get username from user ID, applying excluded-user replacement"""
        username = self.members.get(user_id)

        if not username:
            print(f"DEBUG: User ID {user_id} not found in members data")
            return f"User {user_id}"

        if username.lower() in self.excluded_users:
            return "Deleted user"

        return username

    
    def load_data(self):
        """Load all discussions and comments"""

        self.load_category_data()

        print("Loading discussions...")
        self._load_discussions()
        
        print("Loading comments...")  
        self._load_comments()
        
        print(f"Loaded {len(self.discussions)} discussions and {len(self.comments)} comments")
    

    def _load_discussions(self):
        """Load all discussion files, excluding CategoryID 21 and 22"""
        discussions_path = self.export_path / "discussions"
        if not discussions_path.exists():
            print(f"ERROR: Discussions path not found: {discussions_path}")
            return
            
        excluded_categories = self.config['excluded_categories']
        excluded_counts = {21: 0, 22: 0}
        total_discussions = 0
        
        for batch_dir in discussions_path.iterdir():
            if batch_dir.is_dir():
                for json_file in batch_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            discussion = json.load(f)

                        # FIX THE ENCODING ISSUE
                        if 'Body' in discussion:
                            discussion['Body'] = self.fix_windows_1252_encoding(discussion['Body'])
                        if 'Name' in discussion:
                            discussion['Name'] = self.fix_windows_1252_encoding(discussion['Name'])

                        total_discussions += 1
                        
                        # Check if CategoryID exists and is not in excluded categories
                        category_id = discussion.get('CategoryID')
                        if category_id in excluded_categories:
                            excluded_counts[category_id] += 1
                            print(f"Excluding discussion {discussion['DiscussionID']} - CategoryID {category_id}: {discussion['Name'][:50]}...")
                            continue
                            
                        # Add category name to discussion data for easy access
                        discussion['CategoryName'] = self.get_category_name(category_id)
                        self.discussions[discussion['DiscussionID']] = discussion
                            
                    except Exception as e:
                        print(f"Error loading {json_file}: {e}")
        
        print(f"Loaded {len(self.discussions)} discussions (excluded {excluded_counts[21]} with CategoryID 21, {excluded_counts[22]} with CategoryID 22)")
        print(f"Total discussions processed: {total_discussions}")
        
        print(f"Total discussions processed: {total_discussions}")
    

    def _load_comments(self):
        """Load all comment files, excluding comments from excluded discussions"""
        comments_path = self.export_path / "comments"
        if not comments_path.exists():
            print(f"ERROR: Comments path not found: {comments_path}")
            return
            
        for batch_dir in comments_path.iterdir():
            if batch_dir.is_dir():
                for json_file in batch_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            comments_batch = json.load(f)
                            for comment in comments_batch:
                                disc_id = comment['DiscussionID']
                                # Skip comments from excluded discussions
                                if disc_id not in self.discussions:
                                    continue
                                
                                # FIX THE ENCODING FOR COMMENTS TOO!
                                if 'Body' in comment:
                                    comment['Body'] = self.fix_windows_1252_encoding(comment['Body'])
                                
                                if disc_id not in self.comments:
                                    self.comments[disc_id] = []
                                self.comments[disc_id].append(comment)
                    except Exception as e:
                        print(f"Error loading {json_file}: {e}")
        
        # Sort comments by date within each discussion
        for disc_id in self.comments:
            self.comments[disc_id].sort(key=lambda x: x['DateInserted'])

    def _convert_reply_tag(self, match, current_discussion_id=None):
        """Convert [reply="UserName;ID"] tags to links - handles both comment and discussion IDs"""
        username = match.group(1)
        target_id = match.group(2)

        username = self.get_display_username(username)
        
        # Check if it's a discussion ID (starts with 'd') or comment ID (numeric)
        if target_id.startswith('d'):
            # It's a discussion ID - remove the 'd' prefix
            disc_id = target_id[1:]
            
            # Check if this refers to the current discussion or a different one
            if current_discussion_id and str(disc_id) == str(current_discussion_id):
                # Same discussion - create anchor link to jump to top
                return f'<a href="#discussion-top" class="reply-link">Reply to {username}</a>'
            else:
                # Different discussion - create external link with proper slug
                if disc_id in self.discussions:
                    discussion = self.discussions[disc_id]
                    slug = self.generate_slug(discussion['Name'])
                    return f'<a href="/discussions/{disc_id}-{slug}.html" class="reply-link">Reply to {username}</a>'
                else:
                    # Fallback if discussion not found
                    return f'<a href="/discussions/{disc_id}" class="reply-link">Reply to {username}</a>'
        else:
            # It's a comment ID - create anchor link
            return f'<a href="#comment-{target_id}" class="reply-link">Reply to {username}</a>'

    def _convert_complex_quote(self, match, current_discussion_id=None):
        """Convert [quote="UserName;ID"]...[/quote] tags - handles both comment and discussion IDs"""
        username = match.group(1)
        target_id = match.group(2)
        quoted_content = match.group(3)

        username = self.get_display_username(username)
        
        # Check if it's a discussion ID (starts with 'd') or comment ID (numeric)
        if target_id.startswith('d'):
            # It's a discussion ID - remove the 'd' prefix
            disc_id = target_id[1:]
            
            # Check if this refers to the current discussion or a different one
            if current_discussion_id and str(disc_id) == str(current_discussion_id):
                # Same discussion - create anchor link to jump to top
                return f'<a href="#discussion-top" class="quote-link">Quoting {username}</a><blockquote class="user-quote">{quoted_content}</blockquote>'
            else:
                # Different discussion - create external link with proper slug
                if disc_id in self.discussions:
                    discussion = self.discussions[disc_id]
                    slug = self.generate_slug(discussion['Name'])
                    return f'<a href="/discussions/{disc_id}-{slug}.html" class="quote-link">Quoting {username}</a><blockquote class="user-quote">{quoted_content}</blockquote>'
                else:
                    # Fallback if discussion not found
                    return f'<a href="/discussions/{disc_id}" class="quote-link">Quoting {username}</a><blockquote class="user-quote">{quoted_content}</blockquote>'
        else:
            # It's a comment ID - create anchor link
            return f'<a href="#comment-{target_id}" class="quote-link">Quoting {username}</a><blockquote class="user-quote">{quoted_content}</blockquote>'

    def convert_plush_bbcode(self, text, current_discussion_id=None):
        """Enhanced BBCode parser with proper Unicode handling for em dashes and other special characters"""
        if not text:
            return ""
        
        # Ensure text is properly decoded as UTF-8
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        
        # Your existing dash debugging code...
        
        # Your existing line break processing
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = text.replace('\n', '<br>\n')
        
        # Step 1: Convert reply tags to internal links - UPDATED FOR DISCUSSION IDs
        # Handle both comment IDs (numeric) and discussion IDs (d + numeric)
        text = re.sub(
            r'\[reply="([^";]+);(d?\d+)"\]',
            lambda match: self._convert_reply_tag(match, current_discussion_id),
            text
        )
        
        # Step 2: Convert complex quotes with parameters - UPDATED FOR DISCUSSION IDs
        text = re.sub(
            r'\[quote="([^";]+);([^"]+)"\](.*?)\[/quote\]',
            lambda match: self._convert_complex_quote(match, current_discussion_id),
            text, flags=re.DOTALL | re.IGNORECASE
        )

        # [quote="UserName"]...[/quote] (without ID)
        text = re.sub(
            r'\[quote="([^"]+)"\](.*?)\[/quote\]',
            r'<blockquote class="user-quote"><cite>\1:</cite>\2</blockquote>',
            text, flags=re.DOTALL | re.IGNORECASE
        )

        # [quote=label]...[/quote] (unquoted attribute, e.g. manual book/source quotes)
        text = re.sub(
            r'\[quote=([^\]]+)\](.*?)\[/quote\]',
            r'<blockquote class="user-quote"><cite>\1:</cite>\2</blockquote>',
            text, flags=re.DOTALL | re.IGNORECASE
        )

        # Step 3: Convert simple quotes
        text = re.sub(
            r'\[quote\](.*?)\[/quote\]',
            r'<blockquote class="simple-quote">\1</blockquote>',
            text, flags=re.DOTALL | re.IGNORECASE
        )

        # Clean up any unclosed or orphaned quote tags left unmatched
        text = re.sub(r'\[quote[^\]]*\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[/quote\]', '', text, flags=re.IGNORECASE)

        # Step 4: Convert user mentions @"UserName" with proper links
        text = re.sub(
            r'@"([^"]+)"',
            self._convert_user_mention,
            text
        )
        
        # ... continue with the rest of your existing BBCode processing
        
        # Step 5: Convert basic formatting
        text = re.sub(r'\[b\](.*?)\[/b\]', r'<strong>\1</strong>', text)
        text = re.sub(r'\[i\](.*?)\[/i\]', r'<em>\1</em>', text)
        text = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', text)
        
        # Step 6: Convert URLs and media
        text = re.sub(r'\[url=(.*?)\](.*?)\[/url\]', r'<a href="\1" class="external-link">\2</a>', text)
        text = re.sub(r'\[url\](.*?)\[/url\]', r'<a href="\1" class="external-link">\1</a>', text)
        
        # Step 7: Convert media embeds
        text = re.sub(
            r'\[media\](.*?)\[/media\]', 
            r'<div class="media-embed"><a href="\1" target="_blank">🔗 Media content</a></div>', 
            text
        )
        
        # Step 8: Convert images
        text = re.sub(
            r'\[img\](.*?)\[/img\]', 
            r'<img src="\1" alt="User image" class="user-image" loading="lazy">', 
            text
        )
        
        # Step 9: Convert code blocks
        text = re.sub(
            r'\[code\](.*?)\[/code\]', 
            r'<pre><code>\1</code></pre>', 
            text, flags=re.DOTALL
        )
        
        # Step 10: Convert lists
      # DEBUG: Check for lists before processing
        has_ordered_lists = re.search(r'\[list=([^\]]+)\](.*?)\[/list\]', text, flags=re.DOTALL)
        has_unordered_lists = re.search(r'\[list\](.*?)\[/list\]', text, flags=re.DOTALL)
        
        # Step 10: Convert lists
        # Numbered lists [list=1] or [list=a]
        text = re.sub(
            r'\[list=([^\]]+)\](.*?)\[/list\]',
            self._convert_ordered_list,
            text, flags=re.DOTALL
        )
        
        # Unordered lists [list]
        text = re.sub(
            r'\[list\](.*?)\[/list\]',
            self._convert_unordered_list,
            text, flags=re.DOTALL
        )

        return text
    
    def _convert_user_mention(self, match):
        """Convert @"username" to clickable mention if user exists, respecting excluded_users"""
        username = match.group(1)

        # If this username is excluded, show replacement and do NOT link
        if username.lower() in self.excluded_users:
            return '<span class="user-mention deleted">@Deleted user</span>'

        # Find user ID by username
        user_id = None
        for uid, name in self.members.items():
            if name == username:
                user_id = uid
                break

        if user_id:
            return f'<a href="/members/{user_id}.html" class="user-mention">@{username}</a>'
        else:
            return f'<span class="user-mention unknown">@{username}</span>'

        
    def _convert_ordered_list(self, match):
        """Convert ordered list BBCode to HTML"""
        list_type = match.group(1)
        list_content = match.group(2)
        
        # Split on [*] and clean up each item
        list_items = re.split(r'\[\*\]', list_content)
        
        # Clean each item: remove <br> tags, strip whitespace, filter empties
        cleaned_items = []
        for item in list_items:
            # Remove <br> tags and whitespace
            item = re.sub(r'<br>\s*', '', item)
            item = item.strip()
            # Only add non-empty items
            if item:
                cleaned_items.append(item)
        
        li_tags = ''.join(f'<li>{item}</li>' for item in cleaned_items)
        
        if list_type in ['1', 'a', 'A', 'i', 'I']:
            return f'<ol type="{list_type}">{li_tags}</ol>'
        else:
            return f'<ol>{li_tags}</ol>'

    def _convert_unordered_list(self, match):
        """Convert unordered list BBCode to HTML"""
        list_content = match.group(1)
        
        # Split on [*] and clean up each item
        list_items = re.split(r'\[\*\]', list_content)
        
        # Clean each item: remove <br> tags, strip whitespace, filter empties
        cleaned_items = []
        for item in list_items:
            # Remove <br> tags and whitespace
            item = re.sub(r'<br>\s*', '', item)
            item = item.strip()
            # Only add non-empty items
            if item:
                cleaned_items.append(item)
        
        li_tags = ''.join(f'<li>{item}</li>' for item in cleaned_items)
        return f'<ul>{li_tags}</ul>'
        
    def format_date(self, date_string):
        """Format date string for display"""
        try:
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            return dt.strftime('%B %d, %Y at %H:%M')
        except:
            return date_string
    
    def generate_slug(self, title):
        """Generate URL slug from discussion title"""
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug[:200].rstrip("-")
    

    def generate_discussion_page(self, discussion, page_num=1):
        """Generate discussion page with paginated comments"""
        disc_id = discussion['DiscussionID']
        slug = self.generate_slug(discussion['Name'])
        
        # Get comments for this discussion
        discussion_comments = self.comments.get(disc_id, [])
        
        # Paginate comments
        comments_per_page = self.config.get('comments_per_page', 100)
        total_pages = (len(discussion_comments) + comments_per_page - 1) // comments_per_page
        page_num = max(1, min(page_num, total_pages))  # Clamp to valid range
        
        start_idx = (page_num - 1) * comments_per_page
        end_idx = start_idx + comments_per_page
        page_comments = discussion_comments[start_idx:end_idx]
        
        # Convert discussion body
        discussion_body = self.convert_plush_bbcode(discussion['Body'], disc_id)
        
        # Get author username
        author_id = discussion['InsertUserID']
        author_name = self.get_username(author_id)
        if author_name != "Deleted user":
            author_display = f'<a href="/members/{author_id}.html" class="author-link">{html.escape(author_name)}</a>'
        else:
            author_display = html.escape(author_name)

        # Generate comments HTML
        comments_html = ""
        for comment in page_comments:
            comment_body = self.convert_plush_bbcode(comment['Body'], disc_id)
            comment_author_id = comment['InsertUserID']
            comment_author_name = self.get_username(comment_author_id)
            if comment_author_name != "Deleted user":
                comment_author_display = f'<a href="/members/{comment_author_id}.html" class="author-link">{html.escape(comment_author_name)}</a>'
            else:
                comment_author_display = html.escape(comment_author_name)

            comments_html += f"""
                <div class="comment" id="comment-{comment['CommentID']}">
                    <div class="comment-meta">
                        <span class="author">{comment_author_display}</span>
                        <span class="date">{self.format_date(comment['DateInserted'])}</span>
                        <span class="comment-id"><a href="#comment-{comment['CommentID']}" class="comment-permalink" title="Copy link" onclick="copyPermalink(event,this)">¶ #{comment['CommentID']}</a></span>
                        <span class="likes">{comment.get('Likes', 0)} likes</span>
                    </div>
                    <div class="comment-content">
                        {comment_body}
                    </div>
                </div>"""
        
        # Generate pagination using your existing pattern
        pagination_html = self.generate_comments_pagination_html(disc_id, slug, page_num, total_pages)
        
        # Load templates and render (your existing code)
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('discussion.html')

        cssversion = self.get_cssversion()
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Category link
        cat_id = discussion.get('CategoryID')
        if cat_id and cat_id in self.categories:
            cat_name = self.categories[cat_id]['Name']
            cat_slug = self.generate_slug(cat_name)
            category_html = f'<span class="category"><a href="/categories/{cat_id}-{cat_slug}.html">{html.escape(cat_name)}</a></span>'
        else:
            category_html = ''

        # Render content
        main_content = content_template.format(
            discussion_title=html.escape(discussion['Name']),
            author_name=author_display,
            discussion_date=self.format_date(discussion['DateInserted']),
            view_count=discussion['CountViews'],
            comment_count=len(discussion_comments),
            discussion_body=discussion_body,
            comments_html=comments_html,
            pagination_html=pagination_html,
            category_html=category_html
        )

        if page_num == 1:
            pagepath = "discussions/" + f"{disc_id}-{slug}.html"
        else:
            pagepath = "discussions/" + f"{disc_id}-{slug}-page-{page_num}.html"

        catid = discussion.get('CategoryID')
        robot_block=""
        if catid in self.config["noindex_categories"]:
            robot_block = '<meta name="robots" content="noindex, nofollow">'

        # Then render layout with content
        html_content = layout_template.format(
            title=html.escape(discussion['Name']) + (f" - Page {page_num}" if page_num > 1 else ""),
            cssversion=cssversion,
            buildversion=self.buildversion,
            extrahead="",
            extrafoot=(
                '<a href="#" class="back-to-top" aria-label="Back to top">⇧</a>'
                '<script>'
                'function copyPermalink(e,el){'
                'e.preventDefault();'
                'navigator.clipboard.writeText(el.href);'
                'history.pushState(null,"",el.href);'
                'var t=document.getElementById("permalink-toast");'
                'if(!t){t=document.createElement("div");t.id="permalink-toast";document.body.appendChild(t);}'
                't.textContent="Link copied";'
                'clearTimeout(t._t);'
                't.classList.add("show");'
                't._t=setTimeout(function(){t.classList.remove("show")},1400);'
                '}'
                '</script>'
            ),
            canonical_url=f"{self.site_url}" + pagepath,
            robot_block=robot_block,
            header=header_html,
            main=main_content,
            footer=footer_html
        )
        
        # Write file with appropriate naming
        if page_num == 1:
            output_file = self.output_path / "discussions" / f"{disc_id}-{slug}.html"
        else:
            output_file = self.output_path / "discussions" / f"{disc_id}-{slug}-page-{page_num}.html"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return {
            'id': disc_id,
            'title': discussion['Name'],
            'date': discussion['DateInserted'],
            'slug': slug,
            'url': f"/discussions/{disc_id}-{slug}.html",
            'comment_count': len(discussion_comments),
            'author_id': author_id,
            'category_id': discussion.get('CategoryID'),
            'category_name': self.categories.get(discussion.get('CategoryID'), {}).get('Name', 'Uncategorized'),
            'total_pages': total_pages
        }
    
    def _extract_discussion_meta(self, discussion):
        """Extract discussion metadata without generating HTML. Used for two-pass build."""
        disc_id = discussion['DiscussionID']
        slug = self.generate_slug(discussion['Name'])
        discussion_comments = self.comments.get(disc_id, [])
        comments_per_page = self.config.get('comments_per_page', 100)
        total_pages = (len(discussion_comments) + comments_per_page - 1) // comments_per_page
        author_id = discussion['InsertUserID']
        return {
            'id': disc_id,
            'title': discussion['Name'],
            'date': discussion['DateInserted'],
            'slug': slug,
            'url': f"/discussions/{disc_id}-{slug}.html",
            'comment_count': len(discussion_comments),
            'author_id': author_id,
            'category_id': discussion.get('CategoryID'),
            'category_name': self.categories.get(discussion.get('CategoryID'), {}).get('Name', 'Uncategorized'),
            'total_pages': total_pages,
        }

    def generate_related_discussions_html(self, disc_id, category_id, discussions_meta):
        """Return HTML fragment for up to 5 most-recent discussions in the same category."""
        related = [
            d for d in discussions_meta
            if d['category_id'] == category_id and d['id'] != disc_id
        ][:5]
        if not related:
            return ''
        items = ''.join(
            f'<li><a href="{d["url"]}">{html.escape(d["title"])}</a></li>\n'
            for d in related
        )
        return (
            '<section class="related-discussions">'
            '<h3>More from this category</h3>'
            f'<ul>{items}</ul>'
            '</section>'
        )

    def _generate_pagelist_html(self, current_page, total_pages, url_fn):
        """Generate pagination HTML (1-indexed). url_fn(page_num) -> url string."""
        if total_pages <= 1:
            return ''
        pagination_html = '<div class="pagination">'
        if current_page > 1:
            pagination_html += f'<a href="{url_fn(current_page - 1)}" class="pagination-arrow">← Previous</a> '
        else:
            pagination_html += '<span class="pagination-arrow disabled">← Previous</span> '
        pagination_html += f'<span class="page-info">Page {current_page} of {total_pages}</span>'
        if current_page < total_pages:
            pagination_html += f' <a href="{url_fn(current_page + 1)}" class="pagination-arrow">Next →</a>'
        else:
            pagination_html += ' <span class="pagination-arrow disabled">Next →</span>'
        pagination_html += '</div>'
        return pagination_html

    def generate_category_pages(self, discussions_meta):
        """Generate paginated category listing pages and a categories index."""
        print("Generating category pages...")
        page_size = self.config.get('category_page_size', 50)
        noindex_categories = self.config.get('noindex_categories', [])

        # Group by category (discussions_meta already sorted newest-first)
        by_category = {}
        for disc in discussions_meta:
            cat_id = disc['category_id']
            by_category.setdefault(cat_id, []).append(disc)

        categories_dir = self.output_path / "categories"
        categories_dir.mkdir(parents=True, exist_ok=True)

        layout_template = self.load_template('layout.html')
        content_template = self.load_template('category.html')
        index_template = self.load_template('categories-index.html')
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')
        cssversion = self.get_cssversion()

        category_list_items = []

        for cat_id, discs in by_category.items():
            cat_info = self.categories.get(cat_id, {})
            cat_name = cat_info.get('Name', 'Uncategorized')
            cat_slug = self.generate_slug(cat_name)
            total_pages = max(1, (len(discs) + page_size - 1) // page_size)

            robot_block = ''
            if cat_id in noindex_categories:
                robot_block = '<meta name="robots" content="noindex, nofollow">'

            for page_num in range(1, total_pages + 1):
                start_idx = (page_num - 1) * page_size
                page_discs = discs[start_idx:start_idx + page_size]

                discussions_list = ''
                for disc in page_discs:
                    author_name = self.get_username(disc['author_id'])
                    discussions_list += f"""
                    <article class="discussion-summary">
                        <h3><a href="{disc['url']}">{html.escape(disc['title'])}</a></h3>
                        <div class="discussion-meta">
                            <span class="author">by {html.escape(author_name)}</span>
                            <span class="date">{self.format_date(disc['date'])}</span>
                            <span class="comments">{disc['comment_count']} comments</span>
                        </div>
                    </article>"""

                def page_url(p, _cat_id=cat_id, _cat_slug=cat_slug):
                    if p == 1:
                        return f"/categories/{_cat_id}-{_cat_slug}.html"
                    return f"/categories/{_cat_id}-{_cat_slug}-page-{p}.html"

                pagination_html = self._generate_pagelist_html(page_num, total_pages, page_url)

                if page_num == 1:
                    filename = f"{cat_id}-{cat_slug}.html"
                    pagepath = f"categories/{filename}"
                else:
                    filename = f"{cat_id}-{cat_slug}-page-{page_num}.html"
                    pagepath = f"categories/{filename}"

                main_content = content_template.format(
                    category_name=html.escape(cat_name),
                    discussion_count=len(discs),
                    top_pagination=pagination_html,
                    bottom_pagination=pagination_html,
                    discussions_list=discussions_list,
                )
                html_content = layout_template.format(
                    title=html.escape(cat_name) + (f" - Page {page_num}" if page_num > 1 else ""),
                    cssversion=cssversion,
                    buildversion=self.buildversion,
                    header=header_html,
                    main=main_content,
                    footer=footer_html,
                    canonical_url=f"{self.site_url}{pagepath}",
                    robot_block=robot_block,
                    extrahead='',
                    extrafoot='',
                )
                with open(categories_dir / filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)

            category_list_items.append({
                'name': cat_name,
                'url': f"/categories/{cat_id}-{cat_slug}.html",
                'count': len(discs),
            })

        # Alphabetical categories index
        category_list_items.sort(key=lambda x: x['name'])
        categories_list_html = ''.join(
            f'<li><a href="{item["url"]}">{html.escape(item["name"])}</a>'
            f' <span style="color:#666">({item["count"]} discussions)</span></li>\n'
            for item in category_list_items
        )
        main_content = index_template.format(categories_list=categories_list_html)
        html_content = layout_template.format(
            title="Categories",
            cssversion=cssversion,
            buildversion=self.buildversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
            canonical_url=f"{self.site_url}categories/",
            robot_block='',
            extrahead='',
            extrafoot='',
        )
        with open(categories_dir / "index.html", 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ Generated category pages for {len(by_category)} categories")

    def generate_member_pages(self, discussions_meta):
        """Generate member profile pages."""
        print("Generating member pages...")
        comments_per_page_member = 50
        disc_comments_per_page = self.config.get('comments_per_page', 100)

        members_dir = self.output_path / "members"
        members_dir.mkdir(parents=True, exist_ok=True)

        layout_template = self.load_template('layout.html')
        content_template = self.load_template('member.html')
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')
        cssversion = self.get_cssversion()

        # Build user→discussions map
        user_discussions = {}
        for disc in discussions_meta:
            user_id = disc['author_id']
            user_discussions.setdefault(user_id, []).append(disc)

        # Build user→comments map (with URLs into discussion pages)
        user_comments = {}
        for disc_id, comments in self.comments.items():
            disc_title = self.discussions[disc_id]['Name'] if disc_id in self.discussions else "Unknown Discussion"
            disc_slug = self.generate_slug(disc_title)
            for idx, comment in enumerate(comments):
                user_id = comment['InsertUserID']
                page = (idx // disc_comments_per_page) + 1
                if page == 1:
                    url = f"/discussions/{disc_id}-{disc_slug}.html#comment-{comment['CommentID']}"
                else:
                    url = f"/discussions/{disc_id}-{disc_slug}-page-{page}.html#comment-{comment['CommentID']}"
                user_comments.setdefault(user_id, []).append({
                    'id': comment['CommentID'],
                    'discussion_title': disc_title,
                    'discussion_url': f"/discussions/{disc_id}-{disc_slug}.html",
                    'date': comment['DateInserted'],
                    'url': url,
                    'excerpt': self.make_excerpt(comment.get('Body', ''), 150),
                })

        generated = 0
        skipped = 0

        for user_id, username in self.members.items():
            if username.lower() in self.excluded_users:
                skipped += 1
                continue

            profile = self.member_profiles.get(user_id, {})
            discs = user_discussions.get(user_id, [])
            comments = sorted(user_comments.get(user_id, []), key=lambda x: x['date'], reverse=True)
            total_comment_pages = max(1, (len(comments) + comments_per_page_member - 1) // comments_per_page_member)

            def page_url(p, _uid=user_id):
                return f"/members/{_uid}.html" if p == 1 else f"/members/{_uid}-page-{p}.html"

            for page_num in range(1, total_comment_pages + 1):
                page_comments = comments[(page_num - 1) * comments_per_page_member:page_num * comments_per_page_member]
                pagination_html = self._generate_pagelist_html(page_num, total_comment_pages, page_url)

                # Profile section: page 1 only
                if page_num == 1:
                    profile_section = self._render_member_profile_section(username, profile)
                    discussions_section = self._render_member_discussions_section(discs)
                else:
                    profile_section = f'<div class="member-profile"><h1><a href="/members/{user_id}.html">{html.escape(username)}</a></h1></div>'
                    discussions_section = ''

                comments_html = self._render_member_comments_html(page_comments)

                main_content = content_template.format(
                    username=html.escape(username),
                    profile_section=profile_section,
                    discussions_section=discussions_section,
                    comments_html=comments_html,
                    top_pagination=pagination_html,
                    bottom_pagination=pagination_html,
                )

                if page_num == 1:
                    filename = f"{user_id}.html"
                    pagepath = f"members/{filename}"
                else:
                    filename = f"{user_id}-page-{page_num}.html"
                    pagepath = f"members/{filename}"

                html_content = layout_template.format(
                    title=f"{html.escape(username)}'s Profile" + (f" - Page {page_num}" if page_num > 1 else ""),
                    cssversion=cssversion,
                    buildversion=self.buildversion,
                    header=header_html,
                    main=main_content,
                    footer=footer_html,
                    canonical_url=f"{self.site_url}{pagepath}",
                    robot_block='',
                    extrahead='',
                    extrafoot='<a href="#" class="back-to-top" aria-label="Back to top">⇧</a>',
                )
                with open(members_dir / filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)

            generated += 1

        print(f"✅ Generated pages for {generated} members, skipped {skipped} excluded users")

    def _render_member_profile_section(self, username, profile):
        """Build the profile info HTML for a member page (page 1 only)."""
        status_badges = ''

        roles = profile.get('roles', '') or ''
        date_joined = self.format_date(profile['date_joined']) if profile.get('date_joined') else ''
        date_last = self.format_date(profile['date_last_active']) if profile.get('date_last_active') else ''

        meta_parts = []
        if roles:
            meta_parts.append(f'<span class="roles">{html.escape(str(roles))}</span>')
        if date_joined:
            meta_parts.append(f'<span>Joined: {date_joined}</span>')
        if date_last:
            meta_parts.append(f'<span>Last active: {date_last}</span>')
        meta_parts.append(f'<span>{profile.get("count_discussions", 0)} discussions</span>')
        meta_parts.append(f'<span>{profile.get("count_comments", 0)} comments</span>')
        meta_html = f'<div class="member-meta">{"".join(meta_parts)}</div>' if meta_parts else ''

        bio = profile.get('bio', '') or ''
        bio_html = (
            f'<div class="member-bio"><h3>Bio</h3><div>{self.convert_plush_bbcode(bio)}</div></div>'
            if bio.strip() else ''
        )

        fav_phil = profile.get('fav_philosopher', '') or ''
        fav_phil_html = (
            f'<div class="member-fav-philosopher"><h3>Favourite Philosopher</h3><div>{self.convert_plush_bbcode(fav_phil)}</div></div>'
            if fav_phil.strip() else ''
        )

        fav_quot = profile.get('fav_quotations', '') or ''
        fav_quot_html = (
            f'<div class="member-fav-quotations"><h3>Favourite Quotations</h3><div>{self.convert_plush_bbcode(fav_quot)}</div></div>'
            if fav_quot.strip() else ''
        )

        location = profile.get('location', '') or ''
        loc_html = f'<div class="member-location"><strong>Location:</strong> {html.escape(location)}</div>' if location.strip() else ''

        return (
            f'<div class="member-profile">'
            f'<h1>{html.escape(username)}{status_badges}</h1>'
            f'{meta_html}{loc_html}{bio_html}{fav_phil_html}{fav_quot_html}'
            f'</div>'
        )

    def _render_member_discussions_section(self, discs):
        """Build the discussions list HTML for a member page."""
        if not discs:
            return ''
        items = ''
        for disc in discs:
            items += f"""
            <article class="discussion-summary">
                <h3><a href="{disc['url']}">{html.escape(disc['title'])}</a></h3>
                <div class="discussion-meta">
                    <span class="date">{self.format_date(disc['date'])}</span>
                    <span class="comments">{disc['comment_count']} comments</span>
                    <span class="category">{html.escape(disc['category_name'])}</span>
                </div>
            </article>"""
        return f'<section class="member-discussions"><h2>Discussions ({len(discs)})</h2>{items}</section>'

    def _render_member_comments_html(self, comments):
        """Build the comments list HTML for a member page."""
        if not comments:
            return '<p style="color:#666">No comments.</p>'
        items = ''
        for c in comments:
            items += f"""
            <div class="member-comment-item">
                <div class="comment-discussion">
                    In: <a href="{c['discussion_url']}">{html.escape(c['discussion_title'])}</a>
                    &nbsp;—&nbsp;<a href="{c['url']}">view comment</a>
                </div>
                <div class="comment-excerpt">{html.escape(c['excerpt'])}</div>
                <div class="comment-date">{self.format_date(c['date'])}</div>
            </div>"""
        return items

    def _compute_template_hash(self):
        """MD5 of all template files + style.css."""
        templates_dir = Path(__file__).parent / "templates"
        css_file = Path(__file__).parent / "assets" / "css" / "style.css"
        h = hashlib.md5()
        for f in sorted(templates_dir.rglob("*.html")):
            h.update(f.read_bytes())
        if css_file.exists():
            h.update(css_file.read_bytes())
        return h.hexdigest()

    def _compute_discussion_hash(self, disc_id):
        """MD5 of discussion data + its comments."""
        content = (
            json.dumps(self.discussions[disc_id], sort_keys=True)
            + json.dumps(self.comments.get(disc_id, []), sort_keys=True)
        )
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _load_build_manifest(self):
        """Load the incremental build manifest, returning {} if missing."""
        manifest_path = self.output_path / "processed_data" / "build_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_build_manifest(self, manifest):
        """Save the incremental build manifest."""
        manifest_path = self.output_path / "processed_data" / "build_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False)

    def generate_user_posts_data(self, discussions_meta):
        """Generate user-specific data files and username lookup"""
        
        # Create a mapping of user IDs to their posts
        user_posts_map = {}
        username_lookup = {}  # lowercase username -> user ID
        
        print("Building user posts data...")
        
        # Track Janus specifically for debugging
        janus_user_id = None
        janus_discussions = 0
        janus_comments = 0
        
        # Process discussions
        for disc in discussions_meta:
            user_id = disc['author_id']
            username = self.get_username(user_id)
            
            # Track Janus
            if username.lower() == 'janus':
                janus_user_id = user_id
                janus_discussions += 1
            
            if user_id not in user_posts_map:
                user_posts_map[user_id] = {'discussions': [], 'comments': []}
                username_lookup[username.lower()] = user_id
            
            discussion = self.discussions[disc['id']]
            user_posts_map[user_id]['discussions'].append({
                'id': disc['id'],
                'title': disc['title'],
                'date': disc['date'],
                'url': disc['url'],
                'content': discussion.get('Body', '')[:500] + '...' if len(discussion.get('Body', '')) > 500 else discussion.get('Body', ''),
                'full_content': discussion.get('Body', '')  # Keep full content for download
            })

        # Process comments
        for disc_id, comments in self.comments.items():
            for comment in comments:
                user_id = comment['InsertUserID']
                username = self.get_username(user_id)
                
                # Track Janus
                if username.lower() == 'janus':
                    janus_comments += 1
                
                if user_id not in user_posts_map:
                    user_posts_map[user_id] = {'discussions': [], 'comments': []}
                    username_lookup[username.lower()] = user_id
                
                # Get discussion title for context
                disc_title = "Unknown Discussion"
                if disc_id in self.discussions:
                    disc_title = self.discussions[disc_id]['Name']
                
                user_posts_map[user_id]['comments'].append({
                    'id': comment['CommentID'],
                    'discussion_id': disc_id,
                    'discussion_title': disc_title,
                    'date': comment['DateInserted'],
                    'url': f"/discussions/{disc_id}-{self.generate_slug(disc_title)}.html#comment-{comment['CommentID']}",
                    'content': comment.get('Body', '')[:300] + '...' if len(comment.get('Body', '')) > 300 else comment.get('Body', ''),
                    'full_content': comment.get('Body', '')  # Keep full content for download
                })
        
       
        # Rest of the method continues...
        print(f"Created username lookup with {len(username_lookup)} users")
        # ... etc
        
        print(f"Created username lookup with {len(username_lookup)} users")
        
        # Write username lookup
        lookup_file = self.output_path / "assets" / "js" / "user-lookup.js"
        lookup_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(lookup_file, 'w', encoding='utf-8') as f:
            f.write(f"window.userLookup = {json.dumps(username_lookup, ensure_ascii=False)};")
        
        print(f"Written user lookup to: {lookup_file}")
        
        # DEBUG: what dates are we actually seeing here?
        all_dates = []
        for u in user_posts_map.values():
            for c in u["comments"]:
                all_dates.append(c["date"])

        print("DEBUG newest comment date in user_posts_map:", max(all_dates) if all_dates else "NONE")
        # /DEBUG

        # Write individual user data files
        user_data_dir = self.output_path / "assets" / "user-data"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        user_files_created = 0
        for user_id, data in user_posts_map.items():
            # Sort posts by date (newest first)
            data['discussions'].sort(key=lambda x: x['date'], reverse=True)
            data['comments'].sort(key=lambda x: x['date'], reverse=True)
            
            user_file = user_data_dir / f"{user_id}.json"
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            user_files_created += 1
        
        print(f"Created {user_files_created} user data files")
        
        # Also create a simple user index for debugging
        user_index = []
        for user_id, username in self.members.items():
            user_index.append({
                'id': user_id,
                'name': username,
                'discussion_count': len(user_posts_map.get(user_id, {}).get('discussions', [])),
                'comment_count': len(user_posts_map.get(user_id, {}).get('comments', []))
            })
        
        index_file = self.output_path / "assets" / "js" / "user-index.js"
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(f"window.userIndex = {json.dumps(user_index, ensure_ascii=False)};")
        
        print(f"Written user index with {len(user_index)} users")


    def generate_about_page(self):
        """Generate an About page for the forum export"""
        # Load layout and content templates
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('about.html')

        cssversion = self.get_cssversion()
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Render content first
        main_content = content_template.format()

        # Then render layout with content
        html_content = layout_template.format(
            title="About",
            cssversion=cssversion,
            buildversion=self.buildversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
            canonical_url=f"{self.site_url}about.html",
            robot_block="",
            extrahead="",
            extrafoot=""
        )
        
        output_file = self.output_path / "about.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated About page: {output_file}")


    def generate_404_page(self):
        """Generate 404 page for the forum export"""
        # Load layout and content templates
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('404.html')

        cssversion = self.get_cssversion()
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Render content first
        main_content = content_template.format()

        # Then render layout with content
        html_content = layout_template.format(
            title="404 Page Not Found",
            cssversion=cssversion,
            buildversion=self.buildversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
            canonical_url=f"{self.site_url}404.html",
            robot_block="",
            extrahead="",
            extrafoot=""
        )
        
        output_file = self.output_path / "404.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated 404 page: {output_file}")



    def generate_your_posts_page(self, discussions_meta):
        """Generate a page where users can find and download their posts"""
        
        # Load layout and content templates
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('your-posts.html')

        cssversion = self.get_cssversion()
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Render content first (no JavaScript replacement needed)
        main_content = content_template.format()

        # Prepare extrafoot with both scripts
        extrafoot = f"""
        <script src="/assets/js/user-search-index.js?v={self.buildversion}"></script>
        <script src="/assets/js/user-chunk-mapping.js?v={self.buildversion}"></script>
        <script src="/assets/js/your-posts-fast.js?v={self.buildversion}"></script>
        """

        # Then render layout with content
        html_content = layout_template.format(
            title="Your Posts",
            cssversion=cssversion,
            buildversion=self.buildversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
            canonical_url = f"{self.site_url}your-posts.html",
            robot_block="",
            extrahead="",
            extrafoot=extrafoot
        )
        
        with open(self.output_path / "your-posts.html", 'w', encoding='utf-8') as f:
            f.write(html_content)


    def generate_homepage(self, discussions_meta):
        """Generate paginated homepage with navigation at top and bottom"""
        discussions_meta.sort(key=lambda x: x['date'], reverse=True)
        
        # Split into pages
        page_size = self.config['homepage_page_size']
        total_pages = (len(discussions_meta) + page_size - 1) // page_size
        
        def generate_pagination_html(current_page, total_pages):
            """Generate pagination HTML for both top and bottom"""
            pagination_html = '<div class="pagination">'
            
            # Previous button
            if current_page > 0:
                prev_url = "/index.html" if current_page == 1 else f"/page-{current_page}.html"
                pagination_html += f'<a href="{prev_url}" class="pagination-arrow">← Previous</a> '
            else:
                pagination_html += '<span class="pagination-arrow disabled">← Previous</span> '
            
            # Page numbers
            pagination_html += f'<span class="page-info">Page {current_page + 1} of {total_pages}</span>'
            
            # Next button
            if current_page < total_pages - 1:
                next_url = f"/page-{current_page + 2}.html"
                pagination_html += f' <a href="{next_url}" class="pagination-arrow">Next →</a>'
            else:
                pagination_html += ' <span class="pagination-arrow disabled">Next →</span>'
            
            pagination_html += '</div>'
            return pagination_html
        
        for page_num in range(total_pages):
            start_idx = page_num * page_size
            end_idx = start_idx + page_size
            page_discussions = discussions_meta[start_idx:end_idx]
            
            # Generate discussions list
            discussions_list = ""
            for disc in page_discussions:
                author_name = self.get_username(disc['author_id'])
                cat_id = disc['category_id']
                category_name = self.categories.get(cat_id, {}).get('Name', 'Uncategorized') if cat_id else 'Uncategorized'
                if cat_id:
                    cat_slug = self.generate_slug(category_name)
                    category_html = f'<a href="/categories/{cat_id}-{cat_slug}.html">{html.escape(category_name)}</a>'
                else:
                    category_html = html.escape(category_name)

                discussions_list += f"""
                    <article class="discussion-summary">
                        <h3><a href="{disc['url']}">{html.escape(disc['title'])}</a></h3>
                        <div class="discussion-meta">
                            <span class="author">by {html.escape(author_name)}</span>
                            <span class="date">{self.format_date(disc['date'])}</span>
                            <span class="comments">{disc['comment_count']} comments</span>
                            <span class="category">{category_html}</span>
                        </div>
                    </article>
                """

            # Load layout and content templates
            layout_template = self.load_template('layout.html')
            content_template = self.load_template('homepage.html')

            cssversion = self.get_cssversion()
            header_html = self.load_template('header.html')
            footer_html = self.load_template('footer.html')

            # Render content first
            main_content = content_template.format(
                total_discussions=len(discussions_meta),
                top_pagination=generate_pagination_html(page_num, total_pages),
                bottom_pagination=generate_pagination_html(page_num, total_pages),
                start_idx=start_idx + 1,
                end_idx=min(end_idx, len(discussions_meta)),
                discussions_list=discussions_list
            )

            # Then render layout with content
            html_content = layout_template.format(
                title=f"Page {page_num + 1}",
                cssversion=cssversion,
                buildversion=self.buildversion,
                header=header_html,
                main=main_content,
                footer=footer_html,
                #canonical_url = f"{self.site_url}",
                canonical_url = self.site_url + (f"/page-{page_num + 1}.html" if page_num else ""),
                robot_block="",
                extrahead="",
                extrafoot=""
            )
            
            # Save file
            filename = "index.html" if page_num == 0 else f"page-{page_num + 1}.html"
            with open(self.output_path / filename, 'w', encoding='utf-8') as f:
                f.write(html_content)

    
    def generate_search_page(self, discussions_meta):
        """Generate search page with category filtering"""
        search_data = []
        
        for disc in discussions_meta:
            # Only include discussion titles and authors for search
            discussion = self.discussions[disc['id']]
            
            # Get category info
            category_id = discussion.get('CategoryID')
            category_name = "Uncategorized"
            if category_id and category_id in self.categories:
                category_name = self.categories[category_id]['Name']
            
            search_data.append({
                'title': discussion['Name'],
                'author': self.get_username(discussion['InsertUserID']),
                'url': disc['url'],
                'type': 'discussion',
                'date': discussion['DateInserted'],
                'comment_count': len(self.comments.get(disc['id'], [])),
                'id': f"discussion-{disc['id']}",
                'category_id': category_id,  # Add category ID
                'category_name': category_name  # Add category name
            })
        
        # Generate categories list for dropdown
        categories_list = []
        for cat_id, cat_info in self.categories.items():
            # Skip Moderators category
            if cat_info['Name'] == 'Moderators' or cat_info['Name'] == 'Editors: Private Group':
                continue

            categories_list.append({
                'id': cat_id,
                'name': cat_info['Name']
            })
        
        # Sort categories by name
        categories_list.sort(key=lambda x: x['name'])
        
        # Create a fast lookup object for categories
        category_lookup = {cat['id']: cat['name'] for cat in categories_list}
        
        # Write categories data separately (small file)
        categories_js_content = f"""
    window.searchCategories = {json.dumps(categories_list, ensure_ascii=False)};
    window.categoryLookup = {json.dumps(category_lookup, ensure_ascii=False)};
    """
        
        with open(self.output_path / "assets" / "js" / "categories-data.js", 'w', encoding='utf-8') as f:
            f.write(categories_js_content)
        
        # Write search data separately (large file)
        search_js_content = f"""
    window.searchData = {json.dumps(search_data, ensure_ascii=False)};
    """
        
        with open(self.output_path / "assets" / "js" / "search-data.js", 'w', encoding='utf-8') as f:
            f.write(search_js_content)
        
        # Load layout and content templates
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('search.html')

        cssversion = self.get_cssversion()
        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Render content first
        main_content = content_template.format()

        # Prepare extrafoot with scripts
        extrafoot = f"""
        <script src="/assets/js/categories-data.js?v={self.buildversion}"></script>
        <script src="/assets/js/search-data.js?v={self.buildversion}"></script>
        <script src="/assets/js/search.js?v={self.buildversion}"></script>
        """

        # Then render layout with content
        html_content = layout_template.format(
            title="Search",
            cssversion=cssversion,
            buildversion=self.buildversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
            canonical_url = f"{self.site_url}search.html",
            robot_block="",
            extrahead="",
            extrafoot=extrafoot
        )

        with open(self.output_path / "search.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
    

    def convert(self, html_only=False):
        """Main conversion method with optional html_only mode"""
        print("Starting conversion...")

        if html_only is None:
            html_only = self.config['html_only_mode']

        if not html_only:
            # Load member data first
            self.load_member_data()

            # Create output directory structure
            try:
                (self.output_path / "discussions").mkdir(parents=True, exist_ok=True)
                (self.output_path / "assets" / "css").mkdir(parents=True, exist_ok=True)
                (self.output_path / "assets" / "js").mkdir(parents=True, exist_ok=True)
                (self.output_path / "assets" / "img").mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                print(f"Permission denied creating directories: {e}")
                return

            # Load forum data
            self.load_data()

            if not self.discussions:
                print("No discussions loaded. Check the export path.")
                return

            # Save the processed data for html-only mode
            self._save_processed_data()

            # Pass 1: build discussions_meta (no HTML written yet), sort newest-first
            print("Building discussions metadata (pass 1)...")
            discussions_meta = [
                self._extract_discussion_meta(d)
                for d in self.discussions.values()
            ]
            discussions_meta.sort(key=lambda x: x['date'], reverse=True)

            # Pass 2: generate HTML with incremental build support
            print("Generating discussion pages (pass 2)...")
            manifest = self._load_build_manifest()
            template_hash = self._compute_template_hash()
            templates_changed = manifest.get('template_hash') != template_hash
            if templates_changed:
                print("Templates changed — regenerating all discussion pages")
            new_manifest = {'template_hash': template_hash, 'discussions': {}}
            old_disc_hashes = manifest.get('discussions', {})

            # Build O(1) lookup: disc_id -> meta
            meta_by_id = {m['id']: m for m in discussions_meta}

            generated = 0
            skipped = 0
            for discussion in self.discussions.values():
                disc_id = discussion['DiscussionID']
                meta = meta_by_id[disc_id]
                disc_hash = self._compute_discussion_hash(disc_id)
                new_manifest['discussions'][str(disc_id)] = disc_hash

                output_file = self.output_path / "discussions" / f"{disc_id}-{meta['slug']}.html"
                old_hash = old_disc_hashes.get(str(disc_id))
                if not templates_changed and old_hash == disc_hash and output_file.exists():
                    skipped += 1
                    continue

                print(f"Generating HTML for discussion: {discussion['Name']}")
                self.generate_discussion_page(discussion, page_num=1)
                if meta['total_pages'] > 1:
                    for page_num in range(2, meta['total_pages'] + 1):
                        self.generate_discussion_page(discussion, page_num=page_num)
                generated += 1

            self._save_build_manifest(new_manifest)
            print(f"Generated {generated} discussions, skipped {skipped} unchanged")

        else:
            print("HTML-only mode: loading previously processed data...")
            if not self._load_processed_data():
                print("ERROR: No previously processed data found.")
                print("Please run full conversion first: python3 convert_forum.py")
                return

            # Rebuild discussions_meta from loaded data (no HTML written)
            print("Rebuilding discussions metadata...")
            discussions_meta = [
                self._extract_discussion_meta(d)
                for d in self.discussions.values()
            ]
            discussions_meta.sort(key=lambda x: x['date'], reverse=True)

        # Copy static assets
        self.copy_assets()

        # From here down runs in both modes but uses pre-built discussions_meta
        print("Generating site infrastructure...")

        # Generate user posts page and data (full mode only)
        if not html_only:
            print("Generating user posts data...")
            self.generate_user_posts_data(discussions_meta)
            self.generate_user_search_index(discussions_meta)
            self.generate_user_data_chunks(discussions_meta)
            print("Generating member pages...")
            self.generate_member_pages(discussions_meta)
        else:
            print("Skipping user posts data and member pages in html-only mode...")

        self.generate_about_page()
        self.generate_404_page()
        self.generate_your_posts_page(discussions_meta)

        # Generate indexes (quick to regenerate)
        self.generate_homepage(discussions_meta)
        self.generate_search_page(discussions_meta)
        self.generate_category_pages(discussions_meta)

        count = self.write_sitemap(self.site_url, self.output_path)
        print(f"sitemap.xml written with {count} URLs at {self.output_path / 'sitemap.xml'}")

        print(f"Conversion complete! Output in: {self.output_path}")
        print(f"Processed {len(discussions_meta)} discussions")

    def _save_processed_data(self):
        """Save processed data to JSON files for html-only mode"""
        data_dir = self.output_path / "processed_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON will automatically convert int keys to strings, which is fine
        # We'll handle the conversion back when loading
        with open(data_dir / "discussions.json", 'w', encoding='utf-8') as f:
            json.dump(self.discussions, f, ensure_ascii=False, indent=2)
        
        with open(data_dir / "comments.json", 'w', encoding='utf-8') as f:
            json.dump(self.comments, f, ensure_ascii=False, indent=2)
        
        with open(data_dir / "members.json", 'w', encoding='utf-8') as f:
            json.dump(self.members, f, ensure_ascii=False, indent=2)
        
        # Save categories data
        with open(data_dir / "categories.json", 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, ensure_ascii=False, indent=2)

        # Save member profiles
        with open(data_dir / "member_profiles.json", 'w', encoding='utf-8') as f:
            json.dump(self.member_profiles, f, ensure_ascii=False, indent=2)

        print(f"Saved processed data to {data_dir}")

    def _load_processed_data(self):
        """Load previously processed data for html-only mode"""
        data_dir = self.output_path / "processed_data"
        
        if not data_dir.exists():
            return False
        
        try:
            with open(data_dir / "discussions.json", 'r', encoding='utf-8') as f:
                discussions_data = json.load(f)
                # Convert string keys back to integers
                self.discussions = {int(k): v for k, v in discussions_data.items()}
            
            with open(data_dir / "comments.json", 'r', encoding='utf-8') as f:
                comments_data = json.load(f)
                # Convert string keys back to integers for comments too
                self.comments = {int(k): v for k, v in comments_data.items()}
            
            with open(data_dir / "members.json", 'r', encoding='utf-8') as f:
                members_data = json.load(f)
                # Convert string keys back to integers for members
                self.members = {int(k): v for k, v in members_data.items()}
            
            # Load categories data
            with open(data_dir / "categories.json", 'r', encoding='utf-8') as f:
                categories_data = json.load(f)
                self.categories = {int(k): v for k, v in categories_data.items()}

            # Load member profiles (optional — may not exist in older builds)
            profiles_path = data_dir / "member_profiles.json"
            if profiles_path.exists():
                with open(profiles_path, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    self.member_profiles = {int(k): v for k, v in profiles_data.items()}

            print(f"Loaded {len(self.discussions)} discussions, {len(self.comments)} comment threads, {len(self.members)} members, {len(self.categories)} categories")
            return True
        except Exception as e:
            print(f"Error loading processed data: {e}")
            return False


    def write_sitemap(self, site_url: str, root_dir: str | Path) -> int:
        site_url = site_url.rstrip("/")
        root = Path(root_dir)

        def url_for(path: Path) -> str:
            rel = path.relative_to(root).as_posix()
            if rel == "index.html":
                return f"{site_url}/"
            if rel.endswith("/index.html"):
                return f"{site_url}/{rel[:-10]}/"
            return f"{site_url}/{rel}"

        def is_noindex(html_path: Path) -> bool:
            # cheap/robust enough for your generator output
            s = html_path.read_text(encoding="utf-8", errors="ignore").lower()
            return (
                '<meta name="robots"' in s and "noindex" in s
            ) or (
                '<meta name="googlebot"' in s and "noindex" in s
            )

        html_files = sorted(root.rglob("*.html"))

        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

        included = 0
        for f in html_files:
            if is_noindex(f):
                continue
            lines.append("  <url>")
            lines.append(f"    <loc>{url_for(f)}</loc>")
            lines.append("  </url>")
            included += 1

        lines.append("</urlset>")

        (root / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")
        return included


def main():
    import sys
    
    # Allow custom config path
    config_path = None
    html_only = False
    
    # Parse command line arguments
    for arg in sys.argv[1:]:
        if arg == "html-only":
            html_only = True
        elif arg.endswith('.json'):
            config_path = arg
        elif arg == "--help":
            print("Usage: python convert_forum.py [html-only] [config.json]")
            return
    
    current_dir = Path(__file__).parent
    
    # Use provided config or default
    if config_path is None:
        config_path = current_dir / "config.json"
    
    converter = PlushForumsConverter(config_path)
    converter.convert(html_only=html_only)


if __name__ == "__main__":
    main()