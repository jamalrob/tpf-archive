#!/usr/bin/env python3
"""
Private Message Converter - Text File Output
"""

import json
import re
from datetime import datetime
from pathlib import Path

class PrivateMessageConverter:
    def __init__(self, export_path, output_path):
        self.export_path = Path(export_path).resolve()
        self.output_path = Path(output_path).resolve()
        self.conversations = {}
        self.messages = {}
        self.members = {}

    def load_member_data(self):
        """Load member data from JSON files"""
        print("Loading member data...")
        
        members_path = self.export_path / "members"
        if not members_path.exists():
            print(f"ERROR: Members path not found: {members_path}")
            return
        
        member_files = list(members_path.rglob("*.json"))
        
        for json_file in member_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    member_data = json.load(f)
                
                user_id = member_data['UserID']
                username = member_data['Name']
                self.members[user_id] = username
                
            except Exception as e:
                print(f"Error loading member file {json_file}: {e}")
        
        print(f"Loaded {len(self.members)} members")

    def load_conversation_data(self):
        """Load all conversation data"""
        print("Loading conversations...")
        
        conversations_path = self.export_path / "conversations"
        if not conversations_path.exists():
            print(f"ERROR: Conversations path not found: {conversations_path}")
            return
            
        for json_file in conversations_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    conversations_batch = json.load(f)
                    for conversation in conversations_batch:
                        self.conversations[conversation['ConversationID']] = conversation
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
        
        print(f"Loaded {len(self.conversations)} conversations")

    def load_message_data(self):
        """Load all message data"""
        print("Loading messages...")
        
        messages_path = self.export_path / "messages"
        if not messages_path.exists():
            print(f"ERROR: Messages path not found: {messages_path}")
            return
            
        for batch_dir in messages_path.iterdir():
            if batch_dir.is_dir():
                for json_file in batch_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            messages_batch = json.load(f)
                            for message in messages_batch:
                                conv_id = message['ConversationID']
                                if conv_id not in self.messages:
                                    self.messages[conv_id] = []
                                self.messages[conv_id].append(message)
                    except Exception as e:
                        print(f"Error loading {json_file}: {e}")
        
        # Sort messages by date within each conversation
        for conv_id in self.messages:
            self.messages[conv_id].sort(key=lambda x: x['DateInserted'])
        
        print(f"Loaded messages for {len(self.messages)} conversations")

    def fix_windows_1252_encoding(self, text):
        """Fix Windows-1252 encoded characters"""
        if not text:
            return text
        
        windows_1252_mapping = {
            '\u0080': '€', '\u0081': '', '\u0082': '‚', '\u0083': 'ƒ', '\u0084': '„', 
            '\u0085': '…', '\u0086': '†', '\u0087': '‡', '\u0088': 'ˆ', '\u0089': '‰',
            '\u008A': 'Š', '\u008B': '‹', '\u008C': 'Œ', '\u008D': '', '\u008E': 'Ž',
            '\u008F': '', '\u0090': '', '\u0091': '‘', '\u0092': '’', '\u0093': '“',
            '\u0094': '”', '\u0095': '•', '\u0096': '–', '\u0097': '—', '\u0098': '˜',
            '\u0099': '™', '\u009A': 'š', '\u009B': '›', '\u009C': 'œ', '\u009D': '',
            '\u009E': 'ž', '\u009F': 'Ÿ'
        }
        
        for win_char, unicode_char in windows_1252_mapping.items():
            text = text.replace(win_char, unicode_char)
        
        return text

    def format_date(self, date_string):
        """Format date string for display"""
        try:
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return date_string

    def get_username(self, user_id):
        """Get username from user ID"""
        return self.members.get(user_id, f"User {user_id}")

    def get_user_conversations(self, user_id):
        """Get all conversations for a specific user"""
        user_convos = []
        
        for conv_id, conversation in self.conversations.items():
            contributors = conversation.get('Contributors', [])
            if user_id in contributors:
                user_convos.append(conversation)
        
        # Sort by most recent activity (by last message date)
        user_convos.sort(key=lambda x: self.get_conversation_last_date(x['ConversationID']), reverse=True)
        return user_convos

    def get_conversation_last_date(self, conv_id):
        """Get the last message date for a conversation"""
        messages = self.messages.get(conv_id, [])
        if messages:
            return messages[-1]['DateInserted']
        return "0000-00-00"

    def generate_conversation_text(self, conversation, user_id):
        """Generate text content for a single conversation"""
        conv_id = conversation['ConversationID']
        messages = self.messages.get(conv_id, [])
        
        # Get other participants (excluding the current user)
        participants = [
            self.get_username(pid) for pid in conversation['Contributors'] 
            if pid != user_id
        ]
        
        # Build text content
        text_content = f"CONVERSATION {conv_id}\n"
        text_content += "=" * 50 + "\n"
        text_content += f"Participants: {', '.join(participants)}\n"
        text_content += f"Total messages: {len(messages)}\n"
        text_content += "=" * 50 + "\n\n"
        
        for i, message in enumerate(messages, 1):
            # Fix encoding and clean up the message
            message_body = self.fix_windows_1252_encoding(message['Body'])
            message_body = message_body.replace('\r\n', '\n').replace('\r', '\n').strip()
            
            author_name = self.get_username(message['InsertUserID'])
            date_str = self.format_date(message['DateInserted'])
            
            text_content += f"MESSAGE {i}/{len(messages)}\n"
            text_content += f"From: {author_name}\n"
            text_content += f"Date: {date_str}\n"
            text_content += "-" * 40 + "\n"
            text_content += message_body + "\n"
            text_content += "=" * 50 + "\n\n"
        
        return text_content

    def generate_user_dms(self, user_identifier):
        """Generate all DM text files for a specific user"""
        # Load all data
        self.load_member_data()
        self.load_conversation_data()
        self.load_message_data()
        
        # Find user ID
        user_id = None
        if isinstance(user_identifier, int) or user_identifier.isdigit():
            user_id = int(user_identifier)
        else:
            # Look up by username
            for uid, username in self.members.items():
                if username.lower() == user_identifier.lower():
                    user_id = uid
                    break
        
        if not user_id:
            print(f"ERROR: User '{user_identifier}' not found")
            return
        
        username = self.get_username(user_id)
        print(f"Generating DMs for {username} (ID: {user_id})")
        
        # Get user's conversations
        user_convos = self.get_user_conversations(user_id)
        print(f"Found {len(user_convos)} conversations")
        
        # Create output directory
        user_output_dir = self.output_path / f"user-{user_id}-{username.replace(' ', '_')}"
        user_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate conversation text files
        for conversation in user_convos:
            conv_id = conversation['ConversationID']
            text_content = self.generate_conversation_text(conversation, user_id)
            
            # Get participant names for filename
            participants = [
                self.get_username(pid) for pid in conversation['Contributors'] 
                if pid != user_id
            ]
            participant_names = "_".join([p.replace(' ', '_') for p in participants])
            
            # Save text file
            output_file = user_output_dir / f"conversation_{conv_id}_{participant_names}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            print(f"Generated: {output_file}")
        
        # Generate master file with all conversations
        self.generate_master_file(user_id, user_convos, user_output_dir, username)
        
        print(f"Done! Generated {len(user_convos)} conversation files for {username}")

    def generate_master_file(self, user_id, conversations, output_dir, username):
        """Generate a master file containing all conversations"""
        master_content = f"PRIVATE MESSAGES - {username}\n"
        master_content += "=" * 60 + "\n"
        master_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        master_content += f"Total conversations: {len(conversations)}\n"
        master_content += "=" * 60 + "\n\n"
        
        for conversation in conversations:
            conv_id = conversation['ConversationID']
            text_content = self.generate_conversation_text(conversation, user_id)
            master_content += text_content
            master_content += "\n" + "=" * 80 + "\n\n"
        
        # Save master file
        master_file = output_dir / f"all_conversations_{username.replace(' ', '_')}.txt"
        with open(master_file, 'w', encoding='utf-8') as f:
            f.write(master_content)
        
        print(f"Generated master file: {master_file}")

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python convert_dms.py <user_identifier> [output_path]")
        print("  user_identifier: User ID (number) or username")
        print("  output_path: Optional output directory (default: ./dm_output)")
        return
    
    user_identifier = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "./dm_output"
    
    current_dir = Path(__file__).parent
    EXPORT_PATH = current_dir.parent / "exports"
    OUTPUT_PATH = Path(output_path)
    
    print(f"Looking for export data in: {EXPORT_PATH}")
    print(f"Will output to: {OUTPUT_PATH}")
    
    converter = PrivateMessageConverter(EXPORT_PATH, OUTPUT_PATH)
    converter.generate_user_dms(user_identifier)

if __name__ == "__main__":
    main()