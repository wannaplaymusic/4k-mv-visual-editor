import os
import re
import json
import logging
import subprocess
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTextEdit, QLineEdit, QComboBox, QProgressBar, QCheckBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

from audio_analyzer import AudioBeatDetector

logger = logging.getLogger("StandaloneInjector.ShortsExporter")

def setup_exporter_logger():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(workspace_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "shorts_exporter.log")
    
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)

setup_exporter_logger()

def get_ffmpeg_path():
    paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
    for p in paths:
        try:
            subprocess.run([p, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return p
        except FileNotFoundError:
            continue
    return 'ffmpeg'

class RenderLogParser:
    @staticmethod
    def parse_render_log(log_path):
        if not log_path or not os.path.exists(log_path):
            return None
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Strategy 1: Find JSON metadata marker and parse the JSON on the next line
            marker = "=== RENDER_METADATA_JSON ==="
            for i, line in enumerate(lines):
                if marker in line:
                    # The JSON is on the next line, after the logging timestamp/level prefix
                    if i + 1 < len(lines):
                        json_line = lines[i + 1].strip()
                        # Strip logging prefix: "2025-01-01 12:00:00,000 [INFO] {...}"
                        json_match = re.search(r'\{.*\}', json_line)
                        if json_match:
                            try:
                                return json.loads(json_match.group())
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON 解析失敗 {log_path}: {e}")
            
            # Strategy 2: Fallback — parse text lines for known fields
            content = ''.join(lines)
            result = {
                "bpm": 120.0,
                "duration": 0.0,
                "storyboard": [],
                "genre": "Unknown",
                "resolution": "1920x1080",
                "fps": 30,
                "audio_path": ""
            }
            
            # Parse BPM from "BPM=128" or "BPM: 128"
            bpm_match = re.search(r'BPM[=:]\s*([\d.]+)', content, re.IGNORECASE)
            if bpm_match:
                result["bpm"] = float(bpm_match.group(1))
            
            # Parse resolution and fps from "解析度: 3840x2160@30fps" or "3840x2160@60fps"
            res_match = re.search(r'(\d{3,4})x(\d{3,4})@(\d+)fps', content)
            if res_match:
                result["resolution"] = f"{res_match.group(1)}x{res_match.group(2)}"
                result["fps"] = int(res_match.group(3))
            
            # Parse total frames to estimate duration
            frames_match = re.search(r'總幀數[=:]\s*(\d+)', content)
            if frames_match and result["fps"] > 0:
                result["duration"] = int(frames_match.group(1)) / result["fps"]
            
            # Parse audio path from "輸出: /path/to/file.mp4" -> infer audio from same dir
            output_match = re.search(r'輸出:\s*(.+\.mp4)', content)
            if output_match:
                mp4_path = output_match.group(1).strip()
                # Try common audio extensions in the same directory
                base = os.path.splitext(mp4_path)[0]
                for ext in ['.mp3', '.wav', '.m4a', '.flac']:
                    if os.path.exists(base + ext):
                        result["audio_path"] = base + ext
                        break
            
            return result if result["duration"] > 0 else None
        except Exception as e:
            logger.error(f"讀取 {log_path} 失敗: {e}")
            return None

class HighlightAnalyzer:
    @staticmethod
    def analyze_track(video_path, render_log_path=None, num_clips=3, clip_duration=60):
        metadata = None
        if render_log_path and os.path.exists(render_log_path):
            metadata = RenderLogParser.parse_render_log(render_log_path)
            
        storyboard = []
        if metadata and "storyboard" in metadata and metadata["storyboard"]:
            storyboard = metadata["storyboard"]
        else:
            logger.info(f"無有效 storyboard，提取音訊分析: {video_path}")
            temp_wav = video_path + ".temp.wav"
            ffmpeg_path = get_ffmpeg_path()
            cmd = [ffmpeg_path, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "22050", "-f", "wav", temp_wav]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            detector = AudioBeatDetector()
            try:
                analysis = detector.analyze(temp_wav, genre='Auto (自動偵測)')
                storyboard = analysis.get("storyboard", [])
            except Exception as e:
                logger.error(f"音訊分析失敗: {e}")
            
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
                
        weights = {
            "Drop": 1.0, "Chorus": 0.9, "Build-up": 0.7, 
            "Verse": 0.4, "Bridge": 0.3, "Intro": 0.1, "Outro": 0.1
        }
        
        scored_sections = []
        for sec in storyboard:
            sec_name = sec.get("section", "Verse")
            weight = weights.get(sec_name, 0.4)
            start = sec.get("start", 0.0)
            end = sec.get("end", 0.0)
            dur = end - start
            
            duration_factor = 1.0 if dur >= 15 else 0.5
            score = weight * duration_factor
            
            scored_sections.append({
                "start": start,
                "end": end,
                "section": sec_name,
                "score": score
            })
            
        scored_sections.sort(key=lambda x: x["score"], reverse=True)
        
        selected = []
        for sec in scored_sections:
            if len(selected) >= num_clips:
                break
                
            valid = True
            for sel in selected:
                if abs(sec["start"] - sel["start"]) < 15.0:
                    valid = False
                    break
            
            if valid:
                selected.append(sec)
                
        selected.sort(key=lambda x: x["start"])
        
        cap = cv2.VideoCapture(video_path)
        final_clips = []
        
        for i, clip in enumerate(selected):
            clip_dict = {
                "index": i + 1,
                "start": clip["start"],
                "end": clip["start"] + clip_duration,
                "section": clip["section"],
                "score": clip["score"]
            }
            
            frames_to_check = [clip_dict["start"] + 1.0, clip_dict["start"] + clip_duration/2]
            variances = []
            for t in frames_to_check:
                cap.set(cv2.CAP_PROP_POS_MSEC, int(t * 1000))
                ret, frame = cap.read()
                if ret:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    variances.append(np.var(gray))
            
            if variances and np.mean(variances) < 500:
                logger.warning(f"偵測到靜態畫面於 {clip_dict['start']}s")
                clip_dict["static"] = True
            else:
                clip_dict["static"] = False
                
            final_clips.append(clip_dict)
            
        cap.release()
        return final_clips, metadata


class FolderScanWorker(QThread):
    scan_complete = pyqtSignal(list)
    progress_update = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        self.progress_update.emit(f"開始掃描資料夾: {self.folder_path}")
        results = []
        
        try:
            for root, dirs, files in os.walk(self.folder_path):
                for file in files:
                    if file.lower().endswith(".mp4"):
                        video_path = os.path.join(root, file)
                        base_name = os.path.splitext(file)[0]
                        
                        log_path = os.path.join(root, f"{base_name}_render.log")
                        if not os.path.exists(log_path):
                            log_path = None
                            
                        results.append({
                            "video_path": video_path,
                            "render_log": log_path,
                            "name": base_name
                        })
                        
            self.progress_update.emit(f"掃描完成，找到 {len(results)} 個影片。")
            self.scan_complete.emit(results)
        except Exception as e:
            logger.error(f"掃描失敗: {e}", exc_info=True)
            self.progress_update.emit(f"掃描失敗: {e}")
            self.scan_complete.emit([])


class HighlightAnalysisWorker(QThread):
    progress_update = pyqtSignal(str, int)
    analysis_complete = pyqtSignal(dict)

    def __init__(self, tracks, num_clips, clip_duration, cache_dir=None):
        super().__init__()
        self.tracks = tracks
        self.num_clips = num_clips
        self.clip_duration = clip_duration
        self.cache_dir = cache_dir
        self._is_running = True
        self.cache_file = os.path.join(self.cache_dir, ".shorts_analysis_cache.json") if self.cache_dir else None

    def stop(self):
        self._is_running = False

    def load_cache(self):
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"讀取分析快取失敗: {e}")
        return {}

    def save_cache(self, results):
        if self.cache_file:
            try:
                temp_file = self.cache_file + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                os.replace(temp_file, self.cache_file)
            except Exception as e:
                logger.warning(f"儲存分析快取失敗: {e}")

    def run(self):
        results = self.load_cache()
        total_tracks = len(self.tracks)
        cached_count = sum(1 for t in self.tracks if t["name"] in results and len(results[t["name"]].get("clips", [])) > 0)
        
        if cached_count > 0:
            self.progress_update.emit(f"🔄 偵測到歷史分析快取，已載入 {cached_count}/{total_tracks} 首曲目...", int((cached_count / total_tracks) * 100))
        
        for i, track in enumerate(self.tracks):
            if not self._is_running:
                break
                
            track_name = track["name"]
            
            # Check if this track was already analyzed and has valid clips
            if track_name in results and len(results[track_name].get("clips", [])) > 0:
                pct = int(((i + 1) / total_tracks) * 100)
                self.progress_update.emit(f"⚡ [已快取跳過] ({i+1}/{total_tracks}): {track_name}", pct)
                continue
                
            pct = int(((i + 1) / total_tracks) * 100)
            self.progress_update.emit(f"正在分析 ({i+1}/{total_tracks}): {track_name}", pct)
            try:
                clips, metadata = HighlightAnalyzer.analyze_track(
                    track["video_path"], 
                    track["render_log"],
                    self.num_clips,
                    self.clip_duration
                )
                results[track_name] = {
                    "video_path": track["video_path"],
                    "clips": clips,
                    "metadata": metadata
                }
                # Save checkpoint immediately after each track is analyzed
                self.save_cache(results)
            except Exception as e:
                logger.error(f"分析 {track_name} 失敗: {e}", exc_info=True)
                
        self.progress_update.emit("AI 分析完成。", 100)
        self.analysis_complete.emit(results)


class ShortsExportWorker(QThread):
    progress_update = pyqtSignal(str, int)
    export_complete = pyqtSignal(bool)
    single_clip_done = pyqtSignal(str)

    def __init__(self, analysis_results, output_dir):
        super().__init__()
        self.analysis_results = analysis_results
        self.output_dir = output_dir
        self._is_running = True

    def is_valid_mp4(self, file_path):
        """Check if output mp4 exists and is not corrupt/empty (at least 100KB)."""
        if not os.path.exists(file_path):
            return False
        try:
            if os.path.getsize(file_path) < 100 * 1024:
                return False
            # Quick check with cv2
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                cap.release()
                return False
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            return frame_count > 0
        except Exception:
            return False

    def run(self):
        ffmpeg_path = get_ffmpeg_path()
        os.makedirs(self.output_dir, exist_ok=True)
        
        total_clips = sum(len(track_data["clips"]) for track_data in self.analysis_results.values())
        processed_clips = 0
        
        # Check for macOS videotoolbox
        hw_accel = ""
        try:
            output = subprocess.check_output([ffmpeg_path, "-encoders"], text=True)
            if "h264_videotoolbox" in output:
                hw_accel = "h264_videotoolbox"
            else:
                hw_accel = "libx264"
        except Exception:
            hw_accel = "libx264"
            
        for track_name, track_data in self.analysis_results.items():
            if not self._is_running:
                break
                
            video_path = track_data["video_path"]
            clips = track_data["clips"]
            metadata = track_data.get("metadata")
            
            for clip in clips:
                if not self._is_running:
                    break
                    
                start = clip["start"]
                dur = clip["end"] - clip["start"]
                idx = clip["index"]
                
                out_name = f"{track_name}_short_{idx:02d}.mp4"
                out_path = os.path.join(self.output_dir, out_name)
                
                # Check for existing valid export (Resume/續傳功能)
                if self.is_valid_mp4(out_path):
                    processed_clips += 1
                    pct = int((processed_clips / total_clips) * 100) if total_clips > 0 else 100
                    self.progress_update.emit(f"⚡ [已存在跳過] {out_name}", pct)
                    continue
                
                # Temp file to ensure atomic write on completion
                temp_out_path = os.path.join(self.output_dir, f".tmp_{out_name}")
                if os.path.exists(temp_out_path):
                    try:
                        os.remove(temp_out_path)
                    except Exception:
                        pass
                
                pct = int((processed_clips / total_clips) * 100) if total_clips > 0 else 0
                self.progress_update.emit(f"🎬 正在匯出: {out_name}", pct)
                
                cmd = [
                    ffmpeg_path, "-y",
                    "-ss", str(start),
                    "-i", video_path,
                    "-t", str(dur),
                    "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
                    "-c:v", hw_accel,
                    "-b:v", "8M",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    temp_out_path
                ]
                
                try:
                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res.returncode == 0 and self.is_valid_mp4(temp_out_path):
                        os.replace(temp_out_path, out_path)
                        processed_clips += 1
                        self.single_clip_done.emit(out_name)
                    else:
                        logger.error(f"FFmpeg 匯出失敗或檔案損毀: {out_name}")
                        if os.path.exists(temp_out_path):
                            os.remove(temp_out_path)
                except Exception as e:
                    logger.error(f"FFmpeg 錯誤 {out_name}: {e}")
                    if os.path.exists(temp_out_path):
                        try:
                            os.remove(temp_out_path)
                        except Exception:
                            pass
            
            # Generate social text with visual credits
            self.generate_shorts_social_text(track_name, clips, self.output_dir, metadata)
            
        if self._is_running:
            self.progress_update.emit("批次匯出完成", 100)
            self.export_complete.emit(True)
        else:
            self.progress_update.emit("匯出已中止（已保留進度，下次重啟將自動續傳）", int((processed_clips / total_clips) * 100) if total_clips > 0 else 0)

    def stop(self):
        self._is_running = False

    def generate_shorts_social_text(self, track_name, clips, output_dir, metadata=None):
        text_path = os.path.join(output_dir, f"{track_name}_shorts_social.txt")
        
        # Parse artist/song from track name (e.g., "PoHan - Neon Dreams")
        artist = "PoHan"
        song = track_name
        if " - " in track_name:
            parts = track_name.split(" - ", 1)
            if parts[0].strip().upper() in ["POHAN", "POHAN528"]:
                song = parts[1].strip()
            else:
                song = parts[1].strip()
        
        clean_song = re.sub(r'[^\w]', '', song)
        clean_artist = "PoHan"
        
        # Extract visual credits and storyboard-visual mapping from metadata
        visual_credits = []
        storyboard_visual_map = []
        if metadata:
            visual_credits = metadata.get("visual_credits", [])
            storyboard_visual_map = metadata.get("storyboard_visual_map", [])
        
        def get_clip_visual_credits(clip_start, clip_end):
            """Find which visual modules appear during this clip's time range."""
            if not storyboard_visual_map or not visual_credits:
                return visual_credits  # Fallback: return all credits
            
            seen_indices = set()
            for seg in storyboard_visual_map:
                seg_start = seg.get("start", 0)
                seg_end = seg.get("end", 0)
                vis_idx = seg.get("visual_index", -1)
                # Check time overlap: clip and segment intersect
                if seg_end > clip_start and seg_start < clip_end and vis_idx >= 0:
                    seen_indices.add(vis_idx)
            
            # Return only credits for modules that appear in this clip
            return [c for c in visual_credits if c.get("index") in seen_indices]
        
        lines = [
            "======================================================================",
            f"📱 YOUTUBE SHORTS BATCH EXPORT — {track_name}",
            "======================================================================",
            f"Track: {song}",
            f"Artist: {artist}",
            f"Clips: {len(clips)}",
            "======================================================================",
            "",
        ]
        
        for clip in clips:
            dur = clip['end'] - clip['start']
            
            # Get visual credits for this specific clip's time range
            clip_credits = get_clip_visual_credits(clip['start'], clip['end'])
            
            lines.extend([
                f"--- [Clip {clip['index']}] ({dur:.0f}s) ---",
                "",
                "【YouTube Shorts Title】",
                f"{song} - {artist} | 4K Audio-Reactive p5.js Visualizer 🔥 #shorts #p5js #visualizer",
                "",
                "【YouTube Shorts Description】",
                f"Experience the immersive 4K audio-reactive generative art powered by p5.js! 🎧✨",
                "",
                "👉 Watch full 4K MV on our channel:",
                f"🔗 https://www.youtube.com/@pohan528",
                "",
            ])
            
            # Per-clip visual credits (only modules appearing in this clip)
            if clip_credits:
                lines.append("🎨 【Visual Credits & Licensing】")
                for credit in clip_credits:
                    name = credit.get("name", "Visual")
                    author = credit.get("author", "Unknown")
                    lic = credit.get("license", "Creative Commons")
                    url = credit.get("url", "")
                    lines.append(f"  - Visual: \"{name}\" by {author}")
                    if credit.get("inspired_by"):
                        lines.append(f"    * Inspired by original sketch: {credit['inspired_by']}")
                    if url and url != "OpenProcessing":
                        lines.append(f"    * Link: {url}")
                    lines.append(f"    * License: {lic}")
                lines.append("  All visual elements are licensed under Creative Commons.")
                lines.append("  Please respect the licensing terms and credit the original authors.")
            else:
                lines.append("🎨 Visual licensing details can be found in the full MV description.")
            
            lines.extend([
                "",
                "【Instagram Reels Caption】",
                f"🎧 {song} - {artist} | Audio-Reactive p5.js Visualizer ✨",
                "Immerse yourself in precision audio-reactive generative visuals 🌊",
                "👉 Watch Full 4K MV: https://www.youtube.com/@pohan528",
                "",
                "【TikTok Caption】",
                f"{song} - {artist} 🎧 4K Audio-Reactive p5.js Visualizer! 🤯✨ #p5js #audioreactive #visualizer #generativeart #creativecoding #shorts #fyp",
                "",
                "【Hashtags】",
                f"#shorts #p5js #AudioReactive #GenerativeArt #CreativeCoding #Visualizer #MusicVideo #{clean_song} #{clean_artist} #pohan528 #4KMV #VJLoop #edm #music #beat",
                "",
            ])
        
        lines.extend([
            "======================================================================",
            "⚖️ COPYRIGHT NOTICE",
            "All visual elements in this video are created using open-source",
            "sketches licensed under Creative Commons. Original authors are",
            "credited above for each clip. Please respect their licensing terms.",
            "For full credits and complete audiovisual experience, visit: https://www.youtube.com/@pohan528",
            "======================================================================",
            "",
            "Generated by 4K MV Visual Integration Editor — Shorts Batch Exporter",
            "======================================================================",
        ])
        
        try:
            with open(text_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"社群文字已寫入: {text_path}")
        except Exception as e:
            logger.error(f"寫入 social text 失敗: {e}")


class ShortsExporterTab(QWidget):
    def __init__(self, parent_app=None):
        super().__init__()
        self.app = parent_app
        self.scanned_tracks = []
        self.analysis_results = {}
        
        self.scan_worker = None
        self.analyze_worker = None
        self.export_worker = None
        
        self.init_tab()

    def init_tab(self):
        if self.layout() is not None:
            return
            
        self.setStyleSheet("background-color: #0b0b0e; color: #f4f4f5;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # Scroll Area
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #0b0b0e; }
            QWidget { background-color: #0b0b0e; }
            QScrollBar:vertical { width: 8px; background: #121215; }
            QScrollBar::handle:vertical { background: #3f3f46; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #a855f7; }
        """)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(10)
        
        # Section 1: Folder Selection
        folder_group = QGroupBox("📁 資料夾選擇")
        folder_group.setStyleSheet("QGroupBox { border: 1px solid #27272a; border-radius: 6px; padding-top: 18px; font-weight: bold; }")
        folder_layout = QGridLayout(folder_group)
        
        self.src_folder_input = QLineEdit()
        self.src_folder_input.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; padding: 4px;")
        src_btn = QPushButton("瀏覽來源...")
        src_btn.setStyleSheet("background-color: #3f3f46; padding: 4px 8px; border-radius: 4px;")
        src_btn.clicked.connect(self.browse_src_folder)
        
        self.out_folder_input = QLineEdit()
        self.out_folder_input.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; padding: 4px;")
        out_btn = QPushButton("瀏覽匯出...")
        out_btn.setStyleSheet("background-color: #3f3f46; padding: 4px 8px; border-radius: 4px;")
        out_btn.clicked.connect(self.browse_out_folder)
        
        folder_layout.addWidget(QLabel("來源資料夾:"), 0, 0)
        folder_layout.addWidget(self.src_folder_input, 0, 1)
        folder_layout.addWidget(src_btn, 0, 2)
        folder_layout.addWidget(QLabel("輸出資料夾:"), 1, 0)
        folder_layout.addWidget(self.out_folder_input, 1, 1)
        folder_layout.addWidget(out_btn, 1, 2)
        
        layout.addWidget(folder_group)
        
        # Section 2: Scan Results
        scan_group = QGroupBox("📊 掃描結果")
        scan_group.setStyleSheet("QGroupBox { border: 1px solid #27272a; border-radius: 6px; padding-top: 18px; font-weight: bold; }")
        scan_layout = QVBoxLayout(scan_group)
        
        self.scan_count_label = QLabel("找到 0 首曲目 (0 有 render.log)")
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("background-color: #18181b; border: 1px solid #27272a;")
        
        scan_layout.addWidget(self.scan_count_label)
        scan_layout.addWidget(self.file_list)
        layout.addWidget(scan_group)
        
        # Section 3: Configuration
        config_group = QGroupBox("⚙️ 匯出設定")
        config_group.setStyleSheet("QGroupBox { border: 1px solid #27272a; border-radius: 6px; padding-top: 18px; font-weight: bold; }")
        config_layout = QHBoxLayout(config_group)
        
        config_layout.addWidget(QLabel("Shorts 時長 (秒):"))
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["15", "30", "45", "60"])
        self.duration_combo.setCurrentText("60")
        self.duration_combo.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; padding: 4px;")
        config_layout.addWidget(self.duration_combo)
        
        config_layout.addWidget(QLabel("每首擷取數量:"))
        self.clips_combo = QComboBox()
        self.clips_combo.addItems(["1", "2", "3", "4", "5"])
        self.clips_combo.setCurrentText("3")
        self.clips_combo.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; padding: 4px;")
        config_layout.addWidget(self.clips_combo)
        
        self.ai_checkbox = QCheckBox("🤖 啟用 AI 導演分析")
        self.ai_checkbox.setStyleSheet("color: #c084fc;")
        config_layout.addWidget(self.ai_checkbox)
        config_layout.addStretch()
        
        layout.addWidget(config_group)
        
        # Section 4: Action Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_scan = QPushButton("🔍 掃描資料夾")
        self.btn_scan.setStyleSheet("background-color: #10b981; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_scan.clicked.connect(self.start_scan)
        
        self.btn_analyze = QPushButton("🤖 AI 分析高潮段")
        self.btn_analyze.setStyleSheet("background-color: #a855f7; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_analyze.clicked.connect(self.start_analysis)
        
        self.btn_export = QPushButton("🚀 批量匯出 Shorts")
        self.btn_export.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a855f7, stop:1 #c084fc); color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_export.clicked.connect(self.start_export)
        
        self.btn_stop = QPushButton("⏹️ 中止")
        self.btn_stop.setStyleSheet("background-color: #ef4444; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all)
        
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_analyze)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.btn_stop)
        
        layout.addLayout(btn_layout)
        
        # Section 5: Analysis Preview
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; padding: 4px; font-family: monospace;")
        layout.addWidget(QLabel("👁️ 分析預覽:"))
        layout.addWidget(self.preview_text)
        
        # Section 6: Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #27272a; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #a855f7; width: 10px; }
        """)
        self.progress_label = QLabel("準備就緒")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        
        # Section 7: Console Log
        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet("background-color: #000000; color: #a1a1aa; border: 1px solid #27272a; font-family: monospace;")
        layout.addWidget(QLabel("📝 系統日誌:"))
        layout.addWidget(self.console_log)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def log_to_console(self, msg):
        logger.info(msg)
        self.console_log.append(f"> {msg}")
        # Scroll to bottom
        scrollbar = self.console_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def browse_src_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇來源資料夾")
        if folder:
            self.src_folder_input.setText(folder)

    def browse_out_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if folder:
            self.out_folder_input.setText(folder)

    def start_scan(self):
        src = self.src_folder_input.text().strip()
        if not src or not os.path.isdir(src):
            QMessageBox.warning(self, "錯誤", "請選擇有效的來源資料夾")
            return
            
        self.btn_scan.setEnabled(False)
        self.log_to_console(f"開始掃描: {src}")
        
        self.scan_worker = FolderScanWorker(src)
        self.scan_worker.progress_update.connect(self.log_to_console)
        self.scan_worker.scan_complete.connect(self.on_scan_complete)
        self.scan_worker.start()

    def on_scan_complete(self, results):
        self.btn_scan.setEnabled(True)
        self.scanned_tracks = results
        self.file_list.clear()
        
        log_count = 0
        for item in results:
            has_log = item['render_log'] is not None
            if has_log:
                log_count += 1
                icon = "✅"
            else:
                icon = "⚠️"
            self.file_list.addItem(f"{icon} {item['name']}")
            
        self.scan_count_label.setText(f"找到 {len(results)} 首曲目 ({log_count} 有 render.log)")
        self.log_to_console("掃描完成。")
        
        # Auto-load existing analysis cache if available (重啟無縫接軌，無需重新分析)
        src = self.src_folder_input.text().strip()
        cache_file = os.path.join(src, ".shorts_analysis_cache.json") if src else None
        if cache_file and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_results = json.load(f)
                if cached_results:
                    self.analysis_results = cached_results
                    self.preview_text.clear()
                    for name, data in cached_results.items():
                        self.preview_text.append(f"🎵 {name}")
                        for clip in data.get("clips", []):
                            self.preview_text.append(f"  Clip {clip.get('index', 1)}: {clip.get('start', 0):.1f} - {clip.get('end', 0):.1f} ({clip.get('section', 'Clip')}, Energy: {clip.get('score', 0.5):.2f})")
                        self.preview_text.append("")
                    self.progress_bar.setValue(100)
                    self.progress_label.setText(f"已自動載入歷史分析快取 ({len(cached_results)} 首曲目，可直接匯出)")
                    self.log_to_console(f"⚡ 已自動從快取載入 {len(cached_results)} 首曲目的分析結果，您可以直接點擊「🚀 批量匯出 Shorts」！")
                    self.btn_export.setEnabled(True)
            except Exception as e:
                logger.warning(f"自動讀取快取失敗: {e}")

    def start_analysis(self):
        if not self.scanned_tracks:
            QMessageBox.warning(self, "錯誤", "請先掃描資料夾並確認有影片檔案。")
            return
            
        try:
            num_clips = int(self.clips_combo.currentText())
            clip_dur = int(self.duration_combo.currentText())
        except ValueError:
            return
            
        self.btn_scan.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_stop.setEnabled(True)
        
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在分析高潮段...")
        
        src_dir = self.src_folder_input.text().strip()
        self.analyze_worker = HighlightAnalysisWorker(self.scanned_tracks, num_clips, clip_dur, cache_dir=src_dir)
        self.analyze_worker.progress_update.connect(self.update_progress_label)
        self.analyze_worker.analysis_complete.connect(self.on_analysis_complete)
        self.analyze_worker.start()

    def update_progress_label(self, msg, pct=None):
        self.progress_label.setText(msg)
        self.log_to_console(msg)
        if pct is not None:
            self.progress_bar.setValue(pct)

    def on_analysis_complete(self, results):
        self.btn_scan.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        self.analysis_results = results
        self.preview_text.clear()
        
        for name, data in results.items():
            self.preview_text.append(f"🎵 {name}")
            for clip in data["clips"]:
                self.preview_text.append(f"  Clip {clip['index']}: {clip['start']:.1f} - {clip['end']:.1f} ({clip['section']}, Energy: {clip['score']:.2f})")
            self.preview_text.append("")
            
        self.progress_bar.setValue(100)
        self.progress_label.setText("分析完成。")

    def start_export(self):
        if not self.analysis_results:
            QMessageBox.warning(self, "錯誤", "請先進行 AI 分析。")
            return
            
        out_dir = self.out_folder_input.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "錯誤", "請指定輸出資料夾。")
            return
            
        self.btn_scan.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_stop.setEnabled(True)
        
        self.progress_bar.setValue(0)
        self.progress_label.setText("開始匯出...")
        self.log_to_console("開始批次匯出 Shorts...")
        
        self.export_worker = ShortsExportWorker(self.analysis_results, out_dir)
        self.export_worker.progress_update.connect(self.update_export_progress)
        self.export_worker.single_clip_done.connect(lambda name: self.log_to_console(f"成功匯出: {name}"))
        self.export_worker.export_complete.connect(self.on_export_complete)
        self.export_worker.start()

    def update_export_progress(self, msg, pct):
        self.progress_label.setText(msg)
        self.progress_bar.setValue(pct)
        if "已存在跳過" in msg or "正在匯出" in msg or "完成" in msg or "中止" in msg:
            self.log_to_console(msg)

    def on_export_complete(self, success):
        self.btn_scan.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "完成", "批次匯出 Shorts 完成！")
            self.progress_label.setText("全部匯出完成")
            self.progress_bar.setValue(100)

    def stop_all(self):
        if self.analyze_worker and self.analyze_worker.isRunning():
            self.analyze_worker.stop()
            self.analyze_worker.wait(3000)
            if self.analyze_worker.isRunning():
                self.analyze_worker.terminate()
            
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.stop()
            self.export_worker.wait(3000)
            if self.export_worker.isRunning():
                self.export_worker.terminate()
            
        self.btn_scan.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        self.log_to_console("🛑 操作已由使用者中止（已儲存斷點進度，下次重啟/點擊將自動續傳）。")
        self.progress_label.setText("已中止（進度已保存）")
