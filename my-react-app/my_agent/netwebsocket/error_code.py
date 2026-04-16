"""
JSON-RPC 2.0 错误码定义
遵循架构方案 4.4 节规范
"""


class ErrorCode:
    """JSON-RPC 2.0 标准及自定义错误码"""

    # JSON-RPC 2.0 标准错误码
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # 自定义错误码 (1000-1999: 动画模块)
    ANIMATION_PARAM_OUT_OF_RANGE = 1001
    ANIMATION_DRIVER_NOT_FOUND = 1002
    ANIMATION_CHANNEL_CLOSED = 1003

    # 自定义错误码 (2000-2999: 音频模块)
    AUDIO_TTS_INIT_FAILED = 2001
    AUDIO_TTS_SYNTHESIS_FAILED = 2002
    AUDIO_CHANNEL_CLOSED = 2003
    AUDIO_INVALID_FORMAT = 2004

    # 自定义错误码 (3000-3999: AI模块)
    AI_MODEL_UNAVAILABLE = 3001
    AI_REQUEST_TIMEOUT = 3002
    AI_INVALID_RESPONSE = 3003
    AI_RATE_LIMITED = 3004

    # 自定义错误码 (4000-4999: 控制模块)
    CONTROL_INVALID_COMMAND = 4001
    CONTROL_DRIVER_NOT_INITIALIZED = 4002
    CONTROL_WEBSOCKET_CLOSED = 4003

    # 自定义错误码 (5000-5999: 系统模块)
    SYSTEM_CONFIG_ERROR = 5001
    SYSTEM_RESOURCE_EXHAUSTED = 5002
    SYSTEM_MAINTENANCE = 5003

    @staticmethod
    def get_error_message(code: int) -> str:
        """获取错误码对应的描述消息"""
        error_messages = {
            # JSON-RPC 标准错误
            ErrorCode.PARSE_ERROR: "JSON 解析错误",
            ErrorCode.INVALID_REQUEST: "无效的请求",
            ErrorCode.METHOD_NOT_FOUND: "方法未找到",
            ErrorCode.INVALID_PARAMS: "无效的参数",
            ErrorCode.INTERNAL_ERROR: "内部错误",

            # 动画模块错误
            ErrorCode.ANIMATION_PARAM_OUT_OF_RANGE: "动画参数超出范围",
            ErrorCode.ANIMATION_DRIVER_NOT_FOUND: "动画驱动器未找到",
            ErrorCode.ANIMATION_CHANNEL_CLOSED: "动画通道已关闭",

            # 音频模块错误
            ErrorCode.AUDIO_TTS_INIT_FAILED: "TTS 初始化失败",
            ErrorCode.AUDIO_TTS_SYNTHESIS_FAILED: "TTS 合成失败",
            ErrorCode.AUDIO_CHANNEL_CLOSED: "音频通道已关闭",
            ErrorCode.AUDIO_INVALID_FORMAT: "音频格式无效",

            # AI模块错误
            ErrorCode.AI_MODEL_UNAVAILABLE: "AI 模型不可用",
            ErrorCode.AI_REQUEST_TIMEOUT: "AI 请求超时",
            ErrorCode.AI_INVALID_RESPONSE: "AI 响应无效",
            ErrorCode.AI_RATE_LIMITED: "AI 请求频率限制",

            # 控制模块错误
            ErrorCode.CONTROL_INVALID_COMMAND: "控制指令无效",
            ErrorCode.CONTROL_DRIVER_NOT_INITIALIZED: "控制驱动器未初始化",
            ErrorCode.CONTROL_WEBSOCKET_CLOSED: "WebSocket 连接已关闭",

            # 系统模块错误
            ErrorCode.SYSTEM_CONFIG_ERROR: "系统配置错误",
            ErrorCode.SYSTEM_RESOURCE_EXHAUSTED: "系统资源耗尽",
            ErrorCode.SYSTEM_MAINTENANCE: "系统维护中",
        }

        return error_messages.get(code, f"未知错误 (代码: {code})")