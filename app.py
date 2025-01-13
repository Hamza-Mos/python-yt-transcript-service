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
from functools import wraps

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now().isoformat(),
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

# Add this after loading environment variables
API_KEY = os.getenv('API_KEY')
if not API_KEY:
    raise ValueError("API_KEY environment variable is required")

def require_api_key(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning({
                "event": "auth_missing",
                "error": "No authorization header"
            })
            return jsonify({'error': 'No authorization header'}), 401
            
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != 'bearer':
                raise ValueError('Invalid authorization scheme')
            if token != API_KEY:
                raise ValueError('Invalid API key')
        except Exception as e:
            logger.warning({
                "event": "auth_invalid",
                "error": str(e)
            })
            return jsonify({'error': 'Invalid authorization'}), 401

        return await f(*args, **kwargs)
    return decorated_function

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

async def get_best_transcript(video_id, proxies=None):
    """Get best available transcript with language fallbacks"""
    try:
        # Get list of available transcripts
        transcript_list = await asyncio.to_thread(
            YouTubeTranscriptApi.list_transcripts,
            video_id,
            proxies=proxies
        )
        
        # Categorize available transcripts
        manual_transcripts = []
        generated_transcripts = []
        
        for transcript in transcript_list:
            if transcript.is_generated:
                generated_transcripts.append(transcript.language_code)
            else:
                manual_transcripts.append(transcript.language_code)
        
        # Preferred languages in order
        preferred_languages = ['en', 'es', 'fr', 'de', 'ar']
        
        # First try manual transcripts
        for lang in preferred_languages:
            if lang in manual_transcripts:
                transcript = transcript_list.find_manually_created_transcript([lang])
                if lang != 'en':
                    transcript = transcript.translate('en')
                return await asyncio.to_thread(transcript.fetch)
        
        # Then try generated transcripts
        for lang in preferred_languages:
            if lang in generated_transcripts:
                transcript = transcript_list.find_generated_transcript([lang])
                if lang != 'en':
                    transcript = transcript.translate('en')
                return await asyncio.to_thread(transcript.fetch)
        
        # If none of preferred languages found, use first available transcript
        if generated_transcripts:
            transcript = transcript_list.find_generated_transcript([generated_transcripts[0]])
            return await asyncio.to_thread(transcript.translate('en').fetch)
        
        if manual_transcripts:
            transcript = transcript_list.find_manually_created_transcript([manual_transcripts[0]])
            return await asyncio.to_thread(transcript.translate('en').fetch)
            
        raise Exception("No available transcripts found")
        
    except Exception as e:
        logger.error({
            "event": "transcript_fetch_error",
            "error": str(e),
            "video_id": video_id,
            "error_type": type(e).__name__
        })
        raise

@app.route('/transcript', methods=['GET'])
@require_api_key
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
        
        transcript_parts = await get_best_transcript(video_id, proxies=PROXY_CONFIG)
        
        full_transcript = ' '.join(part['text'] for part in transcript_parts)
        
        logger.info({
            "event": "transcript_retrieved",
            "video_id": video_id,
            "transcript_parts": len(transcript_parts)
        })
        
        return jsonify({
            'transcript': full_transcript,
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