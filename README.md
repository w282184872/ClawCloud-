# 🚀 ClawCloud 自动登录保活脚本 (青龙面板通用版)

基于 Python + Playwright 的 ClawCloud 自动化登录与保活脚本。专为青龙面板（支持 Alpine / Debian 双系统架构）优化设计。

此脚本通过模拟真实浏览器环境，自动完成 GitHub OAuth 授权登录、区域检测、设备验证以及两步验证（2FA），并提取最新的 Session Cookie 用于后续保活。

## ✨ 核心特性

-   🤖 ****全自动无头浏览器****：基于 Playwright，智能绕过基础反爬检测。
-   🌍 ****智能区域检测****：自动识别 ClawCloud 账号所属区域（如 `ap-southeast-1` 等）并记录。
-   📱 ****Telegram 深度对接****：
-   -   自动推送登录页面截图，辅助确认状态。
    -   支持在 TG 接收验证提示，并通过发送 `/code 123456` 直接将验证码输入到无头浏览器中。
-   🛡️ ****双重验证 (2FA) 兼容****：完美支持 GitHub Mobile 手机端弹窗确认与 TOTP 验证码。
-   🧩 ****内核智能寻路****：自动探测青龙底层系统（Alpine / Debian），优先使用系统自带的 Chromium 内核以节省内存，防崩溃。

## 🛠️ 安装与配置指南 (青龙面板)

由于使用了真实的浏览器环境，本脚本的安装比普通 Python 脚本多一个****系统内核安装****步骤。请严格按照以下说明操作。

### 步骤一：添加 Python 依赖

在青龙面板的 ****依赖管理**** -> ****Python3**** 中，添加以下依赖并等待安装完成：

-   `playwright`
-   `requests`

### 步骤二：安装浏览器内核 (⚠️ 极其重要)

根据你的青龙面板底层系统，在 ****系统设置**** -> ****终端**** (或 SSH) 中执行相应的安装命令：

****如果你是轻量级的 Alpine 系统 (青龙默认/老版本)：****

Bash

apk add --no-cache chromium  

****如果你是 Debian 系统 (部分新版青龙/自建环境)：****

Bash

apt-get update  
apt-get install -y chromium chromium-sandbox  
\# 或者直接使用 playwright 官方命令：  
\# playwright install-deps chromium && playwright install chromium  

### 步骤三：添加环境变量

在青龙面板的 ****环境变量**** 中，添加以下变量：

| 变量名             | 是否必填  | 说明                                         |
| --------------- | ----- | ------------------------------------------ |
| GH_USERNAME     | 🔴 必填 | 你的 GitHub 登录用户名或邮箱                         |
| GH_PASSWORD     | 🔴 必填 | 你的 GitHub 登录密码                             |
| TG_BOT_TOKEN    | 🔴 必填 | Telegram Bot 的 Token，用于接收截图和输入验证码          |
| TG_CHAT_ID      | 🔴 必填 | 你的 Telegram 用户 ID                          |
| GH_SESSION      | 🟢 选填 | GitHub Session Cookie。首次运行留空即可。            |
| PROXY_DSN       | 🟢 选填 | 代理地址。国内服务器必填，格式：http://user:pass@host:port |
| TWO_FACTOR_WAIT | 🟢 选填 | 2FA 验证等待时间(秒)，默认 120                       |

## 🚀 使用教程

1.  ****新建脚本****：在青龙面板新建脚本（如 `clawcloud_login.py`），将完整代码粘贴进去。
2.  ****首次运行 (获取 Cookie)****：
3.  -   手动触发运行脚本。
    -   打开你的 Telegram，留意 Bot 发来的消息。
    -   如果遇到 ****设备验证****（新 IP 登录），请前往绑定的邮箱点击授权链接。
    -   如果遇到 ****两步验证 (2FA)****，请在手机 GitHub App 点击数字，或直接在 TG 回复验证码指令（例：`/code 123456`）。
4.  ****更新环境变量****：
5.  -   脚本跑通后，会在青龙****运行日志****的最下方，以及 ****Telegram**** 中输出一串完整的 Cookie。
    -   将这段完整的字符串复制，前往青龙面板的“环境变量”中，手动添加/更新 `GH_SESSION` 变量。
6.  ****日常保活****：
7.  -   设置定时任务（Cron 表达式，例如 `0 8 * * *` 每天早上 8 点运行一次）。
    -   有了 `GH_SESSION` 后，脚本会自动跳过密码和 2FA 验证，实现静默登录和保活。


创建 Telegram 机器人
在 Telegram 搜索 @BotFather，发送 /newbot 创建机器人。
设置名字和用户名（用户名需以 bot 结尾）。
获取 Token，填入 TG_BOT_TOKEN。
获取 Chat ID：私聊应用机器人，@KinhRoBot, 使用/id 命令


## ❓ 常见问题 (FAQ)

****Q1: 脚本报错**** **`**ModuleNotFoundError: No module named 'playwright'**`**

A: 你的 Python 环境还没安装 playwright。请回到【步骤一】，在面板的依赖管理中正确安装。

****Q2: 脚本报错**** **`**BrowserType.launch: Failed to launch chromium because executable doesn't exist...**`**

A: 你的青龙容器内没有浏览器内核！请仔细检查【步骤二】。如果你不知道自己的系统是什么，可以进入青龙终端先执行 `cat /etc/os-release` 查看，然后再选择对应的安装命令。

****Q3: 为什么不让脚本自动更新**** **`**GH_SESSION**`** ****环境变量？****

A: 因为青龙面板的各个版本迭代中，`auth.json` 的路径和鉴权 API 经常发生变动，容易导致自动更新失败。为了追求极简和稳定，本版本采用“日志输出 + 手动更新”的方式。你只需要手动更新一次，后续只要 Cookie 不过期就可以一直用。

****Q4: 运行一直卡在“正在启动系统自带 Chromium...”然后超时？****

A: 这通常发生在内存小于 1GB 的低配机器上。脚本已经开启了 `--disable-dev-shm-usage` 防崩溃参数。如果依然卡死，建议在宿主机增加 Swap 虚拟内存，或考虑更换更大内存的服务器。

## ⚠️ 免责声明

本项目仅供学习与交流使用，旨在学习 Playwright 的自动化与反爬机制。请勿用于任何非法、滥用或违反目标网站服务条款的用途。因使用本脚本产生的任何账号封禁或数据丢失，风险由使用者自行承担。


改自作者@frankiejun  https://github.com/frankiejun/ClawCloud-Run
