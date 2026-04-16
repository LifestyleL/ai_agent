# live2d_manager.py
import time
import threading
from queue import Queue
from .animator import Live2DAnimator
from .live2d_constants import Live2DConstants

# WebSocket实例（延迟导入，避免循环导入）
_ws_instance = None

def _get_ws_instance():
    global _ws_instance
    if _ws_instance is None:
        try:
            from api.netwebsocket.ws_server import ws_instance
            _ws_instance = ws_instance
        except ImportError as e:
            print(f"[Live2DManager] 警告: 无法导入WebSocket实例: {e}")
            class MockQueue:
                def __init__(self): self.queue = Queue()
                def put(self, item): pass
            class MockWSInstance:
                def __init__(self): self.send_queue = MockQueue()
            _ws_instance = MockWSInstance()
    return _ws_instance


class Live2DManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"): return
        self.animator = Live2DAnimator()
        self._tts_queue = Queue()
        self._running = False
        self._initialized = True
        print("[Live2D] Live2D管理器初始化完成")

    # ==========================================
    # 🔥 核心：摄像头坐标 → Live2D 角度 映射
    # 摄像头坐标大约在 0~1 范围，0.5 为中心
    # Live2D 角度范围：头部 ±30，身体 ±10
    # ==========================================
    @staticmethod
    def _map_head(x=None, y=None, z=None):
        """将摄像头坐标映射为 Live2D 头部角度"""
        result = {}
        if x is not None:
            # (0.5 偏移) * 60 = ±30 度
            result['x'] = (x - 0.5) * 60
        if y is not None:
            # Y轴方向通常相反（屏幕Y向下，抬头是负），不需要反转
            # 如果方向反了，把减号换成加号：(y + 0.5 - 1.0) * 60
            result['y'] = (y - 0.5) * 60
        if z is not None:
            # Z轴（歪头），通常值很小，给个合理倍率
            result['z'] = z * 30
        return result

    @staticmethod
    def _map_body(x=None, y=None, z=None):
        """将摄像头坐标映射为 Live2D 身体角度"""
        result = {}
        if x is not None:
            result['x'] = (x - 0.5) * 20   # 身体幅度比头小：±10
        if y is not None:
            result['y'] = (y - 0.5) * 20
        if z is not None:
            result['z'] = z * 10
        return result

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def _send_current_params(self):
        """发送当前参数到前端（事件驱动）"""
        try:
            # 获取当前目标参数（不依赖时间）
            data = self.animator.get_current_target_params()
            _get_ws_instance().send_queue.put(data)
        except Exception as e:
            print(f"[Live2DManager] 发送参数失败: {e}")

    def _sync_loop(self):
        """低频心跳循环（2秒一次），仅用于保持连接"""
        heartbeat_count = 0
        while self._running:
            # 首先检查TTS队列
            if not self._tts_queue.empty():
                data = self._tts_queue.get_nowait()
                _get_ws_instance().send_queue.put(data)

            # 每2秒发送一次当前参数作为心跳（保持连接）
            heartbeat_count += 1
            if heartbeat_count >= 20:  # 0.1秒 * 20 = 2秒
                self._send_current_params()
                heartbeat_count = 0

            time.sleep(0.1)  # 0.1秒检查一次

    def send_tts(self, audio_base64: str, visemes: list):
        self._tts_queue.put({"type": "TTS_AUDIO", "audio_base64": audio_base64, "visemes": visemes})

    def set_emotion_mode(self, mode: str):
        """情绪模式概念已移除，保留方法用于兼容性"""
        pass  # 情绪模式概念已移除，所有动画由前端处理

    # 🔥 修改：加入坐标→角度映射
    def set_head(self, x=None, y=None, z=None):
        """设置头部目标值（输入摄像头归一化坐标，内部自动映射为角度）"""
        mapped = self._map_head(x, y, z)
        self.animator.set_head(**mapped)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_body(self, x=None, y=None, z=None):
        """设置身体目标值（输入摄像头归一化坐标，内部自动映射为角度）"""
        mapped = self._map_body(x, y, z)
        self.animator.set_body(**mapped)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_mouth(self, value=None):
        self.animator.set_mouth(value)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_hair(self, value=None):
        self.animator.set_hair(value)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_eyes(self, left=None, right=None):
        self.animator.set_eyes(left, right)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_arms(self, arm_a=None, arm_b=None):
        self.animator.set_arms(arm_a, arm_b)
        # 事件驱动：立即发送当前参数
        self._send_current_params()

    def set_activity(self, value=None):
        """活动度概念已移除，保留方法用于兼容性"""
        pass  # 活动度概念已移除，所有平滑动画由前端处理

    def reset_control(self):
        self.animator.reset_control()
        # 事件驱动：立即发送重置后的参数
        self._send_current_params()

    def send_custom_params(self, params_dict: dict):
        """
        设置自定义参数（持续生效, 直到 reset_control）
        输入参数应使用标准参数名（如 ParamAngleX, ParamBodyAngleX 等）
        支持旧参数名兼容（如 headX, mouth），但新代码应使用标准参数名
        """
        # 1. 标准化参数名并限制取值范围
        normalized = Live2DConstants.normalize_params(params_dict)

        # 2. 分组处理参数
        head_params = {}
        body_params = {}

        for param_name, value in normalized.items():
            # 头部角度参数
            if param_name == Live2DConstants.PARAM_ANGLE_X:
                head_params['x'] = value
            elif param_name == Live2DConstants.PARAM_ANGLE_Y:
                head_params['y'] = value
            elif param_name == Live2DConstants.PARAM_ANGLE_Z:
                head_params['z'] = value

            # 身体角度参数
            elif param_name == Live2DConstants.PARAM_BODY_ANGLE_X:
                body_params['x'] = value
            elif param_name == Live2DConstants.PARAM_BODY_ANGLE_Y:
                body_params['y'] = value
            elif param_name == Live2DConstants.PARAM_BODY_ANGLE_Z:
                body_params['z'] = value

            # 嘴巴开合
            elif param_name == Live2DConstants.PARAM_MOUTH_OPEN_Y:
                self.animator.set_mouth(value)

            # 头发飘动
            elif param_name == Live2DConstants.PARAM_HAIR_AHOGE:
                self.animator.set_hair(value)

            # 眼睛开合
            elif param_name == Live2DConstants.PARAM_EYE_L_OPEN:
                self.animator.set_eyes(left=value)
            elif param_name == Live2DConstants.PARAM_EYE_R_OPEN:
                self.animator.set_eyes(right=value)

            # 手臂显示（映射到 animator 的两个参数）
            elif param_name in [Live2DConstants.PARAM_ARM_LA, Live2DConstants.PARAM_ARM_LB]:
                # 左臂A或B -> 控制 arm_a
                self.animator.set_arms(arm_a=value)
            elif param_name in [Live2DConstants.PARAM_ARM_RA, Live2DConstants.PARAM_ARM_RB]:
                # 右臂A或B -> 控制 arm_b
                self.animator.set_arms(arm_b=value)

        # 3. 处理头部和身体角度（需要坐标映射）
        if head_params:
            # 头部参数已经是角度值，直接设置
            self.animator.set_head(**head_params)

        if body_params:
            # 身体参数已经是角度值，直接设置
            self.animator.set_body(**body_params)

        # 事件驱动：发送更新后的参数
        self._send_current_params()

    def stop(self):
        self._running = False
