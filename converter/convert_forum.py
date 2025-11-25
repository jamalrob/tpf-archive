#!/usr/bin/env python3
"""
PlushForums to Static HTML Converter
"""

import json
import os
import re
import csv
from datetime import datetime
from pathlib import Path
import html

class PlushForumsConverter:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        
        # Load config directly - will crash if file missing (good for visibility)
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.export_path = Path(self.config['export_path']).resolve()
        self.output_path = Path(self.config['output_path']).resolve()
        
        # Initialize other attributes
        self.discussions = {}
        self.comments = {}
        self.members = {}
        self.categories = {}
        self._cssversion = None
        self._template_cache = {}  # ← Store templates here
        
        print(f"Export path: {self.export_path}")
        print(f"Output path: {self.output_path}")


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
                'excerpt': discussion.get('Body', '')[:200] + '...' if len(discussion.get('Body', '')) > 200 else discussion.get('Body', '')
            })
        
        # Build comments by user (O(n) instead of O(n×m))  
        for disc_id, comments in self.comments.items():
            for comment in comments:
                user_id = comment['InsertUserID']
                if user_id not in user_comments:
                    user_comments[user_id] = []
                
                disc_title = self.discussions[disc_id]['Name'] if disc_id in self.discussions else "Unknown Discussion"
                user_comments[user_id].append({
                    'id': comment['CommentID'],
                    'discussion_id': disc_id,
                    'discussion_title': disc_title,
                    'date': comment['DateInserted'],
                    'url': f"/discussions/{disc_id}-{self.generate_slug(disc_title)}.html#comment-{comment['CommentID']}",
                    'excerpt': comment.get('Body', '')[:150] + '...' if len(comment.get('Body', '')) > 150 else comment.get('Body', '')
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
                
                # Only store the ID and username
                self.members[user_id] = username
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
    
    def get_username(self, user_id):
        """Get username from user ID, fallback to 'User {id}' if not found"""
        if user_id in self.members:
            return self.members[user_id]
        else:
            print(f"DEBUG: User ID {user_id} not found in members data")
            print(f"DEBUG: Available user IDs: {list(self.members.keys())[:10]}...")  # Show first 10
            return f"User {user_id}"
    
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
            text, flags=re.DOTALL
        )
        
        # [quote="UserName"]...[/quote] (without ID)
        text = re.sub(
            r'\[quote="([^"]+)"\](.*?)\[/quote\]',
            r'<blockquote class="user-quote"><cite>\1:</cite>\2</blockquote>',
            text, flags=re.DOTALL
        )
        
        # Rest of your existing BBCode processing remains the same...
        # Step 3: Convert simple quotes
        text = re.sub(
            r'\[quote\](.*?)\[/quote\]',
            r'<blockquote class="simple-quote">\1</blockquote>',
            text, flags=re.DOTALL
        )
        
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
        """Convert @"username" to clickable mention if user exists"""
        username = match.group(1)
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
        return slug[:50]
    

    def generate_discussion_page(self, discussion):
        disc_id = discussion['DiscussionID']
        slug = self.generate_slug(discussion['Name'])
        
        # Get comments for this discussion
        discussion_comments = self.comments.get(disc_id, [])
        
        # Convert discussion body with enhanced BBCode
        discussion_body = self.convert_plush_bbcode(discussion['Body'], disc_id)
        
        # Get author username
        author_id = discussion['InsertUserID']
        author_name = self.get_username(author_id)
        
        # Generate comments HTML
        comments_html = ""
        for comment in discussion_comments:
            comment_body = self.convert_plush_bbcode(comment['Body'], disc_id)
            comment_author_name = self.get_username(comment['InsertUserID'])
            
            comments_html += f"""
                <div class="comment" id="comment-{comment['CommentID']}">
                    <div class="comment-meta">
                        <span class="author">{html.escape(comment_author_name)}</span>
                        <span class="date">{self.format_date(comment['DateInserted'])}</span>
                        <span class="comment-id"><a href="#comment-{comment['CommentID']}">#{comment['CommentID']}</a></span>
                        <span class="likes">{comment.get('Likes', 0)} likes</span>
                    </div>
                    <div class="comment-content">
                        {comment_body}
                    </div>
                </div>"""
        
        # Load layout and content templates
        layout_template = self.load_template('layout.html')
        content_template = self.load_template('discussion.html')

        cssversion = self.get_cssversion()

        header_html = self.load_template('header.html')
        footer_html = self.load_template('footer.html')

        # Render content first
        main_content = content_template.format(
            discussion_title=html.escape(discussion['Name']),
            author_name=html.escape(author_name),
            discussion_date=self.format_date(discussion['DateInserted']),
            view_count=discussion['CountViews'],
            comment_count=len(discussion_comments),
            discussion_body=discussion_body,
            comments_html=comments_html
        )

        # Then render layout with content
        html_content = layout_template.format(
            title=html.escape(discussion['Name']),
            cssversion=cssversion,
            extrahead="",
            extrafoot="",
            header=header_html,
            main=main_content,
            footer=footer_html
        )
        
        # Write file
        output_file = self.output_path / "discussions" / f"{disc_id}-{slug}.html"
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
            'category_name': self.categories.get(discussion.get('CategoryID'), {}).get('Name', 'Uncategorized')
        }
    
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
            header=header_html,
            main=main_content,
            footer=footer_html,
            extrahead="",
            extrafoot=""
        )
        
        output_file = self.output_path / "about.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated About page: {output_file}")


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
        <script src="/assets/js/user-search-index.js?v={cssversion}"></script>
        <script src="/assets/js/user-chunk-mapping.js?v={cssversion}"></script>
        <script src="/assets/js/your-posts-fast.js?v={cssversion}"></script>
        """

        # Then render layout with content
        html_content = layout_template.format(
            title="Your Posts",
            cssversion=cssversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
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
                category_name = self.categories.get(disc['category_id'], {}).get('Name', 'Uncategorized')
                
                discussions_list += f"""
                    <article class="discussion-summary">
                        <h3><a href="{disc['url']}">{html.escape(disc['title'])}</a></h3>
                        <div class="discussion-meta">
                            <span class="author">by {html.escape(author_name)}</span>
                            <span class="date">{self.format_date(disc['date'])}</span>
                            <span class="comments">{disc['comment_count']} comments</span>
                            <span class="category">{html.escape(category_name)}</span>
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
                header=header_html,
                main=main_content,
                footer=footer_html,
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
        <script src="/assets/js/categories-data.js?v={cssversion}"></script>
        <script src="/assets/js/search-data.js?v={cssversion}"></script>
        <script src="/assets/js/search.js?v={cssversion}"></script>
        """

        # Then render layout with content
        html_content = layout_template.format(
            title="Search",
            cssversion=cssversion,
            header=header_html,
            main=main_content,
            footer=footer_html,
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
            
            # Generate discussion pages (only in full mode)
            print("Generating discussion pages...")
            discussions_meta = []
            for disc_id, discussion in self.discussions.items():
                print(f"Generating HTML for discussion: {discussion['Name']}")
                meta = self.generate_discussion_page(discussion)
                discussions_meta.append(meta)
                
        else:
            print("HTML-only mode: loading previously processed data...")
            if not self._load_processed_data():
                print("ERROR: No previously processed data found.")
                print("Please run full conversion first: python3 convert_forum.py")
                return
            
            # In html-only mode, we need to rebuild discussions_meta without regenerating pages
            print("Rebuilding discussions metadata...")
            discussions_meta = []
            for disc_id, discussion in self.discussions.items():
                # Recreate the meta without regenerating the HTML page
                disc_id = discussion['DiscussionID']
                slug = self.generate_slug(discussion['Name'])
                discussion_comments = self.comments.get(disc_id, [])
                
                discussions_meta.append({
                    'id': disc_id,
                    'title': discussion['Name'],
                    'date': discussion['DateInserted'],
                    'slug': slug,
                    'url': f"/discussions/{disc_id}-{slug}.html",
                    'comment_count': len(discussion_comments),
                    'author_id': discussion['InsertUserID'],
                    # ADD THESE TWO LINES:
                    'category_id': discussion.get('CategoryID'),
                    'category_name': self.categories.get(discussion.get('CategoryID'), {}).get('Name', 'Uncategorized')
                })
        
        # Copy static assets
        self.copy_assets()

        # From here down runs in both modes but uses pre-built discussions_meta
        print("Generating site infrastructure...")
        
       
        # Generate user posts page and data (this should also check html_only mode)
        if not html_only:
            print("Generating user posts data...")
            self.generate_user_posts_data(discussions_meta)
            self.generate_user_search_index(discussions_meta)  # Add this
            self.generate_user_data_chunks(discussions_meta)   # Add this            
        else:
            print("Skipping user posts data generation in html-only mode...")
        
        self.generate_about_page()
        self.generate_your_posts_page(discussions_meta)

        # Generate indexes (these are quick to regenerate)
        self.generate_homepage(discussions_meta)
        self.generate_search_page(discussions_meta)

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
        
        # ADD THIS: Save categories data
        with open(data_dir / "categories.json", 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, ensure_ascii=False, indent=2)
        
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
            
            # ADD THIS: Load categories data
            with open(data_dir / "categories.json", 'r', encoding='utf-8') as f:
                categories_data = json.load(f)
                # Convert string keys back to integers for categories
                self.categories = {int(k): v for k, v in categories_data.items()}
            
            print(f"Loaded {len(self.discussions)} discussions, {len(self.comments)} comment threads, {len(self.members)} members, {len(self.categories)} categories")
            return True
        except Exception as e:
            print(f"Error loading processed data: {e}")
            return False

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