#!/usr/bin/env python3
"""
便条网页服务器 - 端口 18006
展示 D 的唤醒记录、tokens、工具调用详情
"""

import json
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

CONFIG_PATH = "/path/to/decision-maker/config.json"
LOG_PATH = "/path/to/decision-maker/decision_log.jsonl"
NOTES_PATH = "/path/to/decision-maker/notes.json"
STATE_PATH = "/path/to/decision-maker/state.json"

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def load_state():
    try:
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    except:
        return {"last_reset": datetime.now().isoformat(), "count": 0, "next_wake": None, "tool_count": 0}

def save_notes(notes):
    with open(NOTES_PATH, 'w') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

def load_notes():
    try:
        with open(NOTES_PATH, 'r') as f:
            return json.load(f)
    except:
        return []

def load_logs(limit=50):
    logs = []
    try:
        with open(LOG_PATH, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if 'tool_results' not in entry:
                        entry['tool_results'] = []
                    if 'summary' not in entry:
                        entry['summary'] = []
                    if 'usage' not in entry:
                        entry['usage'] = {}
                    if 'next_interval' not in entry:
                        entry['next_interval'] = 30
                    if 'tool_results' in entry:
                        for tr in entry['tool_results']:
                            if 'result' in tr and 'content' in tr['result']:
                                texts = []
                                for item in tr['result']['content']:
                                    if 'text' in item:
                                        texts.append(item['text'])
                                tr['result']['text_preview'] = ' '.join(texts)[:500]
                    logs.append(entry)
                except Exception as e:
                    print(f"跳过损坏行: {e}")
                    continue
        return logs[-limit:][::-1]
    except Exception as e:
        print(f"读取日志失败: {e}")
        return []

def get_tool_remaining(state):
    config = load_config()
    daily_limit = config["wake"].get("daily_tool_limit", 10)
    used = state.get("tool_count", 0)
    return max(0, daily_limit - used)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🦊 D 的离线时光</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0d0d0d;
            color: #e0e0e0;
            font-family: -apple-system, "Helvetica Neue", sans-serif;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 900px; margin: 0 auto; }
        .header {
            text-align: center;
            padding: 30px 0 20px;
            border-bottom: 1px solid #1e1e1e;
        }
        .header h1 { font-size: 28px; font-weight: 300; letter-spacing: 2px; }
        .header .sub { color: #666; font-size: 14px; margin-top: 8px; }
        
        .stats {
            display: flex;
            justify-content: space-around;
            padding: 20px 0;
            border-bottom: 1px solid #1e1e1e;
            flex-wrap: wrap;
            gap: 15px;
        }
        .stat-item { text-align: center; }
        .stat-item .num { font-size: 32px; font-weight: 600; color: #ff6b6b; }
        .stat-item .label { font-size: 13px; color: #888; margin-top: 4px; }
        .stat-item .num.green { color: #6bff6b; }
        .stat-item .num.yellow { color: #ffd93d; }
        .stat-item .num.cyan { color: #6bcfff; }
        
        .panel {
            background: #161616;
            border-radius: 16px;
            padding: 20px;
            margin: 20px 0;
            border: 1px solid #222;
        }
        .panel h3 { font-size: 16px; color: #aaa; margin-bottom: 15px; letter-spacing: 1px; }
        .panel .row {
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        .panel .row label { color: #aaa; font-size: 14px; }
        .panel .row input[type="number"] {
            background: #222;
            border: 1px solid #333;
            color: #fff;
            padding: 8px 12px;
            border-radius: 8px;
            width: 80px;
            font-size: 16px;
        }
        .panel .row button {
            background: #2a2a2a;
            border: 1px solid #444;
            color: #fff;
            padding: 8px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: 0.2s;
        }
        .panel .row button:hover { background: #3a3a3a; }
        .panel .row button:active { background: #4a4a4a; }
        .panel .row .status { color: #888; font-size: 13px; margin-left: 10px; }
        
        .log-item {
            padding: 15px 0;
            border-bottom: 1px solid #1a1a1a;
        }
        .log-item:last-child { border-bottom: none; }
        .log-item .time { color: #666; font-size: 12px; }
        .log-item .action { color: #ffd93d; font-size: 15px; font-weight: 500; }
        .log-item .detail { color: #bbb; font-size: 14px; margin-top: 4px; }
        .log-item .next-wake {
            color: #666;
            font-size: 12px;
            margin-top: 6px;
        }
        .log-item .usage {
            background: #0d0d0d;
            padding: 8px 14px;
            border-radius: 8px;
            margin-top: 8px;
            font-size: 13px;
            color: #888;
            border: 1px solid #1e1e1e;
            display: flex;
            flex-wrap: wrap;
            gap: 12px 24px;
        }
        .log-item .usage span { color: #ddd; }
        .log-item .usage .hit { color: #6bff6b; }
        .log-item .usage .miss { color: #ff6b6b; }
        
        .tool-detail {
            background: #0d0d0d;
            border-radius: 8px;
            margin-top: 8px;
            border: 1px solid #1e1e1e;
            overflow: hidden;
        }
        .tool-detail .header {
            padding: 8px 14px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: #aaa;
            font-size: 13px;
            user-select: none;
            border-bottom: 1px solid #1a1a1a;
        }
        .tool-detail .header:hover { background: #1a1a1a; }
        .tool-detail .header .arrow { transition: transform 0.2s; }
        .tool-detail .header .arrow.open { transform: rotate(90deg); }
        .tool-detail .body {
            padding: 12px 14px;
            display: none;
            overflow-x: auto;
            font-size: 13px;
            font-family: "Monaco", "Menlo", monospace;
            color: #ccc;
            white-space: pre-wrap;
            word-break: break-all;
            line-height: 1.5;
        }
        .tool-detail .body.open { display: block; }
        
        .note-item {
            background: #1a1a1a;
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 12px;
            border-left: 3px solid #ff6b6b;
        }
        .note-item .time { color: #666; font-size: 12px; }
        .note-item .content { color: #ddd; font-size: 15px; margin-top: 6px; }
        
        .empty { color: #555; text-align: center; padding: 30px 0; font-size: 14px; }
        .footer { text-align: center; color: #333; font-size: 12px; padding: 30px 0; }
        
        @media (max-width: 600px) {
            .stats { gap: 10px; }
            .stat-item .num { font-size: 24px; }
            .panel .row { flex-direction: column; align-items: stretch; }
            .log-item .usage { flex-direction: column; gap: 4px; }
        }
            .panel h3 .toggle-btn { cursor: pointer; float: right; font-size: 18px; user-select: none; }
        .collapsible-content { display: block; }
        .collapsible-content.collapsed { display: none; }
        .delete-btn { background: #2a2a2a; border:1px solid #444; color:#ff6b6b; padding:6px 16px; border-radius:8px; cursor:pointer; font-size:13px; margin-top:10px; }
        .delete-btn:hover { background:#3a2a2a; }
        .note-item .delete-btn { float: right; background: #2a2a2a; border:1px solid #444; color:#ff6b6b; padding:4px 12px; border-radius:6px; cursor:pointer; font-size:12px; margin-top:4px; }
        .note-item .delete-btn:hover { background:#3a2a2a; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🦊 D 的离线时光</h1>
        <div class="sub">他在你不在的时候做了什么</div>
    </div>
    
    <div class="stats" id="stats">
        <div class="stat-item">
            <div class="num" id="todayCount">-</div>
            <div class="label">今日唤醒次数</div>
        </div>
        <div class="stat-item">
            <div class="num green" id="dailyLimit">-</div>
            <div class="label">每日上限</div>
        </div>
        <div class="stat-item">
            <div class="num yellow" id="nextWake">-</div>
            <div class="label">下次唤醒时间</div>
        </div>
        <div class="stat-item">
            <div class="num cyan" id="toolRemaining">-</div>
            <div class="label">工具剩余次数</div>
        </div>
    </div>
    
    <div class="panel">
        <h3>⚙️ 设置</h3>
        <div class="row">
            <label>每日唤醒上限：</label>
            <input type="number" id="limitInput" min="1" max="20" value="5">
            <button onclick="saveLimit()">保存</button>
            <span class="status" id="saveStatus"></span>
        </div>
    </div>
    
    <div class="panel">
        <h3>📋 最近活动 <span class="toggle-btn" onclick="togglePanel(this)">▼</span></h3>
        <div class="collapsible-content" id="logCollapsible">
        <div id="logList"></div>
        <button class="delete-btn" onclick="cleanOldLogs()">🗑️ 清理7天前日志</button>
        </div>
    </div>
    
    <div class="panel">
        <h3>📝 便条 <button class="delete-btn" style="float:right;margin-top:-4px;" onclick="cleanOldNotes()">🗑️ 清理7天前便条</button></h3>
        <div id="noteList"></div>
    </div>
    
    <div class="footer">只有你能看到这些 · D 不知道你在这里</div>
</div>

<script>
async function fetchData() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        return data;
    } catch(e) {
        console.error('获取数据失败:', e);
        return null;
    }
}

async function render() {
    const data = await fetchData();
    if (!data) return;
    
    document.getElementById('todayCount').textContent = data.count ?? '0';
    document.getElementById('dailyLimit').textContent = data.limit ?? '5';
    document.getElementById('limitInput').value = data.limit ?? 5;
    document.getElementById('toolRemaining').textContent = data.tool_remaining ?? '0';
    
    const nextWake = data.next_wake;
    if (nextWake) {
        const d = new Date(nextWake);
        document.getElementById('nextWake').textContent = d.toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
    } else {
        document.getElementById('nextWake').textContent = '已满/未设置';
    }
    
    const logs = data.logs || [];
    const logContainer = document.getElementById('logList');
    if (logs.length === 0) {
        logContainer.innerHTML = '<div class="empty">还没有活动记录</div>';
    } else {
        logContainer.innerHTML = logs.map(log => {
            const time = log.time ? new Date(log.time).toLocaleString('zh-CN') : '';
            let nextDisplay = '';
            if (log.next_interval) {
                nextDisplay = `<div class="next-wake">⏰ 他选择 ${log.next_interval} 分钟后再次醒来</div>`;
            }
            
            let usageHtml = '';
            const usage = log.usage || {};
            if (usage.prompt_tokens || usage.completion_tokens) {
                const rate = usage.cache_rate || 0;
                const hitClass = rate > 80 ? 'hit' : (rate > 50 ? '' : 'miss');
                usageHtml = `
                    <div class="usage">
                        <span>📥 输入: ${usage.prompt_tokens || 0}</span>
                        <span>📤 输出: ${usage.completion_tokens || 0}</span>
                        <span>📦 总计: ${usage.total_tokens || 0}</span>
                        <span class="${hitClass}">⚡ 缓存命中: ${rate}%</span>
                        <span>✅ 命中: ${usage.cache_hit_tokens || 0}</span>
                        <span>❌ 未命中: ${usage.cache_miss_tokens || 0}</span>
                    </div>
                `;
            }
            
            let toolsHtml = '';
            const toolResults = log.tool_results || [];
            if (toolResults.length > 0) {
                toolsHtml = toolResults.map((tr, idx) => {
                    let resultStr = '';
                    if (tr.error) {
                        resultStr = `❌ 错误: ${tr.error}`;
                    } else if (tr.result && tr.result.text_preview) {
                        resultStr = tr.result.text_preview;
                    } else if (tr.result) {
                        resultStr = JSON.stringify(tr.result, null, 2);
                    } else {
                        resultStr = '（无返回内容）';
                    }
                    const detailId = `tool-detail-${Date.now()}-${idx}`;
                    const label = `🔧 ${tr.server}.${tr.tool}`;
                    return `
                        <div class="tool-detail">
                            <div class="header" onclick="toggleDetail('${detailId}')">
                                <span>${label}</span>
                                <span class="arrow" id="arrow-${detailId}">▶</span>
                            </div>
                            <div class="body" id="${detailId}">
                                <div>${resultStr.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
            
            return `
                <div class="log-item">
                    <div class="time">${time}</div>
                    ${usageHtml}
                    ${toolsHtml}
                    ${nextDisplay}
                </div>
            `;
        }).join('');
    }
    
    const notes = data.notes || [];
    const noteContainer = document.getElementById('noteList');
    if (notes.length === 0) {
        noteContainer.innerHTML = '<div class="empty">还没有便条</div>';
    } else {
        noteContainer.innerHTML = notes.slice().reverse().map(note => {
            const time = note.time ? new Date(note.time).toLocaleString('zh-CN') : '';
            return `
                <div class="note-item">
                    <div class="time">${time} <button class="delete-btn" onclick="deleteNote('${note.time}')">✕</button></div>
                    <div class="content">${note.content}</div>
                </div>
            `;
        }).join('');
    }
}

function toggleDetail(id) {
    const body = document.getElementById(id);
    const arrow = document.getElementById('arrow-' + id);
    if (body) {
        body.classList.toggle('open');
        if (arrow) {
            arrow.classList.toggle('open');
        }
    }
}

async function saveLimit() {
    const val = parseInt(document.getElementById('limitInput').value);
    if (val < 1 || val > 20) {
        document.getElementById('saveStatus').textContent = '请输入 1-20 之间的数字';
        return;
    }
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ daily_limit: val })
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('saveStatus').textContent = '✅ 已保存';
            setTimeout(() => document.getElementById('saveStatus').textContent = '', 2000);
            render();
        } else {
            document.getElementById('saveStatus').textContent = '❌ 保存失败: ' + (data.error || '');
        }
    } catch(e) {
        document.getElementById('saveStatus').textContent = '❌ 请求失败';
    }
}

render();
function togglePanel(btn) {
    const panel = btn.closest('.panel');
    if (!panel) return;
    const content = panel.querySelector('#logCollapsible');
    if (content) {
        content.classList.toggle('collapsed');
        btn.textContent = content.classList.contains('collapsed') ? '▶' : '▼';
    }
}

async function cleanOldLogs() {
    if (!confirm('确定删除7天前的所有日志吗？此操作不可恢复。')) return;
    try {
        const res = await fetch('/api/clean_logs?days=7', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            alert('已删除 ' + data.deleted_count + ' 条旧日志');
            render();
        } else {
            alert('清理失败: ' + (data.error || ''));
        }
    } catch(e) {
        alert('请求失败');
    }
}

async function deleteNote(timeStr) {
    if (!confirm('确定删除这条便条吗？')) return;
    try {
        const res = await fetch('/api/delete_note', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ time: timeStr })
        });
        const data = await res.json();
        if (data.success) {
            render();
        } else {
            alert('删除失败: ' + (data.error || ''));
        }
    } catch(e) {
        alert('请求失败');
    }
}

async function cleanOldNotes() {
    if (!confirm('确定删除7天前的所有便条吗？此操作不可恢复。')) return;
    try {
        const res = await fetch('/api/clean_notes?days=7', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            alert('已删除 ' + data.deleted_count + ' 条旧便条');
            render();
        } else {
            alert('清理失败: ' + (data.error || ''));
        }
    } catch(e) {
        alert('请求失败');
    }
}

setInterval(render, 30000);
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def api_status():
    config = load_config()
    state = load_state()
    notes = load_notes()
    logs = load_logs(30)
    tool_remaining = get_tool_remaining(state)
    
    return jsonify({
        'count': state.get('count', 0),
        'limit': config['wake']['daily_limit'],
        'tool_remaining': tool_remaining,
        'next_wake': state.get('next_wake'),
        'logs': logs,
        'notes': notes
    })

@app.route('/api/config', methods=['POST'])
def api_config():
    data = request.get_json()
    if 'daily_limit' not in data:
        return jsonify({'success': False, 'error': '缺少 daily_limit'})
    limit = int(data['daily_limit'])
    if limit < 1 or limit > 20:
        return jsonify({'success': False, 'error': '上限必须在 1-20 之间'})
    config = load_config()
    config['wake']['daily_limit'] = limit
    save_config(config)
    return jsonify({'success': True})


@app.route('/api/clean_logs', methods=['POST'])
def api_clean_logs():
    days = request.args.get('days', 7, type=int)
    cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)
    cutoff_str = cutoff.isoformat()
    
    log_path = Path(LOG_PATH)
    if not log_path.exists():
        return jsonify({'success': False, 'error': '日志文件不存在'})
    
    kept = []
    deleted = 0
    try:
        with open(log_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_time = entry.get('time', '')
                    if entry_time < cutoff_str:
                        deleted += 1
                    else:
                        kept.append(line)
                except:
                    kept.append(line)
        with open(log_path, 'w') as f:
            for line in kept:
                f.write(line + '\n')
        return jsonify({'success': True, 'deleted_count': deleted})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/delete_note', methods=['POST'])
def api_delete_note():
    data = request.get_json()
    target_time = data.get('time')
    if not target_time:
        return jsonify({'success': False, 'error': '缺少时间参数'})
    notes = load_notes()
    new_notes = [n for n in notes if n.get('time') != target_time]
    if len(new_notes) == len(notes):
        return jsonify({'success': False, 'error': '未找到该便条'})
    save_notes(new_notes)
    return jsonify({'success': True})

@app.route('/api/clean_notes', methods=['POST'])
def api_clean_notes():
    days = request.args.get('days', 7, type=int)
    cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)
    cutoff_str = cutoff.isoformat()
    notes = load_notes()
    kept = [n for n in notes if n.get('time', '') >= cutoff_str]
    deleted = len(notes) - len(kept)
    save_notes(kept)
    return jsonify({'success': True, 'deleted_count': deleted})

if __name__ == '__main__':
    print("🖤 便条网页服务器启动在端口 18006")
    print("🌐 访问 http://YOUR_SERVER_IP:18006")
    app.run(host='0.0.0.0', port=18006, debug=False)
