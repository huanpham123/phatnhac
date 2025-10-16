from flask import Flask, request, render_template, jsonify, redirect
import yt_dlp
import requests
import re
import urllib.parse

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Cache đơn giản
cache = {}

# Cấu hình yt-dlp tối ưu
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extractaudio': True,
    'audioformat': 'mp3',
    'default_search': 'ytsearch1',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'no_call_home': True,
    'no_color': True,
    'socket_timeout': 15,
    'extract_flat': False,
}

def get_audio_info(song):
    """Lấy thông tin audio từ YouTube"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Thêm tiền tố tìm kiếm nếu chưa có
            if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/', song):
                search_query = f"ytsearch1:{song}"
            else:
                search_query = song
                
            info = ydl.extract_info(search_query, download=False)
            
            if not info:
                return None
                
            # Xử lý kết quả tìm kiếm
            if 'entries' in info:
                if not info['entries']:
                    return None
                video = info['entries'][0]
            else:
                video = info

            # Lấy URL audio trực tiếp
            audio_url = None
            if 'url' in video:
                audio_url = video['url']
            else:
                # Thử tìm trong formats
                formats = video.get('formats', [])
                for fmt in formats:
                    if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        audio_url = fmt.get('url')
                        if audio_url:
                            break
            
            if not audio_url:
                return None

            return {
                'title': video.get('title', 'Không có tiêu đề'),
                'audio_url': audio_url,
                'webpage_url': video.get('webpage_url', '#'),
                'thumbnail': video.get('thumbnail', ''),
                'duration': video.get('duration', 0),
                'success': True
            }
            
    except Exception as e:
        print(f"Lỗi khi tìm nhạc: {str(e)}")
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
            result = get_audio_info(song)
            if result:
                cache[cache_key] = result
    
    return render_template('yt.html', 
                         title=result['title'] if result else None,
                         audio_url=result['audio_url'] if result else None,
                         webpage_url=result['webpage_url'] if result else None,
                         thumbnail=result['thumbnail'] if result else None,
                         song_query=song)

@app.route('/search')
def search_music():
    song = request.args.get('song', '').strip()
    
    if not song:
        return jsonify({'error': 'Thiếu tên bài hát', 'success': False}), 400

    cache_key = song.lower()
    if cache_key in cache:
        result = cache[cache_key]
        result['cached'] = True
        return jsonify(result)

    result = get_audio_info(song)
    if result:
        cache[cache_key] = result
        return jsonify(result)
    else:
        return jsonify({'error': 'Không tìm thấy bài hát', 'success': False}), 404

@app.route('/api/play', methods=['GET', 'POST'])
def api_play():
    if request.method == 'POST':
        data = request.get_json() or {}
        song = data.get('song', '').strip()
    else:
        song = request.args.get('song', '').strip()

    if not song:
        return jsonify({'error': 'Thiếu tham số song', 'success': False}), 400

    cache_key = song.lower()
    if cache_key in cache:
        result = cache[cache_key]
        result['cached'] = True
        return jsonify(result)

    result = get_audio_info(song)
    if result:
        cache[cache_key] = result
        result['cached'] = False
        return jsonify(result)
    else:
        return jsonify({'error': 'Không tìm thấy bài hát', 'success': False}), 404

# Redirect đến direct URL (giải pháp thay thế cho streaming)
@app.route('/proxy/<path:url>')
def proxy_audio(url):
    """Redirect đến audio URL thực"""
    decoded_url = urllib.parse.unquote(url)
    return redirect(decoded_url)

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    app.run(debug=True)
