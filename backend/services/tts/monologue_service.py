import sqlite3
import random
import re
import os
from .init_db import DB_PATH

class MonologueService:
    def __init__(self):
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError("请先运行 python init_db.py 初始化独白数据库！")
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    def get_monologue(self, category: str = None, emotion: str = None, keyword: str = None):
        """
        获取一条独白
        :param category: "daily" 或 "philosophy"
        :param emotion: "cute", "sad", "gentle" 等
        :param keyword: 模糊匹配触发词（如 "傍晚"）
        """
        query = "SELECT script, emotion FROM monologues WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if emotion:
            query += " AND emotion = ?"
            params.append(emotion)
        if keyword:
            query += " AND triggers LIKE ?"
            params.append(f"%{keyword}%")
            
        query += " ORDER BY RANDOM() LIMIT 1"
        
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        
        if not row:
            # 兜底：随机返回一条
            cursor.execute("SELECT script, emotion FROM monologues ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            
        return {"script": row[0], "emotion": row[1]} if row else None

    @staticmethod
    def parse_script_to_commands(script: str):
        """
        将剧本拆解为 动作指令 和 语音指令 队列
        返回: [{"type": "motion", "value": "叹气"}, {"type": "tts", "text": "嗯...", "emotion": "gentle"}]
        """
        commands = []
        # 正则：匹配 (动作) 或 纯文本(直到下一个括号或结尾)
        pattern = r'\((.*?)\)|([^\(]+?)(?=\(|$)'
        
        for match in re.finditer(pattern, script):
            action = match.group(1)
            text = match.group(2)
            
            if action and action.strip():
                # 清理动作词前面的修饰词（如 "轻轻"叹气 -> 叹气）
                clean_action = re.sub(r'(轻轻|微微|慢慢|缓缓|静静)', '', action).strip()
                commands.append({"type": "motion", "value": clean_action})
                
            if text and text.strip():
                clean_text = text.strip()
                # 简单的文本情绪推测（用于覆盖默认情绪）
                local_emotion = None
                if "..." in clean_text and "！" not in clean_text: local_emotion = "gentle"
                if "！" in clean_text or "!!" in clean_text: local_emotion = "happy"
                if "苦笑" in script or "空虚" in clean_text: local_emotion = "sad"
                
                commands.append({
                    "type": "tts", 
                    "text": clean_text,
                    "local_emotion": local_emotion # 局部情绪，可选使用
                })
        return commands

# 测试代码
if __name__ == "__main__":
    svc = MonologueService()
    
    # 测试1：随机获取一条日常独白
    res = svc.get_monologue(category="daily", emotion="cute")
    print("【获取结果】")
    print(f"情绪: {res['emotion']}")
    print(f"原文: {res['script']}\n")
    
    # 测试2：解析剧本
    print("【解析队列】")
    cmds = svc.parse_script_to_commands(res['script'])
    for cmd in cmds:
        print(cmd)
