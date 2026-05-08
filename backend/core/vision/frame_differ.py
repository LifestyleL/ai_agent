"""
像素级变化检测：对比两帧 base64 图像，判断画面是否有意义变化
"""
import base64
import hashlib
import io
from PIL import Image
import numpy as np

_RESIZE = (160, 120)  # 缩小到此尺寸加速对比


class FrameDiffer:
    """比较两帧 base64 图像的像素差异比例"""

    def __init__(self, threshold: float = 0.08):
        self._threshold = threshold
        self._last_hash: str = ""
        self._last_pixels: np.ndarray = None

    def is_changed(self, base64_image: str) -> bool:
        """
        与上一帧比较像素差异。
        首帧永远返回 True。
        """
        # 快速路径：数据完全相同时跳过解码
        data_hash = hashlib.md5(base64_image.encode()).hexdigest()
        if data_hash == self._last_hash:
            return False

        try:
            pixels = self._decode(base64_image)
        except Exception:
            return False  # 解码失败，保守跳过

        if self._last_pixels is None:
            self._last_hash = data_hash
            self._last_pixels = pixels
            return True  # 首帧视为变化

        total = pixels.size
        diff = np.count_nonzero(pixels != self._last_pixels)

        self._last_hash = data_hash
        self._last_pixels = pixels

        ratio = diff / total
        return ratio >= self._threshold

    def _decode(self, base64_image: str) -> np.ndarray:
        img_bytes = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = img.resize(_RESIZE, Image.NEAREST)
        return np.array(img, dtype=np.uint8)
