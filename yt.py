# app.py
from flask import Flask, request, render_template, jsonify, Response, stream_with_context
import yt_dlp
import requests
import uuid
import time

app = Flask(__name__)

# -----------------------
# Cấu trúc cache:
# - term_cache: map song_lower -> uid
# - uid_cache: map uid -> metadata { title, webpage_url, direct_url, created_at, term }
# -----------------------
term_cache = {}
uid_cache = {}

# Helper: tìm video + chọn direct audio url tốt nhất
def search_youtube_and_get_audio(song):
    # Trả về dict: { title, webpage_url, direct_url }
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "default_search": "ytsearch1:",
        # không tải file về
        "skip_download": True,
    }

    query = f"ytsearch1:{song}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        video = info["entries"][0] if "entries" in info and info["entries"] else info

        title = video.get("title", "Không rõ tiêu đề")
        webpage_url = video.get("webpage_url")

        # Chọn format audio-only tốt nhất (cao bitrate)
        direct_url = None
        best_bitrate = 0

        formats = video.get("formats") or []
        for f in formats:
            acodec = f.get("acodec")
            vcodec = f.get("vcodec")
            proto = f.get("protocol", "")
            fmt_url = f.get("url")
            # bỏ những format k có audio hoặc không phải http(s)
            if not fmt_url:
                continue
            if acodec in (None, "none"):
                continue
            # Ưu tiên audio-only (vcodec == 'none') hoặc ít nhất audio present và protocol http/https
            if proto and not proto.startswith("http"):
                continue
            # lấy bitrate nếu có
            abr = f.get("abr") or f.get("tbr") or 0
            try:
                abr = float(abr)
            except Exception:
                abr = 0.0
            # chọn bitrate lớn nhất
            if abr >= best_bitrate:
                best_bitrate = abr
                direct_url = fmt_url

        # Fallback nếu không tìm được formats
        if not direct_url:
            # video.get("url") có thể là direct stream link
            direct_url = video.get("url")

        return {"title": title, "webpage_url": webpage_url, "direct_url": direct_url}

# Thêm CORS header cho mọi response (giúp IoT client gọi dễ dàng)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Range"
    return response

# Trang web tìm và phát nhạc
@app.route("/", methods=["GET"])
def index():
    song = request.args.get("song", "").strip()
    result = None
    proxied_url = None

    if song:
        key = song.lower()
        # dùng cache nếu có
        if key in term_cache:
            uid = term_cache[key]
            result = uid_cache.get(uid)
        else:
            try:
                info = search_youtube_and_get_audio(song)
                if not info.get("direct_url"):
                    result = {"title": f"Lỗi: không tìm thấy luồng audio cho '{song}'", "webpage_url": info.get("webpage_url"), "direct_url": None}
                else:
                    uid = uuid.uuid4().hex
                    meta = {
                        "term": key,
                        "title": info.get("title"),
                        "webpage_url": info.get("webpage_url"),
                        "direct_url": info.get("direct_url"),
                        "created_at": time.time(),
                    }
                    uid_cache[uid] = meta
                    term_cache[key] = uid
                    result = meta
            except Exception as e:
                result = {"title": f"Lỗi khi tìm nhạc: {str(e)}", "webpage_url": None, "direct_url": None}

        if result and result.get("direct_url"):
            proxied_url = request.host_url.rstrip("/") + "/stream/" + (term_cache[key] if key in term_cache else uid)

    return render_template("yt.html",
                           title=result["title"] if result else None,
                           webpage_url=result.get("webpage_url") if result else None,
                           proxied_url=proxied_url)

# API cho IoT: trả JSON chứa title, webpage_url, direct_url (nếu muốn), proxied_url (đề xuất dùng proxied_url)
@app.route("/api/search", methods=["GET", "POST", "OPTIONS"])
def api_search():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or request.values or {}
    song = (data.get("song") or data.get("q") or data.get("query") or request.args.get("song") or "").strip()
    if not song:
        return jsonify({"ok": False, "error": "Thiếu tham số 'song'"}), 400

    key = song.lower()
    if key in term_cache:
        uid = term_cache[key]
        meta = uid_cache.get(uid)
    else:
        try:
            info = search_youtube_and_get_audio(song)
            if not info.get("direct_url"):
                return jsonify({"ok": False, "error": "Không tìm được luồng audio."}), 404
            uid = uuid.uuid4().hex
            meta = {
                "term": key,
                "title": info.get("title"),
                "webpage_url": info.get("webpage_url"),
                "direct_url": info.get("direct_url"),
                "created_at": time.time(),
            }
            uid_cache[uid] = meta
            term_cache[key] = uid
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    proxied_url = request.host_url.rstrip("/") + "/stream/" + uid
    # Trả cả direct_url (cẩn thận: direct_url có thể hết hạn), proxied_url dùng an toàn
    return jsonify({
        "ok": True,
        "title": meta["title"],
        "webpage_url": meta["webpage_url"],
        "direct_url": meta["direct_url"],
        "proxied_url": proxied_url,
        "uid": uid
    })

# Stream proxy endpoint: client gọi /stream/<uid> để phát audio
@app.route("/stream/<uid>", methods=["GET", "HEAD"])
def stream_proxy(uid):
    meta = uid_cache.get(uid)
    if not meta:
        return ("UID không tồn tại hoặc hết hạn", 404)

    upstream_url = meta.get("direct_url")
    if not upstream_url:
        return ("Không có URL audio", 404)

    # Forward Range header nếu client gửi (để hỗ trợ seek)
    headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        upstream = requests.get(upstream_url, stream=True, headers=headers, timeout=15)
    except Exception as e:
        return (f"Lỗi khi kết nối đến nguồn: {e}", 502)

    # Tạo generator streaming
    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            try:
                upstream.close()
            except:
                pass

    # Chọn một vài header để trả về cho client (Content-Type, Content-Length, Accept-Ranges, Content-Range)
    response_headers = {}
    ct = upstream.headers.get("Content-Type")
    if ct:
        response_headers["Content-Type"] = ct
    cl = upstream.headers.get("Content-Length")
    if cl:
        response_headers["Content-Length"] = cl
    ar = upstream.headers.get("Accept-Ranges")
    if ar:
        response_headers["Accept-Ranges"] = ar
    cr = upstream.headers.get("Content-Range")
    if cr:
        response_headers["Content-Range"] = cr

    return Response(stream_with_context(generate()), status=upstream.status_code, headers=response_headers)

if __name__ == "__main__":
    # Chạy trên toàn bộ interface để IoT device có thể truy cập
    app.run(host="0.0.0.0", port=5000, debug=False)
