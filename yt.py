# yt.py
from flask import Flask, request, render_template, jsonify
import requests, re, json, time, uuid
from urllib.parse import quote_plus

app = Flask(__name__, template_folder="templates")

# Simple in-memory cache (function instance lifetime)
_cache = {}

def youtube_search_first(song):
    """
    Trả về dict: { videoId, title, watch_url, embed_url }
    Lấy từ YouTube search page bằng cách parse ytInitialData.
    """
    q = quote_plus(song)
    url = f"https://www.youtube.com/results?search_query={q}&bpctr=9999999999"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    text = resp.text

    # tìm block JSON ytInitialData
    m = re.search(r"var ytInitialData = ({.*?});</script>", text, re.S)
    if not m:
        m = re.search(r"ytInitialData\s*=\s*({.*?});", text, re.S)
    if not m:
        m = re.search(r"window\['ytInitialData'\]\s*=\s*({.*?});", text, re.S)
    if not m:
        # một số region sẽ khác, tìm "ytInitialData" mở ngoặc
        m = re.search(r"ytInitialData\"\s*:\s*({.*?})\s*,\s*\"responseContext", text, re.S)
    if not m:
        raise Exception("Không thể trích xuất ytInitialData từ YouTube (có thể bị chặn).")

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        raise Exception("Phân tích JSON thất bại: " + str(e))

    # đệ quy tìm videoRenderer
    def find_video_renderer(node):
        if isinstance(node, dict):
            if "videoRenderer" in node:
                return node["videoRenderer"]
            for v in node.values():
                res = find_video_renderer(v)
                if res:
                    return res
        elif isinstance(node, list):
            for item in node:
                res = find_video_renderer(item)
                if res:
                    return res
        return None

    vr = find_video_renderer(data)
    if not vr:
        raise Exception("Không tìm thấy video trong kết quả tìm kiếm YouTube.")

    vid = vr.get("videoId")
    # lấy tiêu đề
    title = "Không rõ tiêu đề"
    title_info = vr.get("title")
    if isinstance(title_info, dict):
        runs = title_info.get("runs") or []
        if runs:
            title = "".join([r.get("text", "") for r in runs])
        else:
            title = title_info.get("simpleText") or title
    elif isinstance(title_info, str):
        title = title_info

    watch_url = f"https://www.youtube.com/watch?v={vid}"
    embed_url = f"https://www.youtube.com/embed/{vid}?autoplay=1&rel=0"

    return {"videoId": vid, "title": title, "watch_url": watch_url, "embed_url": embed_url}

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Range"
    return response

@app.route("/", methods=["GET"])
def index():
    song = (request.args.get("song") or "").strip()
    result = None
    if song:
        key = song.lower()
        entry = _cache.get(key)
        if entry and (time.time() - entry.get("ts", 0) < 60*60):  # cache 1 giờ
            result = entry["data"]
        else:
            try:
                info = youtube_search_first(song)
                result = info
                _cache[key] = {"ts": time.time(), "data": info}
            except Exception as e:
                result = {"error": str(e)}

    return render_template("yt.html", result=result, song=song)

@app.route("/api/search", methods=["GET","POST","OPTIONS"])
def api_search():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    song = ""
    if request.is_json:
        song = (request.json.get("song") or "").strip()
    if not song:
        song = (request.args.get("song") or "").strip()
    if not song:
        return jsonify({"ok": False, "error": "Thiếu tham số 'song'"}), 400

    key = song.lower()
    entry = _cache.get(key)
    if entry and (time.time() - entry.get("ts", 0) < 60*60):
        info = entry["data"]
    else:
        try:
            info = youtube_search_first(song)
            _cache[key] = {"ts": time.time(), "data": info}
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({
        "ok": True,
        "title": info["title"],
        "watch_url": info["watch_url"],
        "embed_url": info["embed_url"],
        "videoId": info["videoId"]
    })

# cho local dev
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
