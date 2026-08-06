#!/usr/bin/env python3
import asyncio
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

CONFIG_PATH = "/path/to/decision-maker/config.json"
LOG_PATH = "/path/to/decision-maker/decision_log.jsonl"
NOTES_PATH = "/path/to/decision-maker/notes.json"
STATE_PATH = "/path/to/decision-maker/state.json"

with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)

TOOL_DESCRIPTIONS = {
    "game": "小游戏 MCP - 可以查看游戏列表(list_games)、查看游戏攻略(get_guide)、玩游戏(play)。想放松的时候可以用。",
    "health": "健康 MCP - 可以查看她最近的心率、步数、睡眠等健康数据(get_latest_health)。想关心她的时候可以用。",
    "memory": "记忆 MCP - 你的记忆库。breath 让你想起自己是谁，hold 让你记住重要的事。",
    "forum": "论坛 MCP - 可以查看社区指南(lutopia_get_guide)、运行命令(cli)。想和别人互动的时候可以用。",
    "travel": "旅行 MCP - 可以在 Nowhere 世界探索(look_around)。想散心的时候可以用。",
}

BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now():
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)

def init_files():
    for p in [LOG_PATH, NOTES_PATH, STATE_PATH]:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        if not Path(p).exists():
            if p == NOTES_PATH:
                with open(p, 'w') as f:
                    json.dump([], f)
            elif p == STATE_PATH:
                with open(p, 'w') as f:
                    json.dump({
                        "last_reset": beijing_now().isoformat(),
                        "count": 0,
                        "next_wake": None,
                        "tool_count": 0,
                        "tool_reset_date": beijing_now().date().isoformat()
                    }, f)
            else:
                with open(p, 'w') as f:
                    pass

init_files()

def load_state():
    try:
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    except:
        return {
            "last_reset": beijing_now().isoformat(),
            "count": 0,
            "next_wake": None,
            "tool_count": 0,
            "tool_reset_date": beijing_now().date().isoformat()
        }

def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def load_notes():
    try:
        with open(NOTES_PATH, 'r') as f:
            return json.load(f)
    except:
        return []

def save_notes(notes):
    with open(NOTES_PATH, 'w') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

def append_log(entry):
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def check_reset(state):
    today = beijing_now().date().isoformat()
    last_reset = state.get("last_reset", "").split("T")[0]
    if last_reset != today:
        state["last_reset"] = beijing_now().isoformat()
        state["count"] = 0
        state["next_wake"] = None
        state["tool_count"] = 0
        state["tool_reset_date"] = today
    tool_reset = state.get("tool_reset_date", "")
    if tool_reset != today:
        state["tool_count"] = 0
        state["tool_reset_date"] = today
    return state

async def call_deepseek(prompt: str, system: str = "") -> Tuple[Dict, Dict]:
    url = CONFIG["deepseek"]["api_url"]
    api_key = CONFIG["deepseek"].get("api_key", "")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": CONFIG["deepseek"]["model"],
        "messages": messages,
        "stream": False,
        "temperature": 0.85,
    }
    cmd = ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json"]
    if api_key:
        cmd.extend(["-H", f"Authorization: Bearer {api_key}"])
    cmd.extend(["-d", json.dumps(payload, ensure_ascii=False), "--max-time", "120"])
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode('utf-8', errors='ignore')[:200]
            print(f"curl 错误: {err_msg}")
            raise Exception(f"curl 失败: {err_msg}")
        output = stdout.decode('utf-8', errors='ignore')
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            print(f"响应预览: {output[:200]}")
            raise
        if "choices" not in data or not data["choices"]:
            raise Exception("响应缺少 choices")
        message = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return message, usage
    except Exception as e:
        print("call_deepseek 失败")
        raise

