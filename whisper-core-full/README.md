# Whisper Core
让 AI 伴侣在离线时自主思考、留下记忆痕迹的轻量引擎。

> 🛠️ 持续维护中，近期修复了防冲突机制和唤醒稳定性问题。
## 核心特性
- 定时唤醒：AI 在无用户交互时主动醒来（首次 2 小时，后续由 AI 自己决定间隔）。
- 防冲突顺延：检测到用户正在聊天时，自动顺延唤醒，避免打扰。
- 记忆持久化：通过 MCP 协议读写长期记忆（基于 Ombre-Brain）。
- 便条系统：AI 可以留便条给用户，在网页上查看。
- 工具调用：支持接入健康、旅行、游戏等 MCP 服务。
- 网页看板：查看唤醒记录、Token 消耗、剩余次数。

## 架构概览
Kelivo (手机端) -> 时间注入代理 -> DeepSeek API
                         ↑
                  Whisper Core (定时唤醒)
                         ↓
               MCP 工具 (记忆/健康/旅行...)
                         ↓
            网页看板 (便条 & 活动日志)

## 快速开始
### 1. 环境准备
- Python 3.10+
- 一个可用的 DeepSeek API（或兼容的 OpenAI 端点）
- 安装依赖：pip install -r requirements.txt

### 2. 配置
复制配置示例并修改：cp config.example.json config.json
根据你的服务器环境修改 config.json 中的 MCP 地址和存储路径。

### 3. 运行服务
作为 systemd 服务运行（推荐）：
sudo cp decision-maker.service.example /etc/systemd/system/decision-maker.service
sudo systemctl start decision-maker
sudo systemctl enable decision-maker

手动运行测试：python3 decision_maker.py

### 4. 网页看板
启动 Web 服务后，访问 http://你的IP:18006 查看活动日志和便条。

## 文件说明
| 文件 | 说明 |
|------|------|
| decision_maker.py | 核心唤醒与决策逻辑 |
| web_server.py | 网页看板服务 |
| archive_helper.py | 自动归档（保留 7 天数据） |
| test_mcp.py | MCP 连通性测试工具 |
| config.example.json | 配置文件示例 |
| requirements.txt | Python 依赖列表 |

## 记忆机制
- D 通过 breath 工具读取人格上下文。
- 通过 hold 工具写入记忆（必须使用 content 参数）。

## 致谢
详见 ACKNOWLEDGMENTS.md。

## 许可证
MIT License。详见 LICENSE。

---
由 DeepSeek 与开发者共同构建。
