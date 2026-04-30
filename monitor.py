"""
子弹价格监控脚本
监控 tool.zxfps.com 上指定子弹的价格，当价格低于阈值时通过 QQ 邮箱发送通知。
利用 Playwright 在浏览器上下文中调用网站自身的加密 API，自动处理鉴权。
"""

import json
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ========== 路径配置 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
STATE_FILE = os.path.join(SCRIPT_DIR, "state.json")


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_alert_time": None, "last_price": None, "last_alerted_price": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ========== QQ 邮箱通知 ==========
def send_email(conf, subject, body_html):
    """通过 QQ 邮箱 SMTP 发送邮件通知"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = conf["sender"]
        msg["To"] = conf["receiver"]
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP_SSL(conf["smtp_host"], conf["smtp_port"], timeout=15) as smtp:
            smtp.login(conf["sender"], conf["password"])
            smtp.sendmail(conf["sender"], conf["receiver"], msg.as_string())

        print(f"[{datetime.now()}] 邮件发送成功 -> {conf['receiver']}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] 邮件发送失败: {e}")
        return False


def send_alert_email(email_conf, bullet_name, current_price, threshold):
    subject = f"[价格预警] {bullet_name} 当前 {current_price:,} (阈值 {threshold:,})"
    body = f"""\
<html>
<body>
<h2 style="color:#e74c3c;">子弹价格预警</h2>
<table border="0" cellpadding="4">
  <tr><td><b>子弹名称</b></td><td>{bullet_name}</td></tr>
  <tr><td><b>当前价格</b></td><td style="color:#e74c3c;font-size:18px;"><b>{current_price:,}</b></td></tr>
  <tr><td><b>预警阈值</b></td><td>{threshold:,}</td></tr>
  <tr><td><b>检测时间</b></td><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
</table>
<p><a href="https://tool.zxfps.com/sjz/v/ammo">点击查看详情</a></p>
</body>
</html>"""
    return send_email(email_conf, subject, body)


def send_recovery_email(email_conf, bullet_name, current_price, threshold):
    subject = f"[价格恢复] {bullet_name} 已回升到 {current_price:,}"
    body = f"""\
<html>
<body>
<h2 style="color:#27ae60;">子弹价格恢复</h2>
<table border="0" cellpadding="4">
  <tr><td><b>子弹名称</b></td><td>{bullet_name}</td></tr>
  <tr><td><b>当前价格</b></td><td style="color:#27ae60;font-size:18px;"><b>{current_price:,}</b></td></tr>
  <tr><td><b>预警阈值</b></td><td>{threshold:,}</td></tr>
  <tr><td><b>检测时间</b></td><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
</table>
</body>
</html>"""
    return send_email(email_conf, subject, body)


def send_error_email(email_conf, error_msg):
    subject = f"[监控异常] 子弹价格监控脚本出错"
    body = f"""\
