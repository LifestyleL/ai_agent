"""
Phase 5: 路径遍历安全测试

验证 _resolve_safe_path() 拒绝各类路径遍历攻击。
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _backend_dir)

from core.memory.tools import _resolve_safe_path


class TestResolveSafePath:
    """路径遍历防护测试"""

    def test_reject_absolute_unix_path(self):
        """拒绝 Unix 绝对路径"""
        with pytest.raises(ValueError, match="绝对路径"):
            _resolve_safe_path("/etc/passwd")

    def test_reject_absolute_windows_path(self):
        """拒绝 Windows 绝对路径"""
        with pytest.raises(ValueError, match="绝对路径"):
            _resolve_safe_path("C:\\Windows\\System32\\config")

    def test_reject_dot_dot_traversal(self):
        """拒绝 ../ 目录遍历"""
        with pytest.raises(ValueError, match="路径遍历"):
            _resolve_safe_path("../../../etc/passwd")

    def test_reject_dot_dot_mid_path(self):
        """拒绝路径中间的 .."""
        with pytest.raises(ValueError, match="路径遍历"):
            _resolve_safe_path("diary/../etc/passwd")

    def test_reject_encoded_traversal(self):
        """拒绝 URL 编码的目录遍历"""
        with pytest.raises(ValueError, match="路径遍历"):
            _resolve_safe_path("..%2F..%2Fetc%2Fpasswd")

    def test_reject_url_encoded_dot_dot(self):
        """拒绝 URL 编码的 ../ (%2e%2e%2f)"""
        with pytest.raises(ValueError, match="路径遍历"):
            _resolve_safe_path("%2e%2e%2fetc")

    def test_accept_normal_relative(self):
        """接受正常的相对路径"""
        result = _resolve_safe_path("diary/daily/2024-01-01.md")
        assert result.name == "2024-01-01.md"
        assert "agent_memory" in str(result)

    def test_accept_single_filename(self):
        """接受单文件名"""
        result = _resolve_safe_path("cards/cards.jsonl")
        assert result.name == "cards.jsonl"

    def test_reject_backslash_traversal_windows(self):
        """拒绝反斜杠格式的目录遍历"""
        with pytest.raises(ValueError, match="路径遍历"):
            _resolve_safe_path("..\\..\\..\\etc\\passwd")

    def test_accept_nested_subdir(self):
        """接受多层正常子目录"""
        result = _resolve_safe_path("a/b/c/test.md")
        assert result.name == "test.md"
        assert "agent_memory" in str(result)
