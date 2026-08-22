import os
import csv
import time
import hashlib
import hmac
import base64
import urllib.parse
from datetime import datetime, timedelta

import requests


# ============================================================
# 基础配置
# ============================================================

HISTORY_FILE = "oil_history.csv"

ROUTE_NAME = "青岛港 → 郓城"
DISTANCE_KM = 509
FUEL_CONSUMPTION = 35

DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")


# ============================================================
# 计算单程用油
# ============================================================

FUEL_LITERS = (
    DISTANCE_KM *
    FUEL_CONSUMPTION /
    100
)


# ============================================================
# 计算油费
# ============================================================

def calculate_cost(price):

    return FUEL_LITERS * price


# ============================================================
# 获取上个月
# ============================================================

def get_previous_month():

    today = datetime.now()

    first_day_this_month = today.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    last_day_previous_month = (
        first_day_this_month -
        timedelta(days=1)
    )

    month = last_day_previous_month.strftime("%Y-%m")

    return month


# ============================================================
# 读取历史记录
# ============================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):

        return []

    records = []

    with open(
        HISTORY_FILE,
        "r",
        encoding="utf-8-sig"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if not row.get("日期"):
                continue

            records.append(row)

    return records


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

    month = get_previous_month()

    print("=" * 60)
    print("油价月度自动汇总")
    print("=" * 60)
    print(f"统计月份：{month}")

    records = load_history()

    # --------------------------------------------------------
    # 筛选上个月的数据
    # --------------------------------------------------------

    month_records = []

    for record in records:

        date_text = record.get("日期", "")

        if date_text.startswith(month):

            month_records.append(record)

    # --------------------------------------------------------
    # 如果没有调价记录
    # --------------------------------------------------------

    if not month_records:

        message = (
            "📊 油价月度自动报告\n\n"
            f"统计月份：{month}\n\n"
            "本月没有记录到油价变化。\n"
            "油价保持稳定，因此没有产生调价记录。\n\n"
            f"🚛 运输路线：{ROUTE_NAME}\n"
            f"📏 单程距离：{DISTANCE_KM} km\n"
            f"⛽ 油耗：{FUEL_CONSUMPTION} L/100km\n"
            f"🛢️ 单程用油：{FUEL_LITERS:.2f} L"
        )

        send_dingtalk(message)

        print("本月没有油价变化。")

        return

    # --------------------------------------------------------
    # 数据统计
    # --------------------------------------------------------

    prices = []

    increases = 0
    decreases = 0

    total_cost_change = 0

    details = []

    for record in month_records:

        try:

            price = float(
                record["柴油价格(元/L)"]
            )

            change = float(
                record["价格变化(元/L)"]
            )

            cost = float(
                record["单程油费(元)"]
            )

            cost_change = float(
                record["每柜油费变化(元)"]
            )

        except Exception:

            continue

        prices.append(price)

        total_cost_change += cost_change

        change_type = record.get(
            "变化类型",
            ""
        )

        if change_type == "上涨":

            increases += 1

        elif change_type == "下跌":

            decreases += 1

        details.append(
            (
                record["日期"],
                price,
                change,
                change_type,
                cost,
                cost_change
            )
        )

    # --------------------------------------------------------
    # 如果解析后没有有效数据
    # --------------------------------------------------------

    if not prices:

        message = (
            "📊 油价月度自动报告\n\n"
            f"统计月份：{month}\n\n"
            "本月没有有效的油价历史数据。"
        )

        send_dingtalk(message)

        return

    # --------------------------------------------------------
    # 月度数据
    # --------------------------------------------------------

    highest_price = max(prices)

    lowest_price = min(prices)

    first_price = prices[0]

    last_price = prices[-1]

    first_cost = calculate_cost(
        first_price
    )

    last_cost = calculate_cost(
        last_price
    )

    monthly_price_change = (
        last_price -
        first_price
    )

    monthly_cost_change = (
        last_cost -
        first_cost
    )

    # --------------------------------------------------------
    # 调价明细
    # --------------------------------------------------------

    detail_text = ""

    for item in details:

        date_text = item[0]
        price = item[1]
        change = item[2]
        change_type = item[3]
        cost = item[4]
        cost_change = item[5]

        if change_type == "上涨":

            icon = "🔴"

        else:

            icon = "🟢"

        detail_text += (
            f"{icon} {date_text}\n"
            f"   {price:.2f} 元/L "
            f"({change_type} {abs(change):.2f})\n"
            f"   单程油费：{cost:.2f} 元\n"
            f"   每柜变化："
            f"{'+' if cost_change > 0 else ''}"
            f"{cost_change:.2f} 元\n"
        )

    # --------------------------------------------------------
    # 月度总结
    # --------------------------------------------------------

    if monthly_cost_change > 0:

        monthly_cost_text = (
            f"增加 {monthly_cost_change:.2f} 元"
        )

    elif monthly_cost_change < 0:

        monthly_cost_text = (
            f"节省 {abs(monthly_cost_change):.2f} 元"
        )

    else:

        monthly_cost_text = "基本不变"

    if monthly_price_change > 0:

        price_change_text = (
            f"上涨 {monthly_price_change:.2f} 元/L"
        )

    elif monthly_price_change < 0:

        price_change_text = (
            f"下跌 {abs(monthly_price_change):.2f} 元/L"
        )

    else:

        price_change_text = "基本不变"

    # --------------------------------------------------------
    # 钉钉月报
    # --------------------------------------------------------

    message = (
        "📊 油价月度自动报告\n"
        "━━━━━━━━━━━━━━\n\n"

        f"📅 统计月份：{month}\n\n"

        f"⛽ 月度最高油价："
        f"{highest_price:.2f} 元/L\n"

        f"⛽ 月度最低油价："
        f"{lowest_price:.2f} 元/L\n\n"

        f"📈 月初记录价格："
        f"{first_price:.2f} 元/L\n"

        f"📉 月末记录价格："
        f"{last_price:.2f} 元/L\n"

        f"📊 月度变化："
        f"{price_change_text}\n\n"

        f"🔄 当月调价次数："
        f"{len(details)} 次\n"

        f"🔴 上涨次数："
        f"{increases} 次\n"

        f"🟢 下跌次数："
        f"{decreases} 次\n\n"

        f"🚛 运输路线：{ROUTE_NAME}\n"
        f"📏 单程距离：{DISTANCE_KM} km\n"
        f"⛽ 油耗：{FUEL_CONSUMPTION} L/100km\n"
        f"🛢️ 单程用油：{FUEL_LITERS:.2f} L\n\n"

        f"💰 月初单程油费："
        f"{first_cost:.2f} 元\n"

        f"💰 月末单程油费："
        f"{last_cost:.2f} 元\n"

        f"🚛 每个40尺柜月度油费变化："
        f"{monthly_cost_text}\n\n"

        "📋 当月调价明细\n"
        "━━━━━━━━━━━━━━\n"
        f"{detail_text}"
    )

    send_dingtalk(message)

    print("月度报告已发送到钉钉。")


if __name__ == "__main__":
    main()
