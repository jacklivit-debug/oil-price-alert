import os
import json
import csv
import time
import hashlib
import hmac
import base64
import urllib.parse
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


# ============================================================
# 基础配置
# ============================================================

OIL_PRICE_URL = "https://www.xiaoxiongyouhao.com/fprice/"

ROUTE_NAME = "青岛港 → 郓城"
DISTANCE_KM = 509
FUEL_CONSUMPTION = 35

STATE_FILE = "oil_state.json"
HISTORY_FILE = "oil_history.csv"

DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


# ============================================================
# 北京时间
# ============================================================

def beijing_now():

    return datetime.now(BEIJING_TZ)


# ============================================================
# 获取山东0#柴油价格
# ============================================================

def get_shandong_diesel_price():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/140.0 Safari/537.36"
        )
    }

    response = requests.get(
        OIL_PRICE_URL,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # 确认页面日期
    # --------------------------------------------------------

    page_text = soup.get_text(
        " ",
        strip=True
    )

    page_date_match = re.search(
        r"今日油价[（(](\d{4}-\d{2}-\d{2})[）)]",
        page_text
    )

    page_date = (
        page_date_match.group(1)
        if page_date_match
        else None
    )

    # --------------------------------------------------------
    # 找山东价格
    # --------------------------------------------------------

    tables = soup.find_all("table")

    candidates = []

    for table in tables:

        rows = table.find_all("tr")

        for row in rows:

            cells = [
                c.get_text(
                    " ",
                    strip=True
                )
                for c in row.find_all(
                    ["th", "td"]
                )
            ]

            if not cells:
                continue

            joined = " ".join(cells)

            if (
                "山东省" in joined
                and len(cells) >= 4
            ):

                # 通常：
                # 山东省 | 92# | 95# | 0#柴
                try:

                    diesel_price = float(
                        cells[3]
                    )

                    candidates.append(
                        diesel_price
                    )

                except ValueError:

                    pass

    if not candidates:

        raise Exception(
            "无法从油价页面找到山东0#柴油价格"
        )

    # 页面当前表最后一个山东记录为最新价格
    current_price = candidates[-1]

    # --------------------------------------------------------
    # 找最近一次正式调价日期
    # --------------------------------------------------------

    adjustment_date = None

    adjustment_match = re.search(
        r"上次调价：(\d{2})-(\d{2})",
        page_text
    )

    if adjustment_match:

        month = adjustment_match.group(1)
        day = adjustment_match.group(2)

        year = beijing_now().year

        adjustment_date = (
            f"{year}-{month}-{day}"
        )

    return (
        current_price,
        page_date,
        adjustment_date
    )


# ============================================================
# 读取状态
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
# 计算运输成本
# ============================================================

def calculate_cost(price):

    fuel_liters = (
        DISTANCE_KM *
        FUEL_CONSUMPTION /
        100
    )

    cost = (
        fuel_liters *
        price
    )

    return fuel_liters, cost


# ============================================================
# 初始化历史文件
# ============================================================

def initialize_history():

    if os.path.exists(HISTORY_FILE):
        return

    with open(
        HISTORY_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "日期",
            "路线",
            "距离(km)",
            "油耗(L/100km)",
            "柴油价格(元/L)",
            "价格变化(元/L)",
            "变化类型",
            "单程用油(L)",
            "单程油费(元)",
            "每柜油费变化(元)",
            "历史最高油价(元/L)",
            "相比最高油价每柜节省(元)"
        ])


# ============================================================
# 写入历史
# ============================================================

def add_history(
    date,
    current_price,
    price_change,
    change_type,
    fuel_liters,
    current_cost,
    cost_change,
    highest_price,
    saving_vs_highest
):

    initialize_history()

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            date,
            ROUTE_NAME,
            DISTANCE_KM,
            FUEL_CONSUMPTION,
            f"{current_price:.2f}",
            f"{price_change:.2f}",
            change_type,
            f"{fuel_liters:.2f}",
            f"{current_cost:.2f}",
            f"{cost_change:.2f}",
            f"{highest_price:.2f}",
            f"{saving_vs_highest:.2f}"
        ])


# ============================================================
# 钉钉
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
            f"{timestamp}\n"
            f"{DINGTALK_SECRET}"
        )

        hmac_code = hmac.new(
            DINGTALK_SECRET.encode(
                "utf-8"
            ),
            string_to_sign.encode(
                "utf-8"
            ),
            digestmod=hashlib.sha256
        ).digest()

        sign = urllib.parse.quote_plus(
            base64.b64encode(
                hmac_code
            )
        )

        separator = (
            "&"
            if "?" in url
            else "?"
        )

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
            "Content-Type":
            "application/json"
        },
        timeout=20
    )

    response.raise_for_status()

    result = response.json()

    if result.get(
        "errcode",
        0
    ) != 0:

        raise Exception(
            f"钉钉发送失败：{result}"
        )


# ============================================================
# 主程序
# ============================================================

