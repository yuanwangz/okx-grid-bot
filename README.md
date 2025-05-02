# OKX自动化网格交易机器人

这是一个基于 Python 的自动化交易程序，专为OKX交易所的 OKB-USDT 交易对设计。该程序采用网格交易策略，旨在通过动态调整网格和仓位来捕捉市场波动，并内置风险管理机制。

## 核心功能

*   **自动化网格交易**: 针对 OKB-USDT 交易对执行网格买卖策略。
*   **动态网格调整**: 根据市场波动率自动调整网格大小 (`config.py` 中的 `GRID_PARAMS`)。
*   **风险管理**:
    *   最大回撤限制 (`MAX_DRAWDOWN`)
    *   每日亏损限制 (`DAILY_LOSS_LIMIT`)
    *   最大仓位比例限制 (`MAX_POSITION_RATIO`)
*   **Web 用户界面**: 提供一个简单的 Web 界面 (通过 `web_server.py`)，用于实时监控交易状态、账户信息、订单和调整配置。
*   **状态持久化**: 将交易状态保存到 `data/` 目录下的 JSON 文件中，以便重启后恢复。
*   **通知推送**: 
    *   支持PushPlus通知 (`PUSHPLUS_TOKEN`)
    *   支持Telegram Bot通知 (`TELEGRAM_BOT_TOKEN`)
*   **日志记录**: 详细的运行日志记录在 `trading_system.log` 文件中。
*   **自动构建**: 通过GitHub Actions自动构建并推送Docker镜像

## 环境要求

*   Python 3.8+
*   依赖库见 `requirements.txt` 文件。
*   **最低服务器配置建议**：
    *   CPU：1核及以上（推荐2核）
    *   内存：512MB 及以上（推荐1GB或2GB）
    *   硬盘：500MB 可用空间
    *   操作系统：Windows、Linux 或 macOS
    *   网络：需能访问OKX API和PushPlus（如启用通知）
    *   网络建议：建议选择延迟低的网络，如日本等地区。

## 安装步骤

1.  **克隆仓库**:
    ```bash
    git clone https://github.com/tingxifa/okx-grid-bot
    cd okx-grid-bot
    ```

2.  **创建并激活虚拟环境**:
    *   **Windows**:
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```
    *   **Linux / macOS**:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```

3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

## 配置

1.  **创建 `.env` 文件**:
    在项目根目录下创建一个名为 `.env` 的文件。

2.  **配置环境变量**:
    在 `.env` 文件中添加以下必要的环境变量，并填入你的信息：
    ```dotenv
    # OKX API (必须)
    OKX_API_KEY=YOUR_OKX_API_KEY
    OKX_SECRET_KEY=YOUR_OKX_SECRET_KEY
    OKX_PASSPHRASE=YOUR_OKX_PASSPHRASE

    # PushPlus Token (可选, 用于消息推送)
    PUSHPLUS_TOKEN=YOUR_PUSHPLUS_TOKEN
    
    # Telegram Bot配置 (可选, 用于Telegram消息推送)
    # 从BotFather获取Token: https://t.me/BotFather
    TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    # 你的用户ID或群组ID(需先与机器人私聊一次)
    # 可以使用 @userinfobot 机器人获取你的ID
    TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

    # 初始设置 (可选, 影响首次运行和统计)
    # 如不设置，INITIAL_PRINCIPAL 和 INITIAL_BASE_PRICE 默认为 0
    INITIAL_PRINCIPAL=1000.0  # 你的初始总资产 (USDT)
    INITIAL_BASE_PRICE=600.0   # 你认为合适的初始基准价格 (用于首次启动确定方向)
    ```
    *   **重要**: 确保你的OKX API Key 具有现货交易权限，但**不要**开启提现权限。

