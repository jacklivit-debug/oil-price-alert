import os
import json
import time
import hashlib
import hmac
import base64
import urllib.parse
from datetime import datetime

import requests


# ============================================================
# 基础配置
# ============================================================

OIL_PRICE_URL = "https://www.xiaoxiongyouhao.com/fprice/"

# 运输参数
ROUTE_NAME = "青岛港 → 郓城"
DISTANCE_KM = 509
FUEL_CONSUMPTION = 35

# 状态文件
STATE_FILE = "oil_state.json"

# 钉钉
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")


# ============================================================
# 获取山东0#柴油价格
# ============================================================

def get_shandong_diesel_price():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
    }

    response = requests.get(
        OIL_PRICE_URL,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    html = response.text

    marker = "山东省"

    if marker not in html:
        raise Exception("没有找到山东省油价数据")

    start = html.find(marker)

    section = html[start:start + 1000]

    import re

    pattern = r"山东省.*?(\d+\.\d+).*?(\d+\.\d+).*?(\d+\.\d+)"

    match = re.search(pattern, section, re.S)

    if not match:
        raise Exception(
            "无法解析山东柴油价格，请检查油价网站页面结构"
        )

    diesel_price = float(match.group(3))

    return diesel_price


# ============================================================
# 读取历史状态
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):

        return {
            "last_price": None,
            "highest_price": None,
            "last_date": None
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {
            "last_price": None,
            "highest_price": None,
            "last_date": None
        }


# ============================================================
# 保存状态
# ============================================================

def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# 计算油费
# ============================================================

def calculate_cost(diesel_price):

    fuel_liters = (
        DISTANCE_KM *
        FUEL_CONSUMPTION /
        100
    )

    cost = fuel_liters * diesel_price

    return fuel_liters, cost


# ============================================================
# 钉钉发送
# ============================================================

def send_dingtalk(message):

    if not DINGTALK_WEBHOOK:
        raise Exception(
            "没有找到 DINGTALK_WEBHOOK"
        )

    url = DINGTALK_WEBHOOK

    if DINGTALK_SECRET:

        timestamp = str(
            round(time.time() * 1000)
        )

        string_to_sign = (
            f"{timestamp}\n{DINGTALK_SECRET}"
        )

        hmac_code = hmac.new(
            DINGTALK_SECRET.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()

        sign = urllib.parse.quote_plus(
            base64.b64encode(hmac_code)
        )

        separator = "&" if "?" in url else "?"

        url = (
            f"{url}"
            f"{separator}timestamp={timestamp}"
            f"&sign={sign}"
        )

    data = {
        "msgtype": "text",
        "text": {
            "content": message
        }
    }

    response = requests.post(
        url,
        json=data,
        headers={
            "Content-Type": "application/json"
        },
        timeout=20
    )

    response.raise_for_status()

    result = response.json()

    if result.get("errcode", 0) != 0:

        raise Exception(
            f"钉钉发送失败：{result}"
        )


# ============================================================
# 主程序
# ============================================================

def main():

    now = datetime.now()

    today = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("=" * 60)
    print("油价自动监控系统")
    print("=" * 60)
    print("检查时间：", today)

    # --------------------------------------------------------
    # 获取当前油价
    # --------------------------------------------------------

    current_price = get_shandong_diesel_price()

    print(
        f"山东0#柴油：{current_price:.2f} 元/L"
    )

    # --------------------------------------------------------
    # 读取历史
    # --------------------------------------------------------

    state = load_state()

    last_price = state.get("last_price")
    highest_price = state.get("highest_price")

    # --------------------------------------------------------
    # 第一次运行
    # --------------------------------------------------------

    if last_price is None:

        highest_price = current_price

        state["last_price"] = current_price
        state["highest_price"] = highest_price
        state["last_date"] = today

        save_state(state)

        fuel_liters, cost = calculate_cost(
            current_price
        )

        message = (
            "⛽ 油价监控系统首次建立基准\n\n"
            f"时间：{today}\n"
            f"山东0#柴油：{current_price:.2f} 元/L\n\n"
            f"🚛 运输路线：{ROUTE_NAME}\n"
            f"📏 单程距离：{DISTANCE_KM} km\n"
            f"⛽ 油耗：{FUEL_CONSUMPTION} L/100km\n"
            f"🛢️ 单程用油：{fuel_liters:.2f} L\n"
            f"💰 单程油费：{cost:.2f} 元\n\n"
            "已建立油价基准，后续只有价格发生变化才提醒。"
        )

        send_dingtalk(message)

        print("首次运行完成")

        return

    # --------------------------------------------------------
    # 计算价格变化
    # --------------------------------------------------------

    change = current_price - last_price

    # 更新历史最高价
    if current_price > highest_price:

        highest_price = current_price

    # --------------------------------------------------------
    # 计算运输费用
    # --------------------------------------------------------

    fuel_liters, current_cost = calculate_cost(
        current_price
    )

    _, previous_cost = calculate_cost(
        last_price
    )

    _, highest_cost = calculate_cost(
        highest_price
    )

    # 本次油价变化对应的单程油费变化
    cost_change = current_cost - previous_cost

    # --------------------------------------------------------
    # 更新状态
    # --------------------------------------------------------

    state["last_price"] = current_price
    state["highest_price"] = highest_price
    state["last_date"] = today

    save_state(state)

    # --------------------------------------------------------
    # 油价没有变化
    # --------------------------------------------------------

    if abs(change) < 0.001:

        print(
            "油价没有变化，不发送钉钉消息。"
        )

        return

    # --------------------------------------------------------
    # 判断涨跌
    # --------------------------------------------------------

    if change > 0:

        direction = "上涨"
        emoji = "🔴"
        cost_word = "增加"

    else:

        direction = "下跌"
        emoji = "🟢"
        cost_word = "减少"

    # --------------------------------------------------------
    # 历史最高价比较
    # --------------------------------------------------------

    saving_vs_highest = (
        highest_cost - current_cost
    )

    # --------------------------------------------------------
    # 发送提醒
    # --------------------------------------------------------

    message = (
        f"{emoji} 油价发生变化\n\n"

        f"时间：{today}\n"

        f"山东0#柴油："
        f"{current_price:.2f} 元/L\n"

        f"上次价格："
        f"{last_price:.2f} 元/L\n"

        f"本次{direction}："
        f"{abs(change):.2f} 元/L\n\n"

        f"🚛 运输路线：{ROUTE_NAME}\n"

        f"📏 单程距离："
        f"{DISTANCE_KM} km\n"

        f"⛽ 油耗："
        f"{FUEL_CONSUMPTION} L/100km\n"

        f"🛢️ 单程用油："
        f"{fuel_liters:.2f} L\n\n"

        f"💰 当前单程油费："
        f"{current_cost:.2f} 元\n"

        f"💰 上次单程油费："
        f"{previous_cost:.2f} 元\n"

        f"🚛 每个40尺柜单程油费"
        f"{cost_word}："
        f"{abs(cost_change):.2f} 元\n\n"

        f"📊 历史最高油价："
        f"{highest_price:.2f} 元/L\n"

        f"💵 相比历史最高油价，"
        f"当前每柜单程"
        f"{'节省' if saving_vs_highest > 0 else '多花'}："
        f"{abs(saving_vs_highest):.2f} 元"
    )

    send_dingtalk(message)

    print(
        "油价变化，已发送钉钉提醒。"
    )


if __name__ == "__main__":
    main()