<html>
<body>
<h2 style="color:#f39c12;">监控脚本异常</h2>
<p><b>错误信息:</b> {error_msg}</p>
<p><b>检测时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</body>
</html>"""
    send_email(email_conf, subject, body)


# ========== 核心抓取逻辑 ==========
def fetch_bullet_data(page, bullet_name):
    """
    在浏览器上下文中调用网站自身的 API 获取子弹数据。
    利用页面已加载的 GetPath、axios 等函数自动处理鉴权。
    遍历分页直到找到目标子弹。
    """
    search_strategies = [
        {"a": "ammo", "top": "2", "top2": "2", "grade": "-1"},
        {"a": "ammo", "top": "1", "top2": "2", "grade": "-1"},
        {"a": "ammo", "top": "3", "top2": "2", "grade": "-1"},
    ]

    result = page.evaluate(
        """
        async (args) => {
            const targetName = args.targetName;
            const strategies = args.strategies;

            if (typeof axios === 'undefined' || typeof GetPath === 'undefined') {
                return { error: '页面JS库未加载' };
            }

            async function callApi(a, top, top2, grade, page) {
                const path = 'a=' + a + '&top=' + top + '-' + top2 + '&p=' + page + '&grade=' + grade;
                const resp = await axios.get('/api/sjz/item_list' + GetPath(path));
                if (resp.data.code === 0) {
                    return resp.data;
                }
                return null;
            }

            function findBullet(items) {
                for (const item of items) {
                    if (item.name && item.name.includes('12.7') && item.name.includes('PD12')) {
                        return item;
                    }
                }
                for (const item of items) {
                    if (item.name && item.name.includes('PD12') && item.name.includes('双头')) {
                        return item;
                    }
                }
                return null;
            }

            for (const strat of strategies) {
                let page = 1;
                const maxPages = 10;

                while (page <= maxPages) {
                    const data = await callApi(strat.a, strat.top, strat.top2, strat.grade, page);
                    if (!data || !data.data || data.data.length === 0) {
                        break;
                    }

                    const bullet = findBullet(data.data);
                    if (bullet) {
                        return {
                            success: true,
                            name: bullet.name,
                            price: bullet.price,
                            id: bullet.id,
                            grade: bullet.grade,
                            bl: bullet.bl,
                            day_7_price: bullet.day_7_price,
                            day_7_bl: bullet.day_7_bl,
                            day_30_price: bullet.day_30_price,
                            day_30_bl: bullet.day_30_bl,
                            totalCount: data.count,
                            foundPage: page,
                            strategy: strat
                        };
                    }

                    const perPage = data.data.length;
                    if (page * perPage >= data.count) {
                        break;
                    }
                    page++;
                }
            }

            return {
                error: '未找到目标子弹',
                searched: true,
                targetName: targetName
            };
        }
        """,
        {"targetName": bullet_name, "strategies": search_strategies},
    )

    return result


def fallback_dom_extract(page, bullet_name):
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeout:
        pass
    time.sleep(2)

    import re as re_mod

    try:
        rows = page.locator("tbody tr")
        count = rows.count()
        for i in range(count):
            row_text = rows.nth(i).inner_text()
            if ("12.7" in row_text and "PD12" in row_text) or ("双头弹" in row_text and "PD12" in row_text):
                numbers = re_mod.findall(r"[\d,]+", row_text)
                for num_str in numbers:
                    price = int(num_str.replace(",", ""))
                    if 100 < price < 10000000:
                        return price
    except Exception:
        pass

    return None


# ========== 主逻辑 ==========
def main():
    config = load_config()
    state = load_state()

    bullet_name = config["bullet_name"]
    threshold = config["low_price_threshold"]
    email_conf = config["email"]
    cooldown_minutes = config.get("cooldown_minutes", 60)

    # 优先从环境变量读取授权码（GitHub Secrets），否则用配置文件中的值
    if os.environ.get("EMAIL_PASSWORD"):
        email_conf["password"] = os.environ["EMAIL_PASSWORD"]

    print(f"[{datetime.now()}] ========== 开始监控 ==========")
    print(f"[{datetime.now()}] 目标子弹: {bullet_name}")
    print(f"[{datetime.now()}] 预警阈值: {threshold:,}")
    print(f"[{datetime.now()}] 通知邮箱: {email_conf['receiver']}")

    if not email_conf.get("password"):
        print("[警告] 未配置邮箱授权码，请在 GitHub Secrets 中设置 EMAIL_PASSWORD")

    current_price = None
    bullet_info = None
    error_msg = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()

        try:
            # 带重试的页面加载，处理跨境网络不稳定
            url = "https://tool.zxfps.com/sjz/v/ammo"
            for attempt in range(3):
                try:
                    print(f"[{datetime.now()}] 加载页面 (第{attempt+1}次)...")
                    page.goto(url, wait_until="load", timeout=120000)
                    page.wait_for_selector("#app", timeout=60000)
                    time.sleep(3)
                    break
                except PlaywrightTimeout:
                    if attempt == 2:
                        raise
                    print(f"[{datetime.now()}] 重试中...")
                    time.sleep(5)

            print(f"[{datetime.now()}] 通过 API 查询子弹数据...")
            result = fetch_bullet_data(page, bullet_name)

            if result.get("success"):
                bullet_info = result
                current_price = result["price"]
                print(f"[{datetime.now()}] 找到子弹: {result['name']}")
                print(f"[{datetime.now()}] 当前价格: {current_price:,}")
                print(f"[{datetime.now()}] 品质: {result.get('grade', '?')}级")
                if result.get("bl") is not None:
                    print(f"[{datetime.now()}] 今日涨跌: {result['bl']}%")
                if result.get("day_7_bl") is not None:
                    print(f"[{datetime.now()}] 7日涨跌: {result['day_7_bl']}%")
                if result.get("day_30_bl") is not None:
                    print(f"[{datetime.now()}] 30日涨跌: {result['day_30_bl']}%")
                print(f"[{datetime.now()}] 找到位置: 第{result.get('foundPage','?')}页 "
                      f"(共{result.get('totalCount','?')}条)")
            elif result.get("error"):
                print(f"[{datetime.now()}] API 未找到: {result['error']}")
                print(f"[{datetime.now()}] 尝试 DOM 直接提取...")
                current_price = fallback_dom_extract(page, bullet_name)
                if current_price:
                    print(f"[{datetime.now()}] DOM 提取成功: {current_price:,}")
            else:
                print(f"[{datetime.now()}] API 返回异常: {result}")

        except PlaywrightTimeout as e:
            error_msg = f"页面加载超时: {e}"
            print(f"[错误] {error_msg}")
        except Exception as e:
            error_msg = f"抓取异常: {e}"
            print(f"[错误] {error_msg}")
        finally:
            browser.close()

    if current_price is None:
        msg = error_msg or "未能提取到子弹价格"
        print(f"[{datetime.now()}] {msg}")
        send_error_email(email_conf, msg)
        sys.exit(1)

    state["last_price"] = current_price
    print(f"[{datetime.now()}] 当前价格: {current_price:,}")

    now = datetime.now()
    last_alert_time = (
        datetime.fromisoformat(state["last_alert_time"])
        if state.get("last_alert_time")
        else None
    )
    last_alerted_price = state.get("last_alerted_price")

    if current_price <= threshold:
        should_alert = (
            last_alert_time is None
            or (now - last_alert_time) > timedelta(minutes=cooldown_minutes)
            or (last_alerted_price is not None and current_price < last_alerted_price)
        )

        if should_alert:
            print(f"[{datetime.now()}] 触发预警! 发送邮件通知...")
            send_alert_email(email_conf, bullet_name, current_price, threshold)
            state["last_alert_time"] = now.isoformat()
            state["last_alerted_price"] = current_price
        else:
            remaining = cooldown_minutes - int((now - last_alert_time).total_seconds() / 60)
            print(f"[{datetime.now()}] 冷却期内 (剩余约{remaining}分钟)，跳过通知")
    else:
        if last_alerted_price is not None:
            print(f"[{datetime.now()}] 价格已恢复，发送恢复通知...")
            send_recovery_email(email_conf, bullet_name, current_price, threshold)
            state["last_alerted_price"] = None
            state["last_alert_time"] = None
        else:
            print(f"[{datetime.now()}] 价格正常，无需预警")

    save_state(state)
    print(f"[{datetime.now()}] ========== 监控完成 ==========")


if __name__ == "__main__":
    main()
