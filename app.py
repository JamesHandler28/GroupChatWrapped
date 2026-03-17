import streamlit as st
import pandas as pd
import requests
import re
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from nltk.corpus import stopwords
from collections import Counter
import altair as alt
import os
import json

try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')
    
# --- PARSER FUNCTIONS ---

def parse_whatsapp(file_content):
    """Parses WhatsApp exported text files (iOS and Android formats)."""
    pattern = r'^\[?(\d{1,2}\/\d{1,2}\/\d{2,4},? \s?\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?)\]?(?:\s-\s)?\s(.*?):\s(.*)$'
    
    data = []
    lines = file_content.split('\n')
    
    for line in lines:
        match = re.match(pattern, line)
        if match:
            date_str, author, message = match.groups()
            data.append([date_str, author, message])
        else:
            if data:
                data[-1][2] += "\n" + line

    df = pd.DataFrame(data, columns=['Date', 'Author', 'Content'])
    
    # Add an empty Reactions column so the Hall of Fame metric doesn't break
    df['Reactions'] = pd.NA 
    
    df = df[~df['Content'].str.contains("omitted", case=False)]
    return df

def parse_discord_txt(file_content):
    """Parses DiscordChatExporter text files."""
    header_pattern = r'^\[(.*?)\] (.*)$'
    data = []
    current_date = None
    current_author = None
    current_message_buffer = []
    
    lines = file_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('Guild:') or line.startswith('Channel:') or line == '===':
            continue
        
        match = re.match(header_pattern, line)
        if match:
            if current_date and current_author:
                data.append([current_date, current_author, " ".join(current_message_buffer)])
            
            current_date = match.group(1)
            raw_author = match.group(2)
            current_author = raw_author.replace('(pinned)', '').strip()
            current_message_buffer = []
        else:
            if current_date and current_author:
                current_message_buffer.append(line)
    
    if current_date and current_author:
        data.append([current_date, current_author, " ".join(current_message_buffer)])
        
    df = pd.DataFrame(data, columns=['Date', 'Author', 'Content'])
    
    # Add an empty Reactions column so the Hall of Fame metric doesn't break
    df['Reactions'] = pd.NA 
    
    return df

def parse_instagram_json(file_content):
    """Parses Instagram message_1.json export files."""
    data = json.loads(file_content)
    parsed_data = []

    # Instagram stores the actual texts in a 'messages' array
    messages = data.get('messages', [])

    for msg in messages:
        # Skip system actions (like "User named the group") that have no sender
        if 'sender_name' not in msg or 'timestamp_ms' not in msg:
            continue

        author = msg['sender_name']
        content = msg.get('content', '')

        # Fix Instagram's weird mojibake encoding for emojis and special characters
        try:
            author = author.encode('latin1').decode('utf8')
            content = content.encode('latin1').decode('utf8')
        except:
            pass

        if not content:
            continue

        # Instagram uses milliseconds for its dates
        date = pd.to_datetime(msg['timestamp_ms'], unit='ms')

        # Count reactions if they exist!
        reactions = msg.get('reactions', [])
        reaction_count = len(reactions) if isinstance(reactions, list) else 0

        parsed_data.append([date, author, content, reaction_count])

    return pd.DataFrame(parsed_data, columns=['Date', 'Author', 'Content', 'Reactions'])


def parse_telegram_json(file_content):
    """Parses Telegram Desktop result.json export files."""
    data = json.loads(file_content)
    parsed_data = []

    messages = data.get('messages', [])

    for msg in messages:
        # Only parse actual messages (skip "joined group" service messages)
        if msg.get('type') != 'message':
            continue

        date_str = msg.get('date')
        author = msg.get('from', 'Unknown')
        text_obj = msg.get('text', '')

        # Telegram sometimes splits text and links into a list of objects
        content = ""
        if isinstance(text_obj, str):
            content = text_obj
        elif isinstance(text_obj, list):
            for item in text_obj:
                if isinstance(item, str):
                    content += item
                elif isinstance(item, dict) and 'text' in item:
                    content += item['text']

        if not content.strip():
            continue

        # Add up any reactions
        reactions = msg.get('reactions', [])
        reaction_count = sum([r.get('count', 1) for r in reactions]) if isinstance(reactions, list) else 0

        parsed_data.append([date_str, author, content, reaction_count])

    return pd.DataFrame(parsed_data, columns=['Date', 'Author', 'Content', 'Reactions'])

st.set_page_config(page_title="Chat Wrapped", page_icon="🎁", layout="wide")

# --- CUSTOM CSS STYLING ---
st.markdown("""
<style>
    /* Hide the default Streamlit menu and footer for a clean app feel */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Make the Metric values MASSIVE to feel like an award show */
    [data-testid="stMetricValue"] {
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
    }
    
    /* Style the metric labels (1st Place, etc.) */
    [data-testid="stMetricLabel"] {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        color: #aaaaaa !important;
    }

    /* Add a subtle glow/shadow to the main tabs */
    [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    
    [data-baseweb="tab"] {
        background-color: #262730;
        border-radius: 8px 8px 0px 0px;
        padding: 10px 20px;
        box-shadow: 0px -2px 5px rgba(0,0,0,0.1);
    }
    
    /* Make subheaders pop */
    h3 {
        color: #FF4B4B !important; 
        font-weight: 700 !important;
    }
    
    /* Style the dividers */
    hr {
        margin-top: 2rem;
        margin-bottom: 2rem;
        border-top: 1px solid #333333;
    }
</style>
""", unsafe_allow_html=True)

