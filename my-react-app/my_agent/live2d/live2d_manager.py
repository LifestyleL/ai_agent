# live2d_manager.py
import time
import threading
from queue import Queue
from live2d.animator import Live2DAnimator
from live2d.live2d_constants import Live2DConstants

# WebSocket实例（延迟导入，避免循环导入）
_ws_instance = None

def _get_ws_instance():
    global _ws_instance
    if _ws_instance is None:
        try:
            from netwebsocket.ws_server import ws_instance
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

    def _sync_loop(self):
        while self._running:
            if not self._tts_queue.empty():
                data = self._tts_queue.get_nowait()
            else:
                t = time.time()
                data = self.animator.compute_params(t)
            _get_ws_instance().send_queue.put(data)
            time.sleep(0.033)

    def send_tts(self, audio_base64: str, visemes: list):
        self._tts_queue.put({"type": "TTS_AUDIO", "audio_base64": audio_base64, "visemes": visemes})

    def set_emotion_mode(self, mode: str):
        self.animator.mode = mode

    # 🔥 修改：加入坐标→角度映射
    def set_head(self, x=None, y=None, z=None):
        """设置头部目标值（输入摄像头归一化坐标，内部自动映射为角度）"""
        mapped = self._map_head(x, y, z)
        self.animator.set_head(**mapped)

    def set_body(self, x=None, y=None, z=None):
        """设置身体目标值（输入摄像头归一化坐标，内部自动映射为角度）"""
        mapped = self._map_body(x, y, z)
        self.animator.set_body(**mapped)

    def set_mouth(self, value=None):
        self.animator.set_mouth(value)

    def set_hair(self, value=None):
        self.animator.set_hair(value)

    def set_eyes(self, left=None, right=None):
        self.animator.set_eyes(left, right)

    def set_arms(self, arm_a=None, arm_b=None):
        self.animator.set_arms(arm_a, arm_b)

    def set_activity(self, value=None):
        self.animator.set_activity(value)

    def reset_control(self):
        self.animator.reset_control()

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

    def stop(self):
        self._running = False
