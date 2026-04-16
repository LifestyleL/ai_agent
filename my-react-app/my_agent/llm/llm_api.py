import requests
import json
from typing import List, Dict, Any, Optional

class LLMAPI:
    """优化版 LLM API 调用封装类，兼容 OpenAI 格式"""
    
    def __init__(self, api_key: str, base_url: str, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")  # 自动处理多余斜杠
        self.model = model
        
    def chat(self, 
             messages: List[Dict[str, str]], 
             temperature: float = 0.7,
             functions: Optional[List[Dict]] = None
             ) -> Dict[str, Any]:
        """
        发送聊天请求
        messages格式: [{"role": "user", "content": "你好"}]
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        
        if functions:
            payload["functions"] = functions
            
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print("❌ API 请求超时")
            return {"error": "请求超时"}
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP 错误: {e}")
            return {"error": f"HTTP错误: {e}"}
        except Exception as e:
            print(f"❌ API调用失败: {e}")
            return {"error": str(e)}

    # 新增：直接传入字符串，自动包装成 message，超级方便
    def ask(self, prompt: str, temperature: float = 0.7) -> str:
        """简易调用：直接传字符串，返回回答文本"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, temperature=temperature)
        
        if "error" in result:
            return f"出错了：{result['error']}"
        
        try:
            return result["choices"][0]["message"]["content"].strip()
        except:
            return "解析回复失败"
    
    def ask_with_system(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """
        高级调用：分离系统指令和用户输入（适合记忆总结、工具决策、格式化输出）
        - system_prompt: 强制 AI 扮演的角色和死规矩
        - user_prompt: 具体要处理的数据或任务
        - temperature: 默认 0.3（比 ask 更冷静严谨，不容易胡说八道）
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        result = self.chat(messages, temperature=temperature)
        
        if "error" in result:
            return f"出错了：{result['error']}"
        
        try:
            return result["choices"][0]["message"]["content"].strip()
        except:
            return "解析回复失败"