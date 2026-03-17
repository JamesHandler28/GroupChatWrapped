import discord
import pandas as pd
import logging
import os

# Silence the 429 Rate Limit spam so you can actually read the console
logging.getLogger('discord.http').setLevel(logging.ERROR)

# --- CONFIGURATION (USERS MUST FILL THIS OUT) ---
# Replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token. Keep the quotes!
TOKEN = 'YOUR_BOT_TOKEN_HERE'

# Replace 123456789012345678 with your actual Channel ID. No quotes!
CHANNEL_ID = 123456789012345678 

FILE_NAME = 'discord_server_export.csv'

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    
    # Check if the user forgot to change the default ID
    if CHANNEL_ID == 123456789012345678:
        print("❌ ERROR: You forgot to put your CHANNEL_ID in the script!")
        await client.close()
        return

    channel = client.get_channel(CHANNEL_ID)
    
    if not channel:
        print("❌ Channel not found! Make sure the bot is invited to the server and has permission to view the channel.")
        await client.close()
        return

    print(f"📥 Started scraping ALL messages in #{channel.name}... this will take a while.")
    
    # Delete the old file if it exists so we start completely fresh
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)

    data_chunk = []
    total_collected = 0
    
    try:
        # oldest_first=True makes sure it starts from the dawn of time
        async for msg in channel.history(limit=None, oldest_first=True):
            if msg.author.bot:
                continue
            
            # ACCURATE REACTION MATH: Sum the total counts of all emojis used
            total_reactions = sum(reaction.count for reaction in msg.reactions)
                
            data_chunk.append([msg.created_at, msg.author.name, msg.content, total_reactions])
            total_collected += 1
            
            # Save to CSV every 5,000 messages to prevent memory crashes
            if len(data_chunk) >= 5000:
                df = pd.DataFrame(data_chunk, columns=['Date', 'Author', 'Content', 'Reactions'])
                # Only write the header if the file doesn't exist yet
                write_header = not os.path.exists(FILE_NAME)
                df.to_csv(FILE_NAME, mode='a', index=False, header=write_header)
                
                data_chunk = [] # Clear the chunk from memory
                print(f"   Saved {total_collected} messages so far...", end='\r')

        # When the loop is done, save whatever is left over
        if data_chunk:
            df = pd.DataFrame(data_chunk, columns=['Date', 'Author', 'Content', 'Reactions'])
            write_header = not os.path.exists(FILE_NAME)
            df.to_csv(FILE_NAME, mode='a', index=False, header=write_header)

        print(f"\n✅ Finished! Total messages saved: {total_collected}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("💾 Don't worry, messages collected before this error are already saved in the CSV!")
    
    await client.close()

# Catch the error if the user forgets to put their token in
try:
    client.run(TOKEN)
except discord.errors.LoginFailure:
    print("❌ ERROR: Invalid Token. Did you forget to paste your bot token into the script?")