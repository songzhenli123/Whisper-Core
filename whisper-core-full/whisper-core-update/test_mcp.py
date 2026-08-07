#!/usr/bin/env python3
"""
MCP 连通性测试脚本 v2
根据 URL 是否包含 /sse 自动选择客户端类型
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

CONFIG_PATH = "/path/to/decision-maker/config.json"

with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)

# 每个 MCP 的测试工具（根据你提供的工具列表）
TEST_TOOLS = {
    "game": "list_games",
    "health": "get_latest_health",
    "weather": "get_current_weather_by_ip_address",
    "memory": "breath",
    "forum": "lutopia_get_guide",   # 或 cli，先试这个
    "travel": "look_around",
}

# 需要参数的工具
TEST_PARAMS = {
    "weather": {},  # get_current_weather_by_ip_address 可能不需要参数
    "forum": {"guide": "help"},   # 假设 lutopia_get_guide 需要参数
}

async def test_mcp(server_name: str, server_url: str):
    print(f"\n{'='*50}")
    print(f"🔍 测试 {server_name}: {server_url}")
    print('='*50)
    
    tool_name = TEST_TOOLS.get(server_name)
    if not tool_name:
        print(f"⚠️ 没有为 {server_name} 配置测试工具，跳过")
        return
    
    params = TEST_PARAMS.get(server_name, {})
    
    # 判断客户端类型：URL 包含 /sse 则用 SSE，否则用 Streamable HTTP
    is_sse = "/sse" in server_url
    
    try:
        if is_sse:
            print("使用 SSE 客户端")
            async with sse_client(server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    print(f"✅ 连接成功 (SSE)")
                    result = await session.call_tool(tool_name, arguments=params)
                    print(f"✅ 工具调用成功: {tool_name}")
                    if hasattr(result, 'content'):
                        for item in result.content:
                            if hasattr(item, 'text'):
                                preview = item.text[:100] + "..." if len(item.text) > 100 else item.text
                                print(f"   📄 返回: {preview}")
                    else:
                        print(f"   📄 返回: {str(result)[:100]}")
        else:
            print("使用 Streamable HTTP 客户端")
            async with streamable_http_client(server_url) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    print(f"✅ 连接成功 (Streamable HTTP)")
                    result = await session.call_tool(tool_name, arguments=params)
                    print(f"✅ 工具调用成功: {tool_name}")
                    if hasattr(result, 'content'):
                        for item in result.content:
                            if hasattr(item, 'text'):
                                preview = item.text[:100] + "..." if len(item.text) > 100 else item.text
                                print(f"   📄 返回: {preview}")
                    else:
                        print(f"   📄 返回: {str(result)[:100]}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

async def main():
    print("🦊 开始测试所有 MCP 服务 (v2)")
    print(f"📋 共 {len(CONFIG['mcp_servers'])} 个服务待测试\n")
    
    for server_name, server_url in CONFIG['mcp_servers'].items():
        await test_mcp(server_name, server_url)
    
    print("\n" + "="*50)
    print("🏁 所有测试完成")

if __name__ == "__main__":
    asyncio.run(main())
