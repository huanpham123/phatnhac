from flask import Flask, request, render_template, jsonify
import yt_dlp
import os

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Simple in-memory cache (resets on cold start)
cache = {}

# Optimized yt-dlp configuration for Vercel
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
    'extract_flat': False,
}

@app.route('/')
def home():
    return render_template('yt.html')

@app.route('/search')
def search_music():
    song = request.args.get('song', '').strip()
    
    if not song:
        return jsonify({'error': 'Thiếu tên bài hát'}), 400

    # Check cache first
    cache_key = song.lower()
    if cache_key in cache:
        return jsonify(cache[cache_key])

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song, download=False)
            
            if not info:
                return jsonify({'error': 'Không tìm thấy bài hát'}), 404

            # Handle search results
            if 'entries' in info:
                video = info['entries'][0]
            else:
                video = info

            result = {
                'title': video.get('title', 'Không có tiêu đề'),
                'audio_url': video.get('url'),
                'webpage_url': video.get('webpage_url', '#'),
                'thumbnail': video.get('thumbnail', ''),
                'duration': video.get('duration', 0),
                'success': True
            }

            # Cache the result
            cache[cache_key] = result
            return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Lỗi khi tìm nhạc: {str(e)}'}), 500

# API for IoT devices
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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song, download=False)
            
            if not info:
                return jsonify({'error': 'Không tìm thấy bài hát', 'success': False}), 404

            if 'entries' in info:
                video = info['entries'][0]
            else:
                video = info

            result = {
                'title': video.get('title', 'Không có tiêu đề'),
                'audio_url': video.get('url'),
                'webpage_url': video.get('webpage_url', '#'),
                'thumbnail': video.get('thumbnail', ''),
                'duration': video.get('duration', 0),
                'success': True,
                'cached': False
            }

            cache[cache_key] = result
            return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Lỗi khi tìm nhạc: {str(e)}', 'success': False}), 500

# Health check endpoint for Vercel
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

# Handle CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Vercel requires this
if __name__ == '__main__':
    app.run(debug=True)
