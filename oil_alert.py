import os
import json
import time
import hashlib
import hmac
import base64
import urllib.parse
import requests


# =========================
# 钉钉机器人配置
# =========================
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")


def send_dingtalk(message):
    """发送钉钉机器人消息"""

    if not DINGTALK_WEBHOOK:
        print("错误：没有配置 DINGTALK_WEBHOOK")
        return

    url = DINGTALK_WEBHOOK

    if DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))

        string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"

        hmac_code = hmac.new(
            DINGTALK_SECRET.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()

        sign = urllib.parse.quote_plus(
            base64.b64encode(hmac_code)
        )

        url = f"{url}&timestamp={timestamp}&sign={sign}"

    data = {
        "msgtype": "text",
        "text": {
            "content": message
        }
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(data),
        timeout=20
    )

    print("钉钉返回：", response.text)


# =========================
# 临时测试
# =========================
if __name__ == "__main__":

    message = """⛽ 油价自动提醒系统

系统已经成功运行！

下一步将接入柴油价格数据，
并在油价发生变化时自动提醒。

监测路线：
青岛港 → 郓城

车型：
40尺集装箱

油耗：
35L/100km
"""

    send_dingtalk(message)