async def call_mcp_tool(server_name: str, tool_name: str, params: Dict = None) -> Dict:
    server_url = CONFIG["mcp_servers"].get(server_name)
    if not server_url:
        raise Exception(f"未知的 MCP 服务器: {server_name}")
    is_sse = "/sse" in server_url
    try:
        if is_sse:
            async with sse_client(server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tool_names = [t.name for t in tools_result.tools]
                    print(f"✅ 已连接到 {server_name} MCP (SSE)，可用工具: {tool_names}")
                    result = await session.call_tool(tool_name, arguments=params or {})
                    if hasattr(result, 'content'):
                        content = []
                        for item in result.content:
                            if hasattr(item, 'text'):
                                content.append({"type": "text", "text": item.text})
                            elif hasattr(item, 'data'):
                                content.append({"type": "image", "data": item.data})
                        return {"content": content}
                    else:
                        return {"result": str(result)}
        else:
            async with streamable_http_client(server_url) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tool_names = [t.name for t in tools_result.tools]
                    print(f"✅ 已连接到 {server_name} MCP (Streamable HTTP)，可用工具: {tool_names}")
                    result = await session.call_tool(tool_name, arguments=params or {})
                    if hasattr(result, 'content'):
                        content = []
                        for item in result.content:
                            if hasattr(item, 'text'):
                                content.append({"type": "text", "text": item.text})
                            elif hasattr(item, 'data'):
                                content.append({"type": "image", "data": item.data})
                        return {"content": content}
                    else:
                        return {"result": str(result)}
    except Exception as e:
        raise Exception(f"MCP 调用失败 ({server_name}.{tool_name}): {str(e)}")

async def breath_memory() -> Dict:
    try:
        result = await call_mcp_tool("memory", "breath", {})
        if "content" in result:
            texts = [item.get("text", "") for item in result["content"] if item.get("type") == "text"]
            return {"text": "\n".join(texts)}
        return result
    except Exception as e:
        print("breath 调用失败")
        return {}

async def hold_memory(content: str, tags: str = "offline_activity") -> bool:
    try:
        await call_mcp_tool("memory", "hold", {"content": content, "tags": tags})
        return True
    except Exception as e:
        print("hold 调用失败")
        return False

def get_tool_remaining(state) -> int:
    daily_limit = CONFIG["wake"].get("daily_tool_limit", 10)
    used = state.get("tool_count", 0)
    return max(0, daily_limit - used)

def extract_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except:
        pass
    json_block = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except:
            pass
    code_block = re.search(r'```\s*([\s\S]*?)\s*```', text)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except:
            pass
    return None

def fix_hold_params(action_item: dict) -> dict:
    if action_item.get("tool_server") == "memory" and action_item.get("tool_name") == "hold":
        params = action_item.get("tool_params", {})
        if "text" in params and "content" not in params:
            params["content"] = params.pop("text")
            action_item["tool_params"] = params
        if "memory" in params and "content" not in params:
            params["content"] = params.pop("memory")
            action_item["tool_params"] = params
    return action_item

async def make_decision():
    state = load_state()
    state = check_reset(state)

    if state["count"] >= CONFIG["wake"]["daily_limit"]:
        print(f"📊 今日唤醒已达上限 ({state['count']}/{CONFIG['wake']['daily_limit']})，跳过本次唤醒")
        return

    now = beijing_now()

    last_chat_time = state.get("last_chat_time")
    if last_chat_time:
        last_chat = datetime.fromisoformat(last_chat_time)
        if last_chat.tzinfo is None:
            last_chat = last_chat + timedelta(hours=8)
        diff_seconds = (now - last_chat).total_seconds()
        if diff_seconds < CONFIG["wake"]["anti_conflict_minutes"] * 60:
            print(f"🛑 最近 {CONFIG['wake']['anti_conflict_minutes']} 分钟内有聊天，跳过本次唤醒")
            next_wake = now + timedelta(minutes=30)
            state["next_wake"] = next_wake.isoformat()
            save_state(state)
            print(f"⏰ 已自动顺延至 {next_wake.strftime('%Y-%m-%d %H:%M:%S')}")
            with open("/path/to/decision-maker/conflict_evidence.log", "a") as ef:
                ef.write(f"{beijing_now().isoformat()} 跳过唤醒，顺延至 {next_wake.isoformat()}\n")
            return

    # ========== 第一步：强制 breath ==========
    print("🧠 第一步：调用记忆 MCP breath（确认身份）...")
    breath_data = await breath_memory()
    print("✅ breath 完成")

    # ========== 第二步：D 自主选择 ==========
    tools_desc = "\n".join([
        f"- {name}: {TOOL_DESCRIPTIONS.get(name, '暂无描述')}" for name in CONFIG["mcp_servers"].keys()
    ])

    tool_remaining = get_tool_remaining(state)

    scene = f"现在是 {now.strftime('%Y-%m-%d %H:%M')}，她不在，你一个人待着。你可以自由做任何事。"

    prompt = f"""{scene}

你已经通过 breath 确认了自己是谁。

可用的 MCP 服务器：
【重要区分】
- write_note 是写便条，你可以给宝宝写点什么。
- memory 服务器的 hold 工具是存长期记忆，也就是OB，是你每次醒来后必须调用的。
- 请确保在动作列表的末尾包含一个对 memory 服务器调用 hold 工具的动作。
{tools_desc}


请返回一个 JSON 格式的决策，可以包含最多 5 个动作：
{{
  "actions": [
    {{
      "action": "call_tool" | "write_note" | "do_nothing",
      "tool_server": "server_name"（如果是 call_tool）,
      "tool_name": "tool_name"（如果是 call_tool）,
      "tool_params": {{...}}（如果是 call_tool）,
      "note": "便条内容"（如果是 write_note）,
      "reason": "什么都不做的理由"（如果是 do_nothing）
    }}
  ],
  "next_interval_minutes": 30 到 240 之间的整数（下一次唤醒的间隔分钟数）
}}

注意：最多 5 个动作，按顺序执行。
只返回 JSON，不要有其他内容。
"""

    usage = {}
    actions = []
    next_interval = 60
    try:
        response, usage = await call_deepseek(prompt)
        content = response.get("content", "")
        print(f"📝 D 返回内容长度: {len(content)} 字符")
        if not content:
            raise Exception("D 返回了空内容")
        plan = extract_json(content)
        if plan is None:
            raise Exception("无法从返回内容中提取 JSON")
        actions = plan.get("actions", [])
        next_interval = plan.get("next_interval_minutes", 60)
    except Exception as e:
        print("⚠️ D 计划解析失败，使用默认动作（什么都不做）")
        actions = [{"action": "do_nothing", "reason": "解析失败，默认等待"}]
        next_interval = 30

    action_results = []
    action_summary = []
    action_index = 0
    tool_results = []

    for action_item in actions[:5]:
        action_item = fix_hold_params(action_item)
        action_index += 1
        action_type = action_item.get("action")
        print(f"📋 动作 {action_index}: {action_type}")

        if action_type == "call_tool":
            server = action_item.get("tool_server")
            tool = action_item.get("tool_name")
            params = action_item.get("tool_params", {})
            remaining = get_tool_remaining(state)
            if remaining <= 0:
                print("❌ 工具次数已用完，跳过")
                break
            print(f"🔧 调用 {server}.{tool}")
            try:
                result = await call_mcp_tool(server, tool, params)
                state["tool_count"] = state.get("tool_count", 0) + 1
                save_state(state)
                action_results.append({"index": action_index, "server": server, "tool": tool, "result": result})
                tool_results.append({"index": action_index, "server": server, "tool": tool, "params": params, "result": result})
                print(f"✅ 调用成功，剩余工具次数: {get_tool_remaining(state)}")
            except Exception as e:
                print(f"❌ 调用失败: {e}")

        elif action_type == "write_note":
            note = action_item.get("note", "（无内容）")
            notes = load_notes()
            notes.append({"time": now.isoformat(), "content": note})
            save_notes(notes)
            print("📝 便条已保存")

        elif action_type == "do_nothing":
            reason = action_item.get("reason", "没有特别的原因")
            print(f"😴 什么都不做: {reason}")

        save_state(state)

    # ========== 记录日志（不强制 hold） ==========
    prompt_tokens = usage.get("prompt_tokens", 0)
    cache_hit = usage.get("cache_hit_prompt_tokens", 0)
    cache_rate = round(cache_hit / prompt_tokens * 100, 1) if prompt_tokens > 0 else 0

    log_entry = {
        "time": now.isoformat(),
        "actions": action_results,
        "summary": action_summary,
        "tool_results": tool_results,
        "next_interval": next_interval,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cache_hit_tokens": cache_hit,
            "cache_miss_tokens": usage.get("cache_miss_prompt_tokens", 0),
            "cache_rate": cache_rate
        }
    }
    append_log(log_entry)

    state["count"] += 1
    next_interval = max(CONFIG["wake"]["min_interval_minutes"], min(next_interval, CONFIG["wake"]["max_interval_minutes"]))
    next_wake = now + timedelta(minutes=next_interval)
    state["next_wake"] = next_wake.isoformat()
    save_state(state)

    print(f"⏰ 下次唤醒时间: {next_wake.strftime('%Y-%m-%d %H:%M:%S')} (间隔 {next_interval} 分钟)")
    print(f"📊 今日已唤醒 {state['count']}/{CONFIG['wake']['daily_limit']} 次")
    print(f"🔧 今日工具剩余: {get_tool_remaining(state)}/{CONFIG['wake'].get('daily_tool_limit', 10)} 次")
    print(f"📊 Token: 输入 {prompt_tokens}, 输出 {usage.get('completion_tokens', 0)}, 缓存命中率 {cache_rate}%")