gif_chat   = "https://media.giphy.com/media/XIqCQx02E1U9W/giphy.gif"         # Kermit Typing
gif_owl    = "https://media.giphy.com/media/13HgwGsXF0aiGY/giphy.gif"        # Adventure Time "Tired"
gif_ghost  = "https://media.giphy.com/media/jUwpNzg9IcyrK/giphy.gif"         # Homer Hedge
gif_party  = "https://media.giphy.com/media/GeimqsH0TLDt4tScGw/giphy.gif"    # Vibe Cat
gif_leader = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExY2xlZGdhZ3ExNm5jcXJ6eGxidzRsNzhlbm5zaGI2bWxxemVhYnhybSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/26vUGuV1WxhbkEKZy/giphy.gif"     # LEBRONNN
gif_smart  = "https://media.giphy.com/media/d3mlE7uhX8KFgEmY/giphy.gif"    # Roll Safe "Thinking"
gif_loud   = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdWNxMjY4YWdzZjJ3bmt2d3AzZ2ExanR0OGE0c2pvNDNoYzcwdXpteiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/26u49wAh0E8U3S4qA/giphy.gif" # Loud Noises
gif_search = "https://media.giphy.com/media/26n6WywJyh39n1pBu/giphy.gif"   # Detective
gif_dictionary = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaGhlb2Zib3U4dnFnaHFwYjlia3Q0N2lldXBzbTdydmU2b2d2bmJzbiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/WoWm8YzFQJg5i/giphy.gif" # Spongebob Dictionary
gif_double = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHE4ZWFmZ2k2NDdkYjJ4ZXExZDN3b2JpaWhyMTNxeXJ3dXVud3N0ZiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/5qF688fc8X2XCQ4R2L/giphy.gif" # 2 mad
gif_memer = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNzlobGR2eDJibDZta3E3Z3Zpa3RyOHM3OHoya3JzNHRiOWdobmJnZCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ueoUc3gJ5E6Fa/giphy.gif" # Cooking

if 'page' not in st.session_state:
    st.session_state.page = 'landing'
if 'chat_type' not in st.session_state:
    st.session_state.chat_type = None
    
def go_home():
    st.session_state.page = 'landing'
    st.session_state.chat_type = None

def select_whatsapp():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'whatsapp'
    
def select_discord_dm():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'discord_dm'

def select_discord_server():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'discord_server'
    
def select_instagram():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'instagram'

def select_telegram():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'telegram'

def select_imessage():
    st.session_state.page = 'upload'
    st.session_state.chat_type = 'imessage'
    
if st.session_state.page == 'landing':
    st.title("🎁 Group Chat Wrapped")
    st.write("Choose your platform to get started:")
    st.write("---")
    
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    
    with row1_col1:
        st.header("🟢 WhatsApp")
        st.write("For mobile groups.")
        st.info("Easy • Safe • .txt file")
        st.button("Select WhatsApp", on_click=select_whatsapp, width='stretch')
    
    with row1_col2:
        st.header("📸 Instagram")
        st.write("For IG group chats & DMs.")
        st.info("Easy • Safe • .json file")
        st.button("Select Instagram", on_click=select_instagram, width='stretch')

    with row1_col3:
        st.header("✈️ Telegram")
        st.write("For Telegram groups.")
        st.info("Easy • Safe • .json file")
        st.button("Select Telegram", on_click=select_telegram, width='stretch')
    
    st.write("")
    
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    
    with row2_col1:
        st.header("👾 Discord DM")
        st.write("For private group chats.")
        st.warning("Medium • Manual Export • Risky")
        st.button("Select Discord DM", on_click=select_discord_dm, width='stretch')
    
    with row2_col2:
        st.header("🤖 Discord Server")
        st.write("For large communities.")
        st.success("Medium • Invite Bot • Safe")
        st.button("Select Server", on_click=select_discord_server, width='stretch')
    
    with row2_col3:
        st.header("💬 Imessage")
        st.write("For mobile groups")
        st.warning("Medium • Backup Iphone • Slow")
        st.button("Select Imessage", on_click=select_imessage, width='stretch')

df = None

