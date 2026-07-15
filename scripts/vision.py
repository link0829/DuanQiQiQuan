#!/usr/bin/env python3
"""
阿里云 DashScope 视觉识图脚本
用法: python vision.py <图片URL或本地路径>
环境变量: DASHSCOPE_API_KEY
"""
import sys, os, base64, requests, time
from io import BytesIO
from PIL import Image

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen-vl-plus"
DEFAULT_PROMPT = "识别图片里所有信息，使用 markdown 输出全部内容，并保持排版的一致"
MAX_EDGE = 1280

def get_api_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        print("错误: 未设置环境变量 DASHSCOPE_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key

def load_image(source):
    if source.startswith(("http://", "https://")):
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
    else:
        img = Image.open(source)
    return img

def resize_image(img):
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        ratio = MAX_EDGE / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    return img

def encode_image(img):
    buf = BytesIO()
    fmt = img.format or "PNG"
    if fmt.upper() not in ("JPEG", "JPG", "PNG", "WEBP"):
        fmt = "PNG"
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()

def call_vision_api(api_key, b64_data, prompt):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}}
    ]}], "max_tokens": 4096}
    for attempt in range(3):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError as e:
            if attempt < 2:
                print(f"重试 {attempt+1}/3...", file=sys.stderr)
                time.sleep(3)
            else:
                raise e

def main():
    if len(sys.argv) < 2:
        print("用法: python vision.py <图片URL或本地路径>", file=sys.stderr); sys.exit(1)
    try:
        img = load_image(sys.argv[1]); img = resize_image(img)
        b64 = encode_image(img)
        print(call_vision_api(get_api_key(), b64, DEFAULT_PROMPT))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