def main():

    now = beijing_now()

    today = now.strftime(
        "%Y-%m-%d"
    )

    current_time = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("=" * 60)
    print("山东0#柴油油价监控系统")
    print("=" * 60)

    print(
        f"北京时间：{current_time}"
    )

    # --------------------------------------------------------
    # 获取油价
    # --------------------------------------------------------

    (
        current_price,
        page_date,
        adjustment_date
    ) = get_shandong_diesel_price()

    print(
        f"山东0#柴油："
        f"{current_price:.2f} 元/L"
    )

    print(
        f"网页日期：{page_date}"
    )

    print(
        f"最近正式调价日期："
        f"{adjustment_date}"
    )

    # --------------------------------------------------------
    # 初始化历史文件
    # --------------------------------------------------------

    initialize_history()

    # --------------------------------------------------------
    # 读取状态
    # --------------------------------------------------------

    state = load_state()

    last_price = state.get(
        "last_price"
    )

    highest_price = state.get(
        "highest_price"
    )

    # --------------------------------------------------------
    # 第一次运行
    # --------------------------------------------------------

    if last_price is None:

        highest_price = current_price

        state = {
            "last_price":
                current_price,
            "highest_price":
                highest_price,
            "last_date":
                current_time
        }

        save_state(state)

        fuel_liters, cost = (
            calculate_cost(
                current_price
            )
        )

        message = (
            "⛽ 油价监控系统首次建立基准\n\n"
            f"时间：{current_time}\n"
            f"山东0#柴油："
            f"{current_price:.2f} 元/L\n\n"

            f"🚛 运输路线：{ROUTE_NAME}\n"
            f"📏 单程距离："
            f"{DISTANCE_KM} km\n"
            f"⛽ 油耗："
            f"{FUEL_CONSUMPTION} L/100km\n"
            f"🛢️ 单程用油："
            f"{fuel_liters:.2f} L\n"
            f"💰 单程油费："
            f"{cost:.2f} 元\n\n"

            "已建立油价基准，"
            "后续正式调价才提醒。"
        )

        send_dingtalk(message)

        print(
            "首次运行完成"
        )

        return

    # --------------------------------------------------------
    # 判断价格是否变化
    # --------------------------------------------------------

    change = (
        current_price -
        last_price
    )

    if abs(change) < 0.001:

        state["last_price"] = (
            current_price
        )

        state["last_date"] = (
            current_time
        )

        save_state(state)

        print(
            "油价没有变化，"
            "不发送钉钉消息。"
        )

        return

    # ========================================================
    # 关键防错机制
    # ========================================================

    # 只有网页明确显示：
    #
    # 最近一次正式调价日期 = 今天
    #
    # 才允许把价格变化认定为正式调价。
    #
    # 这会直接拦截：
    #
    # 2026-08-28 21:58
    # 7.36 → 7.79
    #
    # 因为8月28日当时正式调价日期仍然是8月15日。
    #
    # 2026-08-29 00:xx
    # 7.36 → 7.67
    #
    # 正式调价日期 = 8月29日
    #
    # 才会确认。

    if adjustment_date != today:

        print(
            "检测到价格变化，"
            "但网页尚未确认今天正式调价。"
        )

        print(
            f"当前价格：{current_price:.2f}"
        )

        print(
            f"上次价格：{last_price:.2f}"
        )

        print(
            "本次价格变化暂不认定为正式调价。"
        )

        return

    # --------------------------------------------------------
    # 正式调价
    # --------------------------------------------------------

    if current_price > highest_price:

        highest_price = current_price

    fuel_liters, current_cost = (
        calculate_cost(
            current_price
        )
    )

    _, previous_cost = (
        calculate_cost(
            last_price
        )
    )

    _, highest_cost = (
        calculate_cost(
            highest_price
        )
    )

    cost_change = (
        current_cost -
        previous_cost
    )

    saving_vs_highest = (
        highest_cost -
        current_cost
    )

    if change > 0:

        direction = "上涨"
        emoji = "🔴"
        cost_word = "增加"

    else:

        direction = "下跌"
        emoji = "🟢"
        cost_word = "减少"

    # --------------------------------------------------------
    # 写入正式历史
    # --------------------------------------------------------

    add_history(
        date=current_time,
        current_price=current_price,
        price_change=change,
        change_type=direction,
        fuel_liters=fuel_liters,
        current_cost=current_cost,
        cost_change=cost_change,
        highest_price=highest_price,
        saving_vs_highest=saving_vs_highest
    )

    # --------------------------------------------------------
    # 更新状态
    # --------------------------------------------------------

    state["last_price"] = (
        current_price
    )

    state["highest_price"] = (
        highest_price
    )

    state["last_date"] = (
        current_time
    )

    save_state(state)

    # --------------------------------------------------------
    # 钉钉
    # --------------------------------------------------------

    message = (
        f"{emoji} 山东0#柴油正式调价\n\n"

        f"调价生效时间："
        f"{today} 00:00\n\n"

        f"山东0#柴油："
        f"{current_price:.2f} 元/L\n"

        f"上次价格："
        f"{last_price:.2f} 元/L\n"

        f"本次{direction}："
        f"{abs(change):.2f} 元/L\n\n"

        f"🚛 运输路线："
        f"{ROUTE_NAME}\n"

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
        f"{highest_price:.2f} 元/L\n\n"

        f"📌 本次为正式调价，"
        f"已写入油价历史记录。"
    )

    send_dingtalk(message)

    print(
        "正式调价确认，"
        "已发送钉钉提醒。"
    )


if __name__ == "__main__":
    main()