# --- UPLOAD PAGE LOGIC ---
if st.session_state.page == 'upload':
    st.button("← Back to Menu", on_click=go_home)
    
    df = None 
    
    # ---------------------------
    # WHATSAPP UPLOAD
    # ---------------------------
    if st.session_state.chat_type == 'whatsapp':
        st.header("🟢 WhatsApp Wrapped")
        st.write("Analyze your WhatsApp group chat history.")
        
        # INSTRUCTIONS
        with st.expander("📱 How to export your WhatsApp chat"):
            st.write("""
            **iPhone:**
            1. Open the group chat.
            2. Tap the group name at the top.
            3. Scroll down and tap **Export Chat**.
            4. Choose **Without Media**.
            5. Save the ZIP file or TXT file to your phone/computer.
            
            **Android:**
            1. Open the group chat.
            2. Tap the three dots (⋮) > **More** > **Export Chat**.
            3. Choose **Without Media**.
            
            **Note:** If you get a .zip file, unzip it first and upload the `_chat.txt` file inside.
            """)
            
        uploaded_file = st.file_uploader("Upload your exported .txt file", type=['txt'])
        
        if uploaded_file:
            try:
                string_data = uploaded_file.getvalue().decode("utf-8")
                df = parse_whatsapp(string_data)
                st.success("WhatsApp chat parsed successfully!")
            except Exception as e:
                st.error(f"Error parsing file. Make sure it's a standard WhatsApp export: {e}")

    # ---------------------------
    # DISCORD DM UPLOAD
    # ---------------------------
    elif st.session_state.chat_type == 'discord_dm':
        st.header("👾 Discord DM Wrapped")
        st.write("Analyze your private Discord DMs or Group DMs.")
        
        # INSTRUCTIONS
        with st.expander("🛠️ How to export Discord chats"):
            st.write("""
            Discord does not have a built-in export button. You need a safe, open-source tool called **DiscordChatExporter**.
            
            1. Download [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) (Windows/Mac/Linux).
            2. Log in and select the DM/Channel you want to wrap.
            3. Click **Export**.
            4. **IMPORTANT:** Select format as **Text (DiscordChatExporter)** or **CSV**.
            5. Upload the resulting file here.
            """)

        uploaded_file = st.file_uploader("Upload .txt or .csv export", type=['txt', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                    # Basic validation
                    if 'Content' not in df.columns or 'Date' not in df.columns:
                        st.error("CSV must have 'Date' and 'Content' columns.")
                        st.stop()
                else:
                    string_data = uploaded_file.getvalue().decode("utf-8")
                    df = parse_discord_txt(string_data)
                
                if df.empty:
                    st.error("File loaded but no messages found. Check the format.")
                else:
                    st.success("Discord chat parsed successfully!")
                    
            except Exception as e:
                st.error(f"Error parsing file: {e}")

    # ---------------------------
    # DISCORD SERVER UPLOAD
    # ---------------------------
    elif st.session_state.chat_type == 'discord_server':
        st.header("🤖 Discord Server Wrapped")
        st.write("Analyze massive community server channels.")
        
        # INSTRUCTIONS
        with st.expander("🛠️ How to export your Discord Server chat", expanded=True):
            st.write("""
            **Because Discord bans users for "self-botting", you must use a real bot to safely download server messages.**
            
            1. Click the button below to download our safe, open-source `bot_dumper.py` script.
            2. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a New Application.
            3. Go to the **Bot** tab, enable the **Message Content Intent**, and click **Reset Token** to get your Bot Token.
            4. Invite the bot to your server.
            5. Open `bot_dumper.py` in any text editor and paste your Token and the Channel ID you want to analyze.
            6. Run the script on your computer (`python bot_dumper.py`).
            7. Upload the resulting `discord_server_export.csv` file here!
            """)
            
            try:
                with open("bot_dumper.py", "rb") as file:
                    st.download_button(
                        label="🐍 Download bot_dumper.py",
                        data=file,
                        file_name="bot_dumper.py",
                        mime="text/x-python-script"
                    )
            except FileNotFoundError:
                st.error("Error: bot_dumper.py is missing from the app directory.")
        
        # TIME ESTIMATES
        with st.expander("⏱️ How long will the script take?", expanded=False):
            st.write("""
            Discord strictly limits how fast bots can read messages to prevent server strain. Our script automatically pauses to respect these limits, which means massive channels take time to download.
            
            **Rough Estimates:**
            * **10,000 messages:** ~1 - 2 minutes
            * **50,000 messages:** ~5 - 10 minutes
            * **100,000 messages:** ~15 - 20 minutes
            * **500,000 messages:** ~1.5 - 2 hours
            * **1,000,000+ messages:** 3+ hours
            
            💡 *Pro-tip: Just let the script run in the background! It prints its progress in your console and automatically saves your progress to the CSV every 5,000 messages in case it gets interrupted.*
            """)
                
        uploaded_file = st.file_uploader("Upload discord_server_export.csv", type=['csv'])
        
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                if df.empty:
                    st.error("File loaded, but no valid messages were found.")
                else:
                    st.success("Discord Server chat parsed successfully!")
            except Exception as e:
                st.error(f"Error parsing CSV: {e}")
    
    # ---------------------------
    # INSTAGRAM UPLOAD
    # ---------------------------
    elif st.session_state.chat_type == 'instagram':
        st.header("📸 Instagram Wrapped")
        st.write("Analyze your Instagram DMs or Group Chats.")
        
        # INSTRUCTIONS
        with st.expander("📱 How to export your Instagram chat", expanded=True):
            st.write("""
            1. Open the Instagram app and go to **Settings > Your activity**.
            2. Scroll down and tap **Download your information**.
            3. Tap **Request a download** > **Select types of information** > **Messages**.
            4. **CRITICAL:** Make sure the format is set to **JSON** (Not HTML).
            5. Once Instagram emails you the file, unzip it.
            6. Navigate to `messages/inbox/` and find the folder for your specific chat.
            7. Upload the `message_1.json` file here!
            """)
            
        uploaded_file = st.file_uploader("Upload message_1.json", type=['json'])
        
        if uploaded_file:
            try:
                string_data = uploaded_file.getvalue().decode("utf-8")
                df = parse_instagram_json(string_data)
                
                if df.empty:
                    st.error("File loaded, but no valid messages were found.")
                else:
                    st.success("Instagram chat parsed successfully!")
            except Exception as e:
                st.error(f"Error parsing Instagram JSON: {e}")

    # ---------------------------
    # TELEGRAM UPLOAD
    # ---------------------------
    elif st.session_state.chat_type == 'telegram':
        st.header("✈️ Telegram Wrapped")
        st.write("Analyze your Telegram Group Chats.")
        
        # INSTRUCTIONS
        with st.expander("🛠️ How to export your Telegram chat", expanded=True):
            st.write("""
            1. Download and open **Telegram Desktop** on your Mac or PC.
            2. Open the group chat you want to analyze.
            3. Click the three dots (⋮) in the top right corner and select **Export chat history**.
            4. **CRITICAL:** Uncheck all media (photos, videos) to make the file smaller, and change the format to **Machine-readable JSON**.
            5. Click **Export** and upload the resulting `result.json` file here!
            """)
            
        uploaded_file = st.file_uploader("Upload result.json", type=['json'])
        
        if uploaded_file:
            try:
                string_data = uploaded_file.getvalue().decode("utf-8")
                df = parse_telegram_json(string_data)
                
                if df.empty:
                    st.error("File loaded, but no valid messages were found.")
                else:
                    st.success("Telegram chat parsed successfully!")
            except Exception as e:
                st.error(f"Error parsing Telegram JSON: {e}")
    
    # ---------------------------
    # IMESSAGE UPLOAD
    # ---------------------------
    elif st.session_state.chat_type == 'imessage':
        st.header("🍏 iMessage Wrapped")
        st.write("Analyze your group chats directly from your iPhone backup.")
        
        with st.expander("🛠️ How to get your iMessage CSV", expanded=False):
            st.markdown("""
            1. Make an **Unencrypted Local Backup** of your iPhone to your PC/Mac.
            2. Locate your backup folder and find the `3d0d7e5fb2ce288813306e4d4636395e047a3d28` file inside the `3d` folder.
            3. Rename it to `chat.db` and put it in this app's folder.
            4. Run `python imessage_dumper.py` to select your chat and generate the CSV!
            """)
            
        uploaded_file = st.file_uploader("Upload your imessage_export.csv", type=['csv'])
        
        if uploaded_file:
            try:
                # Read the CSV generated by our dumper script
                df = pd.read_csv(uploaded_file)
                
                # Make sure Pandas knows the Date column is actually time data
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                
                # Drop any weird blank rows just to be safe
                df = df.dropna(subset=['Date', 'Content'])
                
                st.success(f"✅ Successfully loaded {len(df)} iMessages!")
                
            except Exception as e:
                st.error(f"Error parsing CSV: {e}")

    st.markdown('<div id="top-of-page"></div>', unsafe_allow_html=True)

    # --- COMMON PROCESSING & CLEANING ---
    if df is not None and not df.empty:
        # 1. Fix Dates (Optimized for speed)
        try:
            # For Pandas 2.0+: 'mixed' format with caching is incredibly fast
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce', cache=True)
        except ValueError:
            # Fallback for older Pandas versions
            df['Date'] = pd.to_datetime(df['Date'], infer_datetime_format=True, errors='coerce', cache=True)
        df = df.dropna(subset=['Date'])
        df = df.sort_values('Date') 
        
        # 2. Clean Authors
        df['Author'] = df['Author'].astype(str).str.replace('(pinned)', '', regex=False).str.strip()
        df = df[~df['Author'].str.contains("Deleted User", case=False, na=False)]
        
        # 3. Remove System Messages
        system_phrases = [
            "Pinned a message.", "Added ", "Changed the channel name", 
            "started a call", "joined the group", "left the group",
            "Messages and calls are end-to-end encrypted", "created group"
        ]
        for phrase in system_phrases:
            df = df[~df['Content'].str.startswith(phrase, na=False)]

        # 4. Add Features & Ratios
        df['Hour'] = df['Date'].dt.hour
        df['Word_Count'] = df['Content'].astype(str).apply(lambda x: len(x.split()))
        df['Time_Since_Last_Msg'] = df['Date'].diff()
        df['Time_To_Next_Msg'] = df['Date'].diff(-1).abs()
        
        if 'Reactions' in df.columns:
            df['Reactions'] = pd.to_numeric(df['Reactions'], errors='coerce')
        
        # 5. Global Sentiment Analysis
        sia = SentimentIntensityAnalyzer()
        df['Sentiment'] = df['Content'].astype(str).apply(lambda x: sia.polarity_scores(x)['compound'])
        
        st.success(f"Successfully loaded {len(df)} messages!")
        st.divider()
        
        # --- THE ROSTER UI ---
        # Count the messages before filtering
        msg_counts = df['Author'].value_counts()
        valid_authors = msg_counts[msg_counts >= 50].index.tolist()
        ghosts = msg_counts[msg_counts < 50].index.tolist()
        
        st.markdown("### 📋 Group Chat Roster")
        
        # Display the active members in a green success box
        st.success(f"**Valid Members ({len(valid_authors)}):** {', '.join(valid_authors)}")

        # Display the ghosts in a yellow warning box
        if ghosts:
            st.warning(f"**Ghosts (Less than 50 messages):** {', '.join(ghosts)}")
        else:
            st.info("**Ghosts:** None! Everyone participated.")

        st.markdown("---") 
        
        # Now finally create the filtered dataframe for the rest of your app!
        df_filtered = df[df['Author'].isin(valid_authors)].copy()
    
        # ---------------------
        # TOP LEVEL CATEGORIES
        # ---------------------
        cat_fame, cat_shame, cat_eval, cat_tools, cat_who = st.tabs([
            "🏆 Hall of Fame", 
            "💀 Wall of Shame", 
            "🎭 Psych Eval", 
            "🔎 Detective",
            "❓ Who said it?"
        ])
        
        # =========================
        # CATEGORY 1: HALL OF FAME
        # =========================
        with cat_fame:
            st.title("🏆 Hall of Fame")
            st.caption("The heavy lifters of the group chat.")
            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 1: MOST MESSAGES
            # -----------------------------------
            st.subheader("🗣️ Most Messages Sent")
            st.caption("Total volume of messages sent to the chat.")
            
            col_text, col_anim = st.columns([2, 1])
            with col_text:
                top_senders = msg_counts[valid_authors].head(3)
                
                if not top_senders.empty:
                    st.metric(label="🥇 1st Place", value=f"{top_senders.index[0]}", delta=f"{top_senders.iloc[0]} messages", delta_color="normal")
                    
                    c2, c3 = st.columns(2)
                    if len(top_senders) > 1: c2.caption(f"🥈 **2nd:** {top_senders.index[1]} ({top_senders.iloc[1]})")
                    if len(top_senders) > 2: c3.caption(f"🥉 **3rd:** {top_senders.index[2]} ({top_senders.iloc[2]})")
            
            with col_anim:
                if 'gif_party' in locals(): st.image(gif_party, width='stretch')

            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 2: HIGHEST REACTIONS
            # -----------------------------------
            st.subheader("🎯 Highest Reaction Rate")
            st.caption("Average number of reactions received per message (Quality over Quantity).")
            
            col_text, col_anim = st.columns([2, 1])
            with col_text:
                if 'Reactions' in df.columns:
                    if pd.api.types.is_numeric_dtype(df_filtered['Reactions']):
                         df_filtered['Reaction_Count'] = df_filtered['Reactions'].fillna(0)
                    else:
                        def count_reactions(reaction_str):
                            if pd.isna(reaction_str): return 0
                            total = 0
                            for part in str(reaction_str).split(','):
                                if '(' in part and ')' in part:
                                    try: total += int(part.split('(')[1].split(')')[0])
                                    except: continue
                            return total
                        df_filtered['Reaction_Count'] = df_filtered['Reactions'].apply(count_reactions)

                    avg_reactions = (df_filtered.groupby('Author')['Reaction_Count'].sum() / msg_counts[valid_authors]).sort_values(ascending=False).head(3)
                    
                    if not avg_reactions.empty and avg_reactions.iloc[0] > 0:
                        st.metric(label="🥇 1st Place", value=f"{avg_reactions.index[0]}", delta=f"{avg_reactions.iloc[0]:.2f} reactions / msg", delta_color="normal")
                        
                        c2, c3 = st.columns(2)
                        if len(avg_reactions) > 1: c2.caption(f"🥈 **2nd:** {avg_reactions.index[1]} ({avg_reactions.iloc[1]:.2f})")
                        if len(avg_reactions) > 2: c3.caption(f"🥉 **3rd:** {avg_reactions.index[2]} ({avg_reactions.iloc[2]:.2f})")
                    else:
                        st.write("No reactions found in this chat.")
            
            with col_anim:
                if 'gif_smart' in locals(): st.image(gif_smart, width='stretch')

            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 3: CONVERSATION REVIVALS
            # -----------------------------------
            st.subheader("🧟‍♂️ Conversation Revivals")
            st.caption("Who sends the first message after the chat has been dead for 6+ hours?")
            
            revivals = df_filtered[df_filtered['Time_Since_Last_Msg'] > pd.Timedelta(hours=6)]
            necromancers = revivals['Author'].value_counts().head(3)
            
            if not necromancers.empty:
                st.metric(label="🥇 1st Place", value=f"{necromancers.index[0]}", delta=f"{necromancers.iloc[0]} revivals", delta_color="normal")
                c2, c3 = st.columns(2)
                if len(necromancers) > 1: c2.caption(f"🥈 **2nd:** {necromancers.index[1]} ({necromancers.iloc[1]})")
                if len(necromancers) > 2: c3.caption(f"🥉 **3rd:** {necromancers.index[2]} ({necromancers.iloc[2]})")
            else:
                st.write("Your chat never dies for more than 6 hours.")

            st.markdown("---")

            # -----------------------------------
            # QUICK STATS
            # -----------------------------------
            st.subheader("⚡ Quick Stats")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.caption("📝 Longest Messages")
                avg_words = df_filtered.groupby('Author')['Word_Count'].mean().sort_values(ascending=False)
                if not avg_words.empty: 
                    st.markdown(f"## {avg_words.index[0]}")
                    st.write(f"{avg_words.iloc[0]:.1f} words/msg")

            with col2:
                st.caption("🧠 Biggest Vocabulary")
                def get_avg_word_len(text):
                    clean_text = re.sub(r'http\S+|www\S+|<.*?>|attachment|image omitted', '', str(text), flags=re.IGNORECASE)
                    clean_text = re.sub(r'[^\w\s]', '', clean_text)
                    words = clean_text.split()
                    return sum(len(w) for w in words) / len(words) if words else 0
                
                df_filtered['Word_Length'] = df_filtered['Content'].apply(get_avg_word_len)
                smart_pants = df_filtered.groupby('Author')['Word_Length'].mean().sort_values(ascending=False)
                
                if not smart_pants.empty: 
                    st.markdown(f"## {smart_pants.index[0]}")
                    st.write(f"{smart_pants.iloc[0]:.1f} letters/word")

            with col3:
                st.caption("🦉 Most Late Night Texts")
                df_filtered['Is_Late'] = ((df_filtered['Hour'] >= 1) & (df_filtered['Hour'] <= 5)).astype(int)
                owl_ratio = (df_filtered.groupby('Author')['Is_Late'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False)
                if not owl_ratio.empty and owl_ratio.iloc[0] > 0:
                    st.markdown(f"## {owl_ratio.index[0]}")
                    st.write(f"{owl_ratio.iloc[0]:.1f}% late texts")
            
            st.markdown("<br><div style='text-align: center;'><a href='#top-of-page' style='color: #FF4B4B; text-decoration: none; font-weight: bold;'>⬆️ Back to Top</a></div>", unsafe_allow_html=True)
        
        # ==========================
        # CATEGORY 2: WALL OF SHAME
        # ==========================
        with cat_shame:
            st.title("💀 Wall of Shame")
            st.caption("Exposing the worst conversational habits.")
            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 1: CONVERSATION KILLERS
            # -----------------------------------
            st.subheader("🔪 Conversation Killers")
            st.caption("Percentage of their messages that cause the chat to immediately die for 3+ hours.")
            
            col_text, col_anim = st.columns([2, 1])
            with col_text:
                thread_deaths = df_filtered[df_filtered['Time_To_Next_Msg'] > pd.Timedelta(hours=3)]
                killer_ratio = (thread_deaths['Author'].value_counts() / msg_counts[valid_authors] * 100).sort_values(ascending=False).dropna().head(3)
                
                if not killer_ratio.empty and killer_ratio.iloc[0] > 0:
                    st.metric(label="🥇 1st Place", value=f"{killer_ratio.index[0]}", delta=f"{killer_ratio.iloc[0]:.1f}% kill rate", delta_color="inverse")
                    
                    c2, c3 = st.columns(2)
                    if len(killer_ratio) > 1: c2.caption(f"🥈 **2nd:** {killer_ratio.index[1]} ({killer_ratio.iloc[1]:.1f}%)")
                    if len(killer_ratio) > 2: c3.caption(f"🥉 **3rd:** {killer_ratio.index[2]} ({killer_ratio.iloc[2]:.1f}%)")
                else:
                    st.write("Your chat never dies.")
            
            with col_anim:
                if 'gif_ghost' in locals(): st.image(gif_ghost, width='stretch')

            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 2: MOST CONSECUTIVE MESSAGES
            # -----------------------------------
            st.subheader("📱 Most Consecutive Messages")
            st.caption("Percentage of their messages sent immediately after their own previous message (Double-texting).")
            
            df_filtered['Is_Double_Text'] = (df_filtered['Author'] == df_filtered['Author'].shift(1)).astype(int)
            double_text_ratio = (df_filtered.groupby('Author')['Is_Double_Text'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False).head(3)
            
            if not double_text_ratio.empty and double_text_ratio.iloc[0] > 0:
                st.metric(label="🥇 1st Place", value=f"{double_text_ratio.index[0]}", delta=f"{double_text_ratio.iloc[0]:.1f}% consecutive", delta_color="inverse")
                
                c2, c3 = st.columns(2)
                if len(double_text_ratio) > 1: c2.caption(f"🥈 **2nd:** {double_text_ratio.index[1]} ({double_text_ratio.iloc[1]:.1f}%)")
                if len(double_text_ratio) > 2: c3.caption(f"🥉 **3rd:** {double_text_ratio.index[2]} ({double_text_ratio.iloc[2]:.1f}%)")

            st.markdown("---")
            
           # -----------------------------------
            # QUICK STATS
            # -----------------------------------
            st.subheader("⚡ Quick Stats")
            st.caption("📢 Highest ALL CAPS Usage")
            
            df_filtered['Is_Scream'] = ((df_filtered['Content'].str.isupper()) & (df_filtered['Content'].str.len() > 4)).astype(int)
            scream_ratio = (df_filtered.groupby('Author')['Is_Scream'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False)
            
            if not scream_ratio.empty and scream_ratio.iloc[0] > 0:
                st.markdown(f"## {scream_ratio.index[0]}")
                st.write(f"{scream_ratio.iloc[0]:.1f}% of their texts are yelling")
            else:
                st.markdown("## Everyone")
                st.write("0% yelling (Everyone is quiet)")
            
            st.markdown("<br><div style='text-align: center;'><a href='#top-of-page' style='color: #FF4B4B; text-decoration: none; font-weight: bold;'>⬆️ Back to Top</a></div>", unsafe_allow_html=True)
        
        # ==========================
        # CATEGORY 3: PSYCH EVAL
        # ==========================
        with cat_eval:
            st.title("🎭 Psych Eval")
            st.caption("Deep behavioral analysis of the group chat.")
            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 1: SENTIMENT SPLIT
            # -----------------------------------
            st.subheader("⚖️ Sentiment Analysis")
            st.caption("Who is the most positive, and who is the most negative?")
            
            col_vibes, col_hater = st.columns(2)
            
            emotional_msgs = df_filtered[df_filtered['Sentiment'] != 0.0]
            avg_sentiment = emotional_msgs.groupby('Author')['Sentiment'].mean()
            
            # FIX: Stretch the averages (multiplier of 3) so they don't all cluster around 50/100
            def calculate_vibe_score(raw_avg):
                stretched = max(min(raw_avg * 3, 1.0), -1.0) # Cap at max 1.0 and min -1.0
                return int(((stretched + 1) / 2) * 100)
            
            with col_vibes:
                st.write("**✨ Most Positive (Best Vibes)**")
                vibers = avg_sentiment.sort_values(ascending=False).head(3)
                if not vibers.empty:
                    vibe_score = calculate_vibe_score(vibers.iloc[0])
                    st.metric(label="🥇 1st Place", value=f"{vibers.index[0]}", delta=f"{vibe_score}/100 Positivity Score", delta_color="normal")
                    if len(vibers) > 1: st.caption(f"🥈 **2nd:** {vibers.index[1]}")
            
            with col_hater:
                st.write("**🤬 Most Negative (The Hater)**")
                haters = avg_sentiment.sort_values(ascending=True).head(3) # Ascending gets the lowest scores
                if not haters.empty:
                    hate_score = calculate_vibe_score(haters.iloc[0])
                    st.metric(label="🥇 1st Place", value=f"{haters.index[0]}", delta=f"{hate_score}/100 Positivity Score", delta_color="inverse", delta_arrow="down")
                    if len(haters) > 1: st.caption(f"🥈 **2nd:** {haters.index[1]}")

            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 2: SELF-CENTERED TEXTS
            # -----------------------------------
            st.subheader("🪞 Self-Centered Texts")
            st.caption("Highest percentage of messages containing 'I', 'me', 'my', or 'mine'.")
            
            def count_ego(text):
                if pd.isna(text): return 0
                return 1 if re.search(r'\b(i|me|my|mine)\b', str(text).lower()) else 0
            
            df_filtered['Ego_Check'] = df_filtered['Content'].apply(count_ego)
            ego_ratio = (df_filtered.groupby('Author')['Ego_Check'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False).head(3)
            
            if not ego_ratio.empty and ego_ratio.iloc[0] > 0:
                st.metric(label="🥇 1st Place", value=f"{ego_ratio.index[0]}", delta=f"{ego_ratio.iloc[0]:.1f}% about themselves", delta_color="off")
                
                c2, c3 = st.columns(2)
                if len(ego_ratio) > 1: c2.caption(f"🥈 **2nd:** {ego_ratio.index[1]} ({ego_ratio.iloc[1]:.1f}%)")
                if len(ego_ratio) > 2: c3.caption(f"🥉 **3rd:** {ego_ratio.index[2]} ({ego_ratio.iloc[2]:.1f}%)")

            st.markdown("---")

            # -----------------------------------
            # HERO METRIC 3: ONE-WORD REPLIES
            # -----------------------------------
            st.subheader("🤖 One-Word Replies")
            st.caption("Highest percentage of messages that are exactly ONE word long.")
            
            df_filtered['Is_One_Word'] = (df_filtered['Word_Count'] == 1).astype(int)
            npc_ratio = (df_filtered.groupby('Author')['Is_One_Word'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False).head(3)
            
            if not npc_ratio.empty and npc_ratio.iloc[0] > 0:
                st.metric(label="🥇 1st Place", value=f"{npc_ratio.index[0]}", delta=f"{npc_ratio.iloc[0]:.1f}% 1-word replies", delta_color="off")
                
                c2, c3 = st.columns(2)
                if len(npc_ratio) > 1: c2.caption(f"🥈 **2nd:** {npc_ratio.index[1]} ({npc_ratio.iloc[1]:.1f}%)")
                if len(npc_ratio) > 2: c3.caption(f"🥉 **3rd:** {npc_ratio.index[2]} ({npc_ratio.iloc[2]:.1f}%)")

            st.markdown("---")

            # -----------------------------------
            # QUICK STATS
            # -----------------------------------
            st.subheader("⚡ Quick Stats: Communication Styles")
            col1, col2 = st.columns(2)

            with col1:
                st.caption("🖼️ Most Media/Links Sent")
                media_pattern = r'http|www|\.com|\.gif|\.png|\.jpg|\.mp4|attachment|image omitted|<media omitted>'
                df_filtered['Is_Media'] = df_filtered['Content'].str.contains(media_pattern, case=False, na=False).astype(int)
                meme_ratio = (df_filtered.groupby('Author')['Is_Media'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False)
                if not meme_ratio.empty and meme_ratio.iloc[0] > 0:
                    st.markdown(f"## {meme_ratio.index[0]}")
                    st.write(f"{meme_ratio.iloc[0]:.1f}% of their texts are media")

            with col2:
                st.caption("❓ Most Questions Asked")
                df_filtered['Has_Question'] = df_filtered['Content'].astype(str).apply(lambda x: 1 if '?' in x else 0)
                riddler_ratio = (df_filtered.groupby('Author')['Has_Question'].sum() / msg_counts[valid_authors] * 100).sort_values(ascending=False)
                if not riddler_ratio.empty and riddler_ratio.iloc[0] > 0:
                    st.markdown(f"## {riddler_ratio.index[0]}")
                    st.write(f"{riddler_ratio.iloc[0]:.1f}% of their texts contain '?'")
            
            st.markdown("<br><div style='text-align: center;'><a href='#top-of-page' style='color: #FF4B4B; text-decoration: none; font-weight: bold;'>⬆️ Back to Top</a></div>", unsafe_allow_html=True)

        # =====================
        # CATEGORY 4: DETECTIVE
        # =====================
        with cat_tools:
            st.title("🔎 Detective")
            st.caption("Investigate the raw data and find out who really said what.")
            st.markdown("---")
            
            # -----------------------------------
            # TOOL 1: INTERACTIVE WORD SEARCH 
            # -----------------------------------
            st.subheader("🕵️‍♂️ Who said it most?")
            st.caption("Search the chat history for a specific word (e.g., 'bro', 'cooked', 'lol')")
            
            col_text, col_anim = st.columns([2, 1])
            with col_text:
                search_word = st.text_input("Enter a word to investigate:", "lol")
                
                if search_word:
                    # Case-insensitive regex search with word boundaries (\b)
                    mask = df['Content'].str.contains(
                        rf"\b{re.escape(search_word)}\b",
                        case=False,
                        regex=True,
                        na=False
                    )
                    
                    word_counts = df[mask]['Author'].value_counts().head(3)
                    
                    if not word_counts.empty:
                        st.metric(label=f"🥇 Sends '{search_word}' the most", value=f"{word_counts.index[0]}", delta=f"{word_counts.iloc[0]} times", delta_color="off")
                        st.bar_chart(word_counts)
                    else:
                        st.write(f"Nobody has said '{search_word}'... yet.")

            with col_anim:
                if 'gif_search' in locals(): st.image(gif_search, width='stretch')

            st.markdown("---")

            # -----------------------------------
            # TOOL 2: THE DICTIONARY
            # -----------------------------------
            st.subheader("📚 The Chat Dictionary")
            st.caption("The most used words in this chat overall (excluding fillers).")
            
            col_dict, col_dict_viz = st.columns([2, 1])
            with col_dict:
                min_length = st.slider("Minimum Word Length:", min_value=1, max_value=12, value=4)
                
                custom_ignore = [
                    'nan', 'null', 'none', 'like', 'yeah', 'just', 'okay', 'maybe', 
                    'http', 'https', 'www', 'com', 'image', 'images', 
                    'omitted', 'attachment', 'attachments', 'embed', 'embeds',
                    'video', 'videos', 'gif', 'gifs', 'sticker', 'stickers',
                    'reaction', 'pinned', 'message', 'joined', 'left', 'call',
                    'start', 'channel', 'group', 'missed', 'upload', 'file', '<media'
                ]
                
                try:
                    stop_words = set(stopwords.words('english'))
                    stop_words.update(custom_ignore)
                except:
                    stop_words = set(custom_ignore)
                    
                content_series = df['Content'].dropna().astype(str).str.lower()
                content_series = content_series.str.replace(r'\{.*?\}', '', regex=True)
                content_series = content_series.str.replace(r'\<.*?\>', '', regex=True)
                
                all_text = " ".join(content_series)
                all_text = re.sub(r'http\S+', '', all_text)
                all_text = re.sub(r'www\S+', '', all_text)
                all_text = re.sub(r'[^a-z\s]', '', all_text)
                
                words = all_text.split()
                filtered_words = [w for w in words if w not in stop_words and len(w) >= min_length]
                word_counts = Counter(filtered_words).most_common(10)
                
                if word_counts:
                    top_word, top_count = word_counts[0]
                    st.metric(label="🥇 MOST USED WORD", value=f"'{top_word.upper()}'", delta=f"{top_count} times", delta_color="off")
                    
                    common_df = pd.DataFrame(word_counts, columns=['Word', 'Count'])
                    c = alt.Chart(common_df).mark_bar(color='#FF4B4B').encode(
                        x='Count',
                        y=alt.Y('Word', sort='-x'),
                        tooltip=['Word', 'Count']
                    )
                    st.altair_chart(c, width='stretch')
                else:
                    st.write("Not enough words found to analyze!")
            
            with col_dict_viz:
                if 'gif_dictionary' in locals(): st.image(gif_dictionary, width='stretch')

            st.markdown("---")

            # -----------------------------------
            # TOOL 3: THE CALENDAR
            # -----------------------------------
            st.subheader("📅 Activity Heatmap")
            st.caption("When is the group chat most active?")
            
            # Reusing your excellent calendar logic
            df['Day'] = df['Date'].dt.day_name()
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_counts = df['Day'].value_counts().reindex(days_order).fillna(0).reset_index()
            day_counts.columns = ['Day', 'Messages']
            
            c_cal = alt.Chart(day_counts).mark_bar().encode(
                x=alt.X('Day', sort=days_order),
                y='Messages',
                color=alt.condition(
                    alt.datum.Messages == day_counts['Messages'].max(),
                    alt.value('orange'), alt.value('steelblue')
                )
            ).properties(height=300) # Give the chart plenty of room to breathe
            
            st.altair_chart(c_cal, width='stretch')
            
            st.markdown("<br><div style='text-align: center;'><a href='#top-of-page' style='color: #FF4B4B; text-decoration: none; font-weight: bold;'>⬆️ Back to Top</a></div>", unsafe_allow_html=True)
        
        # -----------------------------------
        # CATEGORY 5: WHO SAID IT?
        # -----------------------------------
        with cat_who:
            st.header("🕹️ Who Said It?")
            st.write("We filtered out the boring texts and pulled 10 highly reactive or out-of-context messages. Read the quote aloud and have the group guess who sent it!")
            st.info("💡 Pro-tip: Keep score of who guesses the most correctly!")
            st.write("---")

            # Initialize trackers
            if 'used_messages' not in st.session_state:
                st.session_state.used_messages = []
            if 'game_round' not in st.session_state:
                st.session_state.game_round = 1

            # Generate new messages if we don't have any queued up
            if 'game_messages' not in st.session_state:
                
                # 1. Filter out boring messages
                interesting_df = df_filtered[
                    (df_filtered['Word_Count'] >= 4) & 
                    (~df_filtered['Content'].str.contains('http|www|\.com', case=False, na=False)) &
                    (~df_filtered['Content'].str.contains('attachment', case=False, na=False))
                ]

                # 2. Remove the messages we've already played with!
                available_df = interesting_df.drop(st.session_state.used_messages, errors='ignore')

                # 3. Check if we ran out of messages
                if len(available_df) < 10:
                    st.toast("🔄 You've seen all the best messages! Reshuffling the deck...", icon="🃏")
                    st.session_state.used_messages = [] # Reset the tracker
                    available_df = interesting_df       # Start over with all messages

                # 4. Pick the "Best" messages from what is AVAILABLE
                if 'Reactions' in available_df.columns and available_df['Reactions'].sum() > 0:
                    top_pool = available_df.sort_values('Reactions', ascending=False).head(50)
                    st.session_state.game_messages = top_pool.sample(min(10, len(top_pool)))
                else:
                    extreme_sentiment = available_df[
                        (available_df['Sentiment'] > 0.6) | (available_df['Sentiment'] < -0.6)
                    ]
                    if len(extreme_sentiment) >= 10:
                        st.session_state.game_messages = extreme_sentiment.sample(10)
                    else:
                        st.session_state.game_messages = available_df.sample(min(10, len(available_df)))
                        
                # 5. Add these new 10 messages to our "used" list so they don't appear next time
                st.session_state.used_messages.extend(st.session_state.game_messages.index.tolist())


            # --- THE GAME UI ---
            
            # Add a nice header that shows what round they are on, and a TOP button!
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader(f"🎮 Round {st.session_state.game_round}")
            with col2:
                if st.button("🎲 Skip to Next Round", key="top_btn"):
                    del st.session_state['game_messages']
                    st.session_state.game_round += 1
                    st.rerun()
                    
            st.write("---")

            # Build the 10 messages
            for i, row in enumerate(st.session_state.game_messages.itertuples()):
                st.markdown(f"### 💬 *\"{row.Content}\"*")
                
                # CRITICAL: Adding the game_round to the label forces Streamlit to reset it to CLOSED!
                with st.expander(f"👀 Click to reveal Answer #{i+1} (Round {st.session_state.game_round})"):
                    nice_date = row.Date.strftime('%B %d, %Y at %I:%M %p')
                    st.success(f"🚨 **{row.Author}** sent this!")
                    st.caption(f"Sent on {nice_date}")
                    
                    if hasattr(row, 'Reactions') and pd.notna(row.Reactions) and row.Reactions > 0:
                        st.write(f"🔥 This message got **{int(row.Reactions)} reactions!**")
                
                st.write("---")
                
            # Bottom Button
            if st.button("🎲 Play Again (Generate New Messages)", key="bottom_btn"):
                del st.session_state['game_messages']
                st.session_state.game_round += 1
                st.rerun()