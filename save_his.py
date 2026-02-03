import sqlite3
import json
import os
import time
from datetime import datetime

def convert_safedraft_to_notegen(db_path, output_path):
    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        print(f"错误: 找不到数据库文件 '{db_path}'")
        return

    print(f"正在读取 SafeDraft 数据库: {db_path} ...")

    try:
        # 连接 SQLite 数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询 drafts 表 (SafeDraft 的历史归档)
        # 字段: id, content, created_at, last_updated_at
        cursor.execute("SELECT id, content, created_at FROM drafts ORDER BY created_at DESC")
        rows = cursor.fetchall()

        marks_list = []

        for row in rows:
            draft_id, content, created_at_iso = row

            # 1. 时间戳转换 (ISO String -> Milliseconds Timestamp)
            try:
                dt_obj = datetime.fromisoformat(created_at_iso)
                # 转换为毫秒时间戳
                timestamp_ms = int(dt_obj.timestamp() * 1000)
            except ValueError:
                # 如果时间格式解析失败，使用当前时间
                timestamp_ms = int(time.time() * 1000)

            # 2. 构建 note-gen 的数据结构
            # 参考 marks.json 的结构
            note_item = {
                "id": draft_id,                 # 保持原有 ID，或者可以重新生成
                "tagId": 1,                     # 默认分类 ID
                "type": "text",                 # 类型
                "content": content,             # 原始内容
                "url": None,                    # URL 为空
                "desc": content,                # 描述 (参考示例，desc 与 content 一致)
                "deleted": 0,                   # 状态为未删除
                "createdAt": timestamp_ms       # 转换后的时间戳
            }

            marks_list.append(note_item)

        # 关闭数据库连接
        conn.close()

        # 3. 写入 JSON 文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(marks_list, f, ensure_ascii=False, indent=2)

        print(f"✅ 导出成功！")
        print(f"共导出 {len(marks_list)} 条记录。")
        print(f"文件已保存为: {os.path.abspath(output_path)}")

    except Exception as e:
        print(f"❌ 导出过程中发生错误: {e}")

if __name__ == "__main__":
    # 配置文件路径
    DB_FILE = "safedraft.db"           # 源文件：SafeDraft 数据库
    OUTPUT_FILE = "exported_marks.json" # 目标文件：导出的 JSON

    convert_safedraft_to_notegen(DB_FILE, OUTPUT_FILE)