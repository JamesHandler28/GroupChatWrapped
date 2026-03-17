import sqlite3
import pandas as pd
from datetime import datetime

print("🔍 Connecting to chat.db...")

# 1. Connect to your copied iPhone database
try:
    conn = sqlite3.connect('chat.db')
except Exception as e:
    print("❌ Could not find chat.db! Make sure you copied it to the same folder as this script.")
    exit()

# 2. Find the most active chats so you can choose which one to extract
print("📊 Finding your most active group chats...\n")
chats_query = """
SELECT chat.ROWID, chat.chat_identifier, chat.display_name, COUNT(message.ROWID) as msg_count
FROM chat
JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
JOIN message ON chat_message_join.message_id = message.ROWID
GROUP BY chat.ROWID
ORDER BY msg_count DESC
LIMIT 15
"""

try:
    chats_df = pd.read_sql_query(chats_query, conn)
except Exception as e:
    print("❌ Error reading the database. If this happens, your backup might have been encrypted.")
    print(f"Error details: {e}")
    exit()

print("--- TOP 15 CHATS ---")
for index, row in chats_df.iterrows():
    # Apple sometimes leaves the display name blank if it's not a named group chat
    name = row['display_name'] if pd.notna(row['display_name']) and row['display_name'] else row['chat_identifier']
    print(f"[{row['ROWID']}] {name} ({row['msg_count']} messages)")

# 3. Ask the user which chat they want
print("\n")
chat_id = input("⌨️  Type the ID number (in brackets) of the chat you want to extract: ")

# 4. Extract all messages from that specific chat
print(f"\n🚀 Extracting messages for Chat ID {chat_id}...")
msg_query = f"""
SELECT
    message.date,
    handle.id AS Author,
    message.text AS Content,
    message.is_from_me
FROM message
LEFT JOIN handle ON message.handle_id = handle.ROWID
JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
WHERE chat_message_join.chat_id = {chat_id}
ORDER BY message.date ASC
"""
df = pd.read_sql_query(msg_query, conn)

# 5. Clean up the data
# Apple timestamps are seconds (or nanoseconds) since Jan 1, 2001. 
# Unix time starts Jan 1, 1970. The difference is 978,307,200 seconds.
def convert_apple_date(apple_time):
    if pd.isna(apple_time) or apple_time == 0: return None
    try:
        if apple_time > 1000000000000000: # iOS 11+ uses nanoseconds
            return datetime.fromtimestamp((apple_time / 1000000000) + 978307200)
        else: # Older iOS versions use seconds
            return datetime.fromtimestamp(apple_time + 978307200)
    except:
        return None

print("⚙️  Converting Apple timestamps and formatting CSV...")
df['Date'] = df['date'].apply(convert_apple_date)

# Fix the author names (Your own texts show up as blank, so we label them "Me")
df.loc[df['is_from_me'] == 1, 'Author'] = 'Me'

# Drop rows where there is no text (like system messages, missed calls, or image attachments)
df = df.dropna(subset=['Content', 'Date'])

# Keep only the columns your Streamlit app needs
final_df = df[['Date', 'Author', 'Content']]

# 6. Save it!
export_name = 'imessage_export.csv'
final_df.to_csv(export_name, index=False)

print(f"✅ SUCCESS! Exported {len(final_df)} messages to {export_name}!")