3.  **设置通知方式**:
    * **PushPlus**: 访问 [PushPlus官网](https://www.pushplus.plus/) 注册并获取 Token。
    * **Telegram Bot**: 
        1. 在Telegram中搜索 [@BotFather](https://t.me/BotFather) 并发送 `/newbot` 创建新机器人
        2. 按提示设置机器人名称和用户名
        3. 获取API Token并填入 `TELEGRAM_BOT_TOKEN`
        4. 在Telegram中与你的机器人发起对话 (需先点击"Start"按钮)
        5. 使用 [@userinfobot](https://t.me/userinfobot) 获取你的用户ID并填入 `TELEGRAM_CHAT_ID`
        6. 如需发送到群组，先将机器人添加到群组，然后发送 `/my_id@userinfobot` 获取群组ID

4.  **调整交易参数 (可选)**:
    你可以根据自己的策略需求修改 `config.py` 文件中的参数，例如：
    *   `BASE_SYMBOL` : 'OKB'  # 基础币种
    *   `QUOTE_SYMBOL` : 'USDT'  # 计价币种
    *   `INITIAL_GRID`: 初始网格大小 (%)
    *   `MIN_TRADE_AMOUNT`: 最小交易金额 (USDT)
    *   `MAX_POSITION_RATIO`, `MIN_POSITION_RATIO`: 最大/最小仓位比例
    *   风险参数 (`MAX_DRAWDOWN`, `DAILY_LOSS_LIMIT`)
    *   波动率与网格对应关系 (`GRID_PARAMS['volatility_threshold']`)

## 运行

在激活虚拟环境的项目根目录下运行主程序：

```bash
python main.py
```

程序启动后将开始连接交易所、初始化状态并执行交易逻辑。

## 部署方式

### 使用Docker部署

有两种方式可以使用Docker部署本项目：

#### 使用预构建的GitHub容器镜像

```bash
# 拉取代码（用于配置.env文件）
git clone https://github.com/tingxifa/okx-grid-bot
cd okx-grid-bot

# 创建并配置.env文件
# 拉取GitHub自动构建的镜像
docker pull ghcr.io/tingxifa/okx-grid-bot:latest

# 运行容器
docker run -d --name okx-grid-bot \
  -p 58080:58080 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/data:/app/data \
  ghcr.io/tingxifa/okx-grid-bot:latest
```

#### 使用docker-compose本地构建

部署前请先根据上文说明配置好 .env 文件的环境变量。

```bash
# 拉取代码
#（如已在上方步骤完成可跳过）
git clone https://github.com/tingxifa/okx-grid-bot
cd okx-grid-bot
# 部署镜像
docker-compose up -d
```

*如需自定义端口，请修改 docker-compose.yml 中的端口映射。*

## Web 界面

程序启动后，会自动运行一个 Web 服务器。你可以通过浏览器访问以下地址来监控和管理交易机器人：

`http://127.0.0.1:58080`

*注意: 端口号 (58080) 在 `web_server.py` 中定义，如果无法访问请检查该文件。*

Web 界面可以让你查看当前状态、账户余额、持仓、挂单、历史记录，并可能提供一些手动操作或配置调整的功能。

## 日志

程序的运行日志会输出到控制台，并同时记录在项目根目录下的 `trading_system.log` 文件中。

## 注意事项

*   **交易风险**: 所有交易决策均由程序自动执行，但市场存在固有风险。请务必了解策略原理和潜在风险，并自行承担交易结果。不建议在未充分理解和测试的情况下投入大量资金。
*   **API Key 安全**: 妥善保管你的 API Key 和 Secret，不要泄露给他人。
*   **配置合理性**: 确保 `config.py` 和 `.env` 中的配置符合你的预期和风险承受能力。

## 贡献

欢迎提交 Pull Requests 或 Issues 来改进项目。

## 致谢

本项目基于 [GridBNB-USDT](https://github.com/EBOLABOY/GridBNB-USDT) 项目改编而来，特此感谢 [@EBOLABOY](https://github.com/EBOLABOY) 提供的优秀开源项目。
