"""
SAVAP (Surreal-AudioVisual Asset Pipeline) Deterministic 4K 60FPS Offline Pipe
依據 Google Antigravity SAVAP Technical Blueprint 第 10 頁設計：

1. Time-Step Hook: 確定性步進時鐘，解耦 Wall-Clock 實時依賴
2. Pixel Capture: 3840x2160 未壓縮 RGBA Frame Buffer
3. HW Pipe Stream: 零磁碟中介寫入 (Zero-disk write)，直接將 byte stream 推送至 FFmpeg stdin
4. Mux & Render: Apple Silicon VideoToolbox / NVIDIA NVENC 硬體加速編碼
"""

import os
import sys
import time
import shutil
import subprocess
import logging
from typing import Optional, Tuple, Callable
import numpy as np

logger = logging.getLogger("SAVAP.Deterministic4KPipe")


class SAVAPDeterministic4KPipe:
    """
    確定性 4K 60FPS 離線硬體編碼管線
    """
    def __init__(
        self,
        output_path: str,
        width: int = 3840,
        height: int = 2160,
        fps: int = 60,
        audio_path: Optional[str] = None,
        bitrate: str = "80M",
        enable_10bit: bool = True
    ):
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.audio_path = audio_path
        self.bitrate = bitrate
        self.enable_10bit = enable_10bit
        
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.frames_rendered = 0
        self.encoder_name = self._detect_best_hw_encoder()

    def _detect_best_hw_encoder(self) -> str:
        """偵測最佳硬體加速編碼器"""
        if sys.platform == "darwin":
            # macOS: 優先使用 VideoToolbox HEVC / H.264
            return "hevc_videotoolbox"
        else:
            # 嘗試檢測 NVENC
            try:
                probe = subprocess.run(
                    ["ffmpeg", "-encoders"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3
                )
                if "hevc_nvenc" in probe.stdout:
                    return "hevc_nvenc"
                if "h264_nvenc" in probe.stdout:
                    return "h264_nvenc"
            except Exception:
                pass
            return "libx265" if self.enable_10bit else "libx264"

    def start_pipeline(self):
        """啟動無中介磁碟寫入的 FFmpeg stdin 管道進程"""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        
        # 基礎輸入參數：從 pipe:0 讀取 rawvideo (RGBA)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.width}x{self.height}",
            "-pix_fmt", "rgba",
            "-r", str(self.fps),
            "-i", "pipe:0"
        ]

        # 若有音軌，合併音訊
        if self.audio_path and os.path.exists(self.audio_path):
            cmd.extend([
                "-i", self.audio_path,
                "-c:a", "aac",
                "-b:a", "320k"
            ])

        # 編碼器與 10-bit 抗色帶品質參數 (Anti-Banding for Ambient Ganzfeld Fog)
        pix_fmt = "yuv420p10le" if self.enable_10bit else "yuv420p"
        cmd.extend([
            "-c:v", self.encoder_name,
            "-pix_fmt", pix_fmt
        ])

        if "videotoolbox" in self.encoder_name:
            # VideoToolbox HEVC 10-bit
            cmd.extend(["-b:v", self.bitrate, "-tag:v", "hvc1"])
            if self.enable_10bit and "hevc" in self.encoder_name:
                cmd.extend(["-profile:v", "main10"])
        elif "nvenc" in self.encoder_name:
            cmd.extend(["-b:v", self.bitrate, "-preset", "p7"])
            if self.enable_10bit:
                cmd.extend(["-profile:v", "main10"])
        else:
            cmd.extend(["-preset", "fast", "-crf", "16"])

        cmd.extend([
            "-shortest",
            self.output_path
        ])

        logger.info(f"SAVAP: 啟動確定性 4K 離線編碼進程 (編碼器: {self.encoder_name}, 10-bit: {self.enable_10bit})...")
        self.ffmpeg_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        self.frames_rendered = 0

    @staticmethod
    def apply_blue_noise_dither(frame_rgba_np: np.ndarray, strength: float = 1.5) -> np.ndarray:
        """
        對輸出幀施加高頻藍噪聲/三角隨機抖動 (Stochastic Dithering)
        消除大氣光霧、微光暈染在量化時產生的色帶 (Anti-Banding)
        """
        h, w, c = frame_rgba_np.shape
        # 產生高頻抖動噪聲
        noise = (np.random.rand(h, w, 1) - 0.5) * (strength * 2.0)
        dithered_rgb = np.clip(frame_rgba_np[:, :, :3].astype(np.float32) + noise, 0, 255).astype(np.uint8)
        frame_rgba_np[:, :, :3] = dithered_rgb
        return frame_rgba_np

    def push_frame_rgba(self, frame_bytes: bytes) -> bool:
        """
        將一幀 uncompressed 4K RGBA 記憶體直接 push 給 FFmpeg stdin
        長度必須嚴格等於 width * height * 4
        """
        if not self.ffmpeg_process or not self.ffmpeg_process.stdin:
            raise RuntimeError("FFmpeg 離線渲染進程未啟動")

        expected_size = self.width * self.height * 4
        if len(frame_bytes) != expected_size:
            raise ValueError(f"幀緩衝區大小不匹配: 期望 {expected_size} bytes，收到 {len(frame_bytes)} bytes")

        try:
            self.ffmpeg_process.stdin.write(frame_bytes)
            self.frames_rendered += 1
            return True
        except (BrokenPipeError, IOError) as e:
            logger.error(f"FFmpeg 管道斷開: {e}")
            return False

    def push_frame_numpy(self, frame_np: np.ndarray) -> bool:
        """支援傳入 NumPy 陣列 (H, W, 4)"""
        return self.push_frame_rgba(frame_np.tobytes())

    def finalize(self) -> Tuple[bool, str]:
        """結束管道並等待封裝完成"""
        if not self.ffmpeg_process:
            return False, "Process not running"

        try:
            if self.ffmpeg_process.stdin:
                self.ffmpeg_process.stdin.close()
            _, stderr = self.ffmpeg_process.communicate(timeout=60)
            return_code = self.ffmpeg_process.returncode

            if return_code == 0:
                logger.info(f"SAVAP: 確定性 4K 輸出成功！共計渲染 {self.frames_rendered} 幀 -> {self.output_path}")
                return True, self.output_path
            else:
                err_msg = stderr.decode("utf-8", errors="replace") if stderr else "未知錯誤"
                logger.error(f"FFmpeg 編碼退出異常 ({return_code}): {err_msg}")
                return False, err_msg
        except Exception as e:
            logger.exception(f"等待 FFmpeg 封裝時逾時或出錯: {e}")
            if self.ffmpeg_process:
                self.ffmpeg_process.kill()
            return False, str(e)


class DeterministicTimeStepClock:
    """
    確定性時間步進控制器
    將動畫運算與系統實時時鐘完全解耦
    """
    def __init__(self, fps: int = 60, total_duration_seconds: float = 10.0):
        self.fps = fps
        self.dt = 1.0 / fps
        self.total_duration = total_duration_seconds
        self.total_frames = int(round(total_duration_seconds * fps))
        self.current_frame = 0

    def step(self) -> Tuple[int, float, bool]:
        """
        步進到下一幀
        回傳: (當前幀索引, 當前時間戳秒, 是否已完成)
        """
        if self.current_frame >= self.total_frames:
            return self.current_frame, self.current_frame * self.dt, True

        frame_idx = self.current_frame
        timestamp = frame_idx * self.dt
        self.current_frame += 1
        is_done = self.current_frame >= self.total_frames
        return frame_idx, timestamp, is_done

    def reset(self):
        self.current_frame = 0
