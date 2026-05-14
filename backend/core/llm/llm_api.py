import httpx
import json
from typing import List, Dict, Any, Optional, Union

# content 字段可以是纯文本字符串，也可以是多模态数组（OpenAI 格式）
MessageContent = Union[str, List[Dict[str, Any]]]

class LLMAPI:
    """LLM API 调用封装类，兼容 OpenAI 格式（含多模态）。同时支持同步和异步调用。"""

    def __init__(self, api_key: str, base_url: str, model: str = "gpt-3.5-turbo", timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ─── 同步方法（httpx.Client，向后兼容） ───

    def chat(self,
             messages: List[Dict[str, Any]],
             temperature: float = 0.7,
             functions: Optional[List[Dict]] = None,
             tools: Optional[List[Dict]] = None,
             tool_choice: str = "auto",
             ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        if tools:
            payload["tools"] = tools
            if tool_choice and tool_choice != "auto":
                payload["tool_choice"] = tool_choice
        elif functions:
            payload["functions"] = functions

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            print("[ERROR] API 请求超时")
            return {"error": "请求超时"}
        except httpx.HTTPStatusError as e:
            print(f"[ERROR] HTTP 错误: {e}")
            return {"error": f"HTTP错误: {e}"}
        except Exception as e:
            print(f"[ERROR] API调用失败: {e}")
            return {"error": str(e)}

    def ask(self, prompt: str, temperature: float = 0.7) -> str:
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, temperature=temperature)
        if "error" in result:
            return f"出错了：{result['error']}"
        try:
            return result["choices"][0]["message"]["content"].strip()
        except:
            return "解析回复失败"

    def ask_with_system(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
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

    def chat_stream(self,
                    messages: List[Dict[str, Any]],
                    temperature: float = 0.7,
                    functions: Optional[List[Dict]] = None,
                    tools: Optional[List[Dict]] = None,
                    tool_choice: str = "auto",
                    ):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        if tools:
            payload["tools"] = tools
            if tool_choice and tool_choice != "auto":
                payload["tool_choice"] = tool_choice
        elif functions:
            payload["functions"] = functions

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line:
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if 'choices' in chunk and len(chunk['choices']) > 0:
                                        delta = chunk['choices'][0].get('delta', {})
                                        if 'content' in delta and delta['content']:
                                            yield delta['content']
                                        if 'tool_calls' in delta:
                                            yield {"tool_calls": delta['tool_calls']}
                                except json.JSONDecodeError:
                                    continue
        except httpx.TimeoutException:
            print("[ERROR] 流式 API 请求超时")
            yield "[ERROR] 请求超时"
        except httpx.HTTPStatusError as e:
            print(f"[ERROR] 流式 HTTP 错误: {e}")
            yield "[ERROR] HTTP错误: {e}"
        except Exception as e:
            print(f"[ERROR] 流式 API 调用失败: {e}")
            yield "[ERROR] {str(e)}"

    def ask_stream(self, prompt: str, temperature: float = 0.7):
        messages = [{"role": "user", "content": prompt}]
        return self.chat_stream(messages, temperature=temperature)

    # ─── 异步方法（httpx.AsyncClient） ───

    async def chat_async(self,
                         messages: List[Dict[str, Any]],
                         temperature: float = 0.7,
                         functions: Optional[List[Dict]] = None,
                         tools: Optional[List[Dict]] = None,
                         tool_choice: str = "auto",
                         ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        if tools:
            payload["tools"] = tools
            if tool_choice and tool_choice != "auto":
                payload["tool_choice"] = tool_choice
        elif functions:
            payload["functions"] = functions

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            print("[ERROR] API 请求超时")
            return {"error": "请求超时"}
        except httpx.HTTPStatusError as e:
            print(f"[ERROR] HTTP 错误: {e}")
            return {"error": f"HTTP错误: {e}"}
        except Exception as e:
            print(f"[ERROR] API调用失败: {e}")
            return {"error": str(e)}

    async def ask_async(self, prompt: str, temperature: float = 0.7) -> str:
        messages = [{"role": "user", "content": prompt}]
        result = await self.chat_async(messages, temperature=temperature)
        if "error" in result:
            return f"出错了：{result['error']}"
        try:
            return result["choices"][0]["message"]["content"].strip()
        except:
            return "解析回复失败"

    async def ask_with_system_async(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        result = await self.chat_async(messages, temperature=temperature)
        if "error" in result:
            return f"出错了：{result['error']}"
        try:
            return result["choices"][0]["message"]["content"].strip()
        except:
            return "解析回复失败"

    async def chat_stream_async(self,
                                 messages: List[Dict[str, Any]],
                                 temperature: float = 0.7,
                                 functions: Optional[List[Dict]] = None,
                                 tools: Optional[List[Dict]] = None,
                                 tool_choice: str = "auto",
                                 ):
        """异步流式聊天，逐 token yield"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        if tools:
            payload["tools"] = tools
            if tool_choice and tool_choice != "auto":
                payload["tool_choice"] = tool_choice
        elif functions:
            payload["functions"] = functions

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            if line.startswith('data: '):
                                data = line[6:]
                                if data == '[DONE]':
                                    return
                                try:
                                    chunk = json.loads(data)
                                    if 'choices' in chunk and len(chunk['choices']) > 0:
                                        delta = chunk['choices'][0].get('delta', {})
                                        if 'content' in delta and delta['content']:
                                            yield delta['content']
                                        if 'tool_calls' in delta:
                                            yield {"tool_calls": delta['tool_calls']}
                                except json.JSONDecodeError:
                                    continue
        except httpx.TimeoutException:
            yield "[ERROR] 请求超时"
        except httpx.HTTPStatusError as e:
            yield f"[ERROR] HTTP错误: {e}"
        except Exception as e:
            yield f"[ERROR] {str(e)}"
