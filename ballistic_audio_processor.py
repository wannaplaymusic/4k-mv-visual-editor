import numpy as np

class BallisticAudioProcessor:
    """
    SOTA 音訊非對稱動態濾波器 (Ballistic Asymmetric Envelope Processor)
    - 依據兩次專家會議規範，模擬物理類比 VU 錶響應特性
    - Attack 時間 10ms (快速響應打擊樂瞬態)，Decay 時間 120ms (平滑釋放防止神經質閃爍)
    - 消除 Onset 突變殘影，賦予 4K MV 自然流暢的「動態呼吸感」
    """
    def __init__(self, sample_rate=44100, hop_length=512, tau_attack_ms=10.0, tau_decay_ms=120.0):
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.dt = hop_length / sample_rate

        self.alpha_attack = np.exp(-self.dt / (tau_attack_ms / 1000.0))
        self.alpha_decay = np.exp(-self.dt / (tau_decay_ms / 1000.0))

        self._envelope = 0.0

    def process_frame(self, raw_energy: float) -> float:
        """
        對單一訊號幀進行單向非對稱濾波
        """
        if raw_energy > self._envelope:
            # 瞬態衝擊階段 (Attack)
            self._envelope = (1.0 - self.alpha_attack) * raw_energy + self.alpha_attack * self._envelope
        else:
            # 能量衰退階段 (Decay)
            self._envelope = (1.0 - self.alpha_decay) * raw_energy + self.alpha_decay * self._envelope

        return float(self._envelope)

    def process_sequence(self, raw_energies: np.ndarray) -> np.ndarray:
        """
        批次處理一整條能量包絡曲線
        """
        out = np.zeros_like(raw_energies, dtype=np.float32)
        env = 0.0
        for i in range(len(raw_energies)):
            val = raw_energies[i]
            if val > env:
                env = (1.0 - self.alpha_attack) * val + self.alpha_attack * env
            else:
                env = (1.0 - self.alpha_decay) * val + self.alpha_decay * env
            out[i] = env
        return out
