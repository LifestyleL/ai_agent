import json
from pathlib import Path
from backend.core.state_machine.state_machine import State

class StateMemory:
    """独立于业务记忆，仅负责保存会话的机械状态和槽位"""
    def __init__(self, save_dir: str = "data/state_sessions"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self, session_id: str) -> dict:
        file_path = self.save_dir / f"{session_id}.json"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['state'] = State(data['state']) # 反序列化为枚举
                return data
        return {"state": State.IDLE, "slots": {}}

    def save_state(self, session_id: str, state: State, slots: dict = None):
        data = {
            "state": state.value,
            "slots": slots or {}
        }
        file_path = self.save_dir / f"{session_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)