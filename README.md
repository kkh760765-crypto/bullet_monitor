# 三角洲行动 - 子弹价格监控(QQ邮箱通知版)

实时监控 [准星代售工具站](https://tool.zxfps.com) 上的 `12.7x55mm PD12双头弹` 子弹价格，当价格低于阈值时通过 **QQ邮箱** 发送预警。

## 工作原理

```
GitHub Actions (定时触发, 每10分钟)
    ↓
Playwright 浏览器加载子弹列表页 (自动处理JS加密鉴权)
    ↓
调用网站加密API获取 PD12双头弹 当前价格
    ↓ 低于阈值？
QQ邮箱发送预警邮件
```

## 快速开始

### 1. 创建 GitHub 公开仓库

在 GitHub 新建一个**公开**仓库（公开仓库 Actions 无限免费）。

### 2. 获取 QQ 邮箱 SMTP 授权码

1. 登录 QQ邮箱网页版
2. 设置 → 账户 → POP3/IMAP/SMTP 服务
3. 开启 **SMTP 服务**
4. 按提示发送短信后会生成一个 **16位授权码**（不是QQ密码）

### 3. 配置参数

编辑 `config.json`：

```json
{
    "bullet_name": "12.7x55mm PD12双头弹",
    "low_price_threshold": 2000,
    "email": {
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "sender": "123456789@qq.com",
        "password": "你的SMTP授权码",
        "receiver": "接收通知的邮箱@qq.com"
    },
    "cooldown_minutes": 60
}
```

| 参数 | 说明 |
|------|------|
| `bullet_name` | 监控的子弹名称 |
| `low_price_threshold` | 预警阈值，低于此值触发邮件 |
| `email.sender` | 发件QQ邮箱 |
| `email.password` | **SMTP授权码**（不是QQ密码！） |
| `email.receiver` | 接收通知的邮箱（可填自己QQ邮箱） |
| `cooldown_minutes` | 同阈值重复通知的最小间隔 |

### 4. 推送到 GitHub

```bash
git init
git add .
git commit -m "子弹价格监控"
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

### 5. 手动测试

Actions → 子弹价格监控 → **Run workflow** → 等待2分钟查看结果和邮件

## 监控间隔调整

编辑 `.github/workflows/monitor.yml`，修改 cron 表达式：

```yaml
on:
  schedule:
    - cron: "*/10 * * * *"   # 每10分钟
    # - cron: "*/30 * * * *" # 每30分钟
    # - cron: "0 * * * *"    # 每小时
```

## 本地测试

```bash
pip install -r requirements.txt
playwright install chromium
python monitor.py
```

## 费用

| 仓库类型 | GitHub Actions |
|----------|---------------|
| **公开仓库** | **无限免费** |
| 私有仓库 | 2000分钟/月 |