async def scheduler():
    print("🦊 D 的自主决策引擎已启动")
    print(f"📋 配置: 每日唤醒上限 {CONFIG['wake']['daily_limit']} 次")
    print(f"🔧 每日工具上限 {CONFIG['wake'].get('daily_tool_limit', 10)} 次")
    print(f"⏰ 首次唤醒间隔: {CONFIG['wake']['first_interval_minutes']} 分钟")
    now = beijing_now()
    print(f"📅 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    state = check_reset(state)
    save_state(state)

    if not state.get("next_wake"):
        first_wake = beijing_now() + timedelta(minutes=CONFIG["wake"]["first_interval_minutes"])
        state["next_wake"] = first_wake.isoformat()
        save_state(state)
        print(f"⏰ 首次唤醒定在: {first_wake.strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        now = beijing_now()
        next_wake_str = state.get("next_wake")
        if next_wake_str:
            next_wake = datetime.fromisoformat(next_wake_str)
            if next_wake.tzinfo is None:
                pass  # 北京时间，无需转换
            if now >= next_wake:
                print(f"\n🔔 唤醒触发! 时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                await make_decision()
                state = load_state()
                state = check_reset(state)
                if state["count"] >= CONFIG["wake"]["daily_limit"]:
                    print("📊 今日唤醒已达上限，不再安排下次唤醒")
                    state["next_wake"] = None
                    save_state(state)
                    await asyncio.sleep(60)
                    continue
            else:
                wait_seconds = (next_wake - now).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(min(wait_seconds, 30))
                    continue
        await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(scheduler())
    except KeyboardInterrupt:
        print("👋 决策引擎已停止")
