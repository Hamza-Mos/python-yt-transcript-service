from quart import Quart, jsonify, request
from youtube_transcript_api import YouTubeTranscriptApi
from quart_cors import cors
import asyncio
import os
from dotenv import load_dotenv
import logging
import requests
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name
        }
        
        # Add error information if present
        if record.exc_info:
            log_obj["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }
            
        return json.dumps(log_obj)

# Configure logging
logger = logging.getLogger("transcript-service")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

app = Quart(__name__)
cors(app)

# Get proxy config from environment variables
PROXY_USER = os.getenv('PROXY_USER')
PROXY_PASS = os.getenv('PROXY_PASS')

# Smartproxy configuration
PROXY_URL = f"https://{PROXY_USER}:{PROXY_PASS}@gate.smartproxy.com:10001"
PROXY_CONFIG = {
    "https": PROXY_URL
}

# Create a session with trust_env=False
session = requests.Session()
session.trust_env = False

def get_video_id(url):
    """Extract video ID from YouTube URL"""
    url = url.strip()
    
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    if 'watch?v=' in url:
        return url.split('watch?v=')[1].split('&')[0]
        
    if '/shorts/' in url:
        return url.split('/shorts/')[1].split('?')[0]

    raise ValueError("Could not extract video ID from URL")

@app.route('/transcript', methods=['GET'])
async def get_transcript():
    youtube_url = request.args.get('url')
    logger.info({
        "event": "request_received",
        "url": youtube_url
    })
    
    if not youtube_url:
        logger.warning({
            "event": "missing_url",
            "error": "YouTube URL is required"
        })
        return jsonify({'error': 'YouTube URL is required'}), 400
        
    try:
        video_id = get_video_id(youtube_url)
        logger.info({
            "event": "video_id_extracted",
            "video_id": video_id
        })
        
        transcript_parts = await asyncio.to_thread(
            YouTubeTranscriptApi.get_transcript,
            video_id,
            proxies=PROXY_CONFIG,
            requests_session=session
        )
        
        full_transcript = ' '.join(part['text'] for part in transcript_parts)
        
        logger.info({
            "event": "transcript_retrieved",
            "video_id": video_id,
            "transcript_parts": len(transcript_parts)
        })
        
        return jsonify({
            'transcript': full_transcript,
            'raw': transcript_parts
        })
    except ValueError as e:
        logger.warning({
            "event": "invalid_url",
            "error": str(e),
            "url": youtube_url
        })
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error({
            "event": "transcript_error",
            "error": str(e),
            "url": youtube_url,
            "error_type": type(e).__name__
        })
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info({
        "event": "server_start",
        "environment": os.getenv('ENVIRONMENT', 'development')
    })
    app.run(port=3000)