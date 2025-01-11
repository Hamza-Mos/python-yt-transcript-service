from quart import Quart, jsonify, request
from youtube_transcript_api import YouTubeTranscriptApi
from quart_cors import cors
import asyncio
import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Quart(__name__)
cors(app)

# Get proxy config from environment variables
PROXY_USER = os.getenv('PROXY_USER')
PROXY_PASS = os.getenv('PROXY_PASS')

# Smartproxy configuration
PROXY_URL = f"https://{PROXY_USER}:{PROXY_PASS}@us.smartproxy.com:10001"
PROXY_CONFIG = {
    "https": PROXY_URL
}

def get_video_id(url):
    """Extract video ID from YouTube URL"""
    # Remove any whitespace and get the full URL
    url = url.strip()
    
    # Handle youtu.be links
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    # Handle watch?v= links
    if 'watch?v=' in url:
        return url.split('watch?v=')[1].split('&')[0]
        
    # Handle YouTube Shorts
    if '/shorts/' in url:
        return url.split('/shorts/')[1].split('?')[0]

    raise ValueError("Could not extract video ID from URL")

@app.route('/transcript', methods=['GET'])
async def get_transcript():
    youtube_url = request.args.get('url')
    logger.info(f"Received request for URL: {youtube_url}")
    
    if not youtube_url:
        return jsonify({'error': 'YouTube URL is required'}), 400
        
    try:
        video_id = get_video_id(youtube_url)
        logger.info(f"Extracted video ID: {video_id}")
        
        transcript_parts = await asyncio.to_thread(
            YouTubeTranscriptApi.get_transcript,
            video_id,
            proxies=PROXY_CONFIG,
        )
        
        full_transcript = ' '.join(part['text'] for part in transcript_parts)
        
        logger.info("Successfully retrieved and concatenated transcript")
        return jsonify({
            'transcript': full_transcript,
        })
    except ValueError as e:
        logger.error(f"ValueError: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting server...")
    app.run(port=3000, debug=True)