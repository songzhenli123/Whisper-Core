#!/usr/bin/env python3
"""
归档清理脚本：保留最近7天的记录，删除更早的数据
每天凌晨2点执行一次
"""

import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

LOG_PATH = "/path/to/decision-maker/decision_log.jsonl"
NOTES_PATH = "/path/to/decision-maker/notes.json"
BACKUP_DIR = "/path/to/decision-maker/backups"
DAYS_TO_KEEP = 7

def ensure_backup_dir():
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

def backup_file(filepath):
    """备份原始文件"""
    if os.path.exists(filepath):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(filepath) + f".{timestamp}.bak")
        shutil.copy2(filepath, backup_path)
        return backup_path
    return None

def clean_log():
    """清理日志文件，保留最近7天的记录"""
    if not os.path.exists(LOG_PATH):
        return
    
    backup_path = backup_file(LOG_PATH)
    cutoff = datetime.now() - timedelta(days=DAYS_TO_KEEP)
    
    kept_lines = []
    kept_count = 0
    removed_count = 0
    
    try:
        with open(LOG_PATH, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entry_time = datetime.fromisoformat(entry.get('time', '').replace('Z', '+00:00'))
                    # 转换为不含时区的比较
                    if entry_time.replace(tzinfo=None) >= cutoff:
                        kept_lines.append(line)
                        kept_count += 1
                    else:
                        removed_count += 1
                except:
                    # 如果解析失败，保留该行（安全起见）
                    kept_lines.append(line)
                    kept_count += 1
        
        with open(LOG_PATH, 'w') as f:
            f.writelines(kept_lines)
        
        print(f"📋 日志清理完成：保留 {kept_count} 条，删除 {removed_count} 条")
        print(f"📁 备份文件: {backup_path if backup_path else '无'}")
    except Exception as e:
        print(f"❌ 清理日志失败: {e}")

def clean_notes():
    """清理便条，保留最近7天的记录"""
    if not os.path.exists(NOTES_PATH):
        return
    
    backup_path = backup_file(NOTES_PATH)
    cutoff = datetime.now() - timedelta(days=DAYS_TO_KEEP)
    
    try:
        with open(NOTES_PATH, 'r') as f:
            notes = json.load(f)
        
        kept = []
        removed = 0
        for note in notes:
            try:
                note_time = datetime.fromisoformat(note.get('time', '').replace('Z', '+00:00'))
                if note_time.replace(tzinfo=None) >= cutoff:
                    kept.append(note)
                else:
                    removed += 1
            except:
                # 如果解析失败，保留该条（安全起见）
                kept.append(note)
        
        with open(NOTES_PATH, 'w') as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
        
        print(f"📝 便条清理完成：保留 {len(kept)} 条，删除 {removed} 条")
        print(f"📁 备份文件: {backup_path if backup_path else '无'}")
    except Exception as e:
        print(f"❌ 清理便条失败: {e}")

def main():
    print(f"🕐 开始清理 {DAYS_TO_KEEP} 天前的记录...")
    ensure_backup_dir()
    clean_log()
    clean_notes()
    print("✅ 清理完成")

if __name__ == "__main__":
    main()
