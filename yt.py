from flask import Flask, request, render_template, jsonify
import yt_dlp
import os
import logging

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple in-memory cache
cache = {}

# Optimized yt-dlp configuration
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extractaudio': True,
    'audioformat': 'mp3',
    'default_search': 'ytsearch1',
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'no_call_home': True,
    'no_color': True,
    'socket_timeout': 10,
}

def search_youtube(song):
    """Search YouTube and return audio info"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song, download=False)
            
            # Check if we got valid results
            if not info:
                logger.error(f"No results found for: {song}")
                return None
                
            # Handle search results (ytsearch returns entries)
            if 'entries' in info:
                if not info['entries']:
                    logger.error(f"No entries in search results for: {song}")
                    return None
                video = info['entries'][0]
            else:
                video = info

            # Validate we have required fields
            if not video.get('url'):
                logger.error(f"No audio URL found for: {song}")
                return None

            return {
                'title': video.get('title', 'Không có tiêu đề'),
                'audio_url': video.get('url'),
                'webpage_url': video.get('webpage_url', '#'),
                'thumbnail': video.get('thumbnail', ''),
                'duration': video.get('duration', 0),
                'success': True
            }
            
    except Exception as e:
        logger.error(f"Error searching YouTube for {song}: {str(e)}")
        return None

@app.route('/')
def home():
    song = request.args.get('song', '').strip()
    result = None
    
    if song:
        cache_key = song.lower()
        if cache_key in cache:
            result = cache[cache_key]
        else:
            result = search_youtube(song)
            if result:
                cache[cache_key] = result
    
    return render_template('yt.html', 
                         title=result['title'] if result else None,
                         audio_url=result['audio_url'] if result else None,
                         webpage_url=result['webpage_url'] if result else None,
                         thumbnail=result['thumbnail'] if result else None)

@app.route('/search')
def search_music():
    song = request.args.get('song', '').strip()
    
    if not song:
        return jsonify({'error': 'Thiếu tên bài hát', 'success': False}), 400

    # Check cache first
    cache_key = song.lower()
    if cache_key in cache:
        result = cache[cache_key]
        result['cached'] = True
        return jsonify(result)

    # Search YouTube
    result = search_youtube(song)
    if result:
        cache[cache_key] = result
        return jsonify(result)
    else:
        return jsonify({'error': 'Không tìm thấy bài hát hoặc có lỗi xảy ra', 'success': False}), 404

@app.route('/api/play', methods=['GET', 'POST'])
def api_play():
    if request.method == 'POST':
        data = request.get_json() or {}
        song = data.get('song', '').strip()
    else:
        song = request.args.get('song', '').strip()

    if not song:
        return jsonify({'error': 'Thiếu tham số song', 'success': False}), 400

    # Use the same search logic
    cache_key = song.lower()
    if cache_key in cache:
        result = cache[cache_key]
        result['cached'] = True
        return jsonify(result)

    result = search_youtube(song)
    if result:
        cache[cache_key] = result
        result['cached'] = False
        return jsonify(result)
    else:
        return jsonify({'error': 'Không tìm thấy bài hát', 'success': False}), 404

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Vercel requires this
if __name__ == '__main__':
    app.run(debug=True)
