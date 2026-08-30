import os
import hashlib
import logging
import numpy as np
from typing import Optional, List, Union

logger = logging.getLogger("StandaloneInjector.AudioFingerprint")

try:
    import torch
    import laion_clap
    HAS_CLAP = True
except ImportError:
    HAS_CLAP = False
    logger.warning("laion_clap or torch not available, heuristic acoustic embedding will be used.")

try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False
    logger.warning("umap-learn not available, fallback linear projection manifold will be used.")

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False


class AudioFingerprintEngine:
    """
    音訊語意指紋與 3D 拓撲流形映射引擎
    - 支援 LAION-CLAP 512 維度音訊語意提取 (HTSAT-unfused)
    - 支援 Librosa 物理聲學統計特徵 Heuristic Fallback
    - 內建 .npz 特徵快取機制，避免批次重複計算
    - 支援 UMAP 3D 空間降維，輸出正規化 DNA 座標與 Track Seed
    """
    def __init__(self, cache_dir: Optional[str] = None):
        self.device = "cuda" if (HAS_CLAP and torch.cuda.is_available()) else (
            "mps" if (HAS_CLAP and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()) else "cpu"
        )
        self.model = None
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        if HAS_CLAP:
            try:
                self.model = laion_clap.CLAP_Module(enable_fusion=False, amlib='htsat')
                self.model.load_ckpt()
                self.model.eval().to(self.device)
                logger.info(f"✅ CLAP 模型加載成功，運算設備: {self.device}")
            except Exception as e:
                logger.warning(f"CLAP 初始化失敗 ({e})，將採用聲學統計特徵模式。")
                self.model = None

        if HAS_UMAP:
            self.reducer = umap.UMAP(n_components=3, n_neighbors=15, min_dist=0.1, metric='cosine', random_state=42)
        else:
            self.reducer = None

        self._is_reducer_fitted = False

    def _get_cache_path(self, audio_path: str) -> str:
        mtime = os.path.getmtime(audio_path) if os.path.exists(audio_path) else 0
        audio_id = hashlib.md5(f"{audio_path}_{mtime}".encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"clap_emb_{audio_id}.npz")

    def _extract_acoustic_heuristics(self, audio_path: str) -> np.ndarray:
        """ 當缺乏神經網路 CLAP 時，使用 Librosa 提取真實物理聲學統計特徵 (512D) """
        vec = np.zeros(512, dtype=np.float32)
        if not HAS_LIBROSA or not os.path.exists(audio_path):
            return vec

        try:
            y, sr = librosa.load(audio_path, sr=22050, duration=90)  # 採樣前 90 秒
            
            # 1. MFCC (1-40) 均值與變異數 -> 80 維
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40)
            mfcc_mean = np.mean(mfcc, axis=1)
            mfcc_std = np.std(mfcc, axis=1)
            
            # 2. Chroma STFT 統計 -> 24 維
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            chroma_std = np.std(chroma, axis=1)
            
            # 3. Spectral Contrast -> 14 維
            contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
            contrast_mean = np.mean(contrast, axis=1)
            contrast_std = np.std(contrast, axis=1)
            
            # 4. Tonnetz (和聲特徵) -> 12 維
            tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
            tonnetz_mean = np.mean(tonnetz, axis=1)
            tonnetz_std = np.std(tonnetz, axis=1)
            
            # 5. 節奏與頻譜包絡
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
            spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
            spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
            zcr = np.mean(librosa.feature.zero_crossing_rate(y=y))
            
            # 拼接主要物理特徵
            features = np.concatenate([
                mfcc_mean, mfcc_std,
                chroma_mean, chroma_std,
                contrast_mean, contrast_std,
                tonnetz_mean, tonnetz_std,
                [spectral_centroid, spectral_bandwidth, spectral_rolloff, zcr]
            ]).astype(np.float32)
            
            l = min(len(features), 512)
            vec[:l] = features[:l]
            
            # 透過正弦頻率基底擴展填充剩餘維度以維持 512D 稠密流形
            if l < 512:
                t = np.linspace(0, 4 * np.pi, 512 - l)
                vec[l:] = np.sin(t * (np.sum(features) % 10.0 + 1.0)) * 0.1
                
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec /= norm
        except Exception as e:
            logger.warning(f"聲學特徵提取異常: {e}")

        return vec

    def extract_clap_vector(self, audio_path: str) -> np.ndarray:
        """
        提取 512 維 CLAP 音訊語意向量（優先命中本機快取）
        """
        if not os.path.exists(audio_path):
            return np.zeros(512, dtype=np.float32)

        cache_file = self._get_cache_path(audio_path)
        if os.path.exists(cache_file):
            try:
                data = np.load(cache_file)
                return data['vector']
            except Exception:
                pass

        vector = None
        if self.model is not None:
            try:
                with torch.no_grad():
                    embed = self.model.get_audio_embedding_from_filelist(x=[audio_path], use_tensor=False)
                    vector = embed[0].astype(np.float32)
            except Exception as e:
                logger.warning(f"CLAP 推論失敗 ({e})，切換至聲學特徵 fallback。")

        if vector is None:
            vector = self._extract_acoustic_heuristics(audio_path)

        # 寫入 .npz 快取
        try:
            np.savez_compressed(cache_file, vector=vector)
        except Exception:
            pass

        return vector

    def fit_and_project_batch(self, clap_vectors: np.ndarray) -> np.ndarray:
        """
        對曲目向量矩陣進行 UMAP 3D 拓撲映射，輸出 [0.0, 1.0] 的 3D DNA 座標
        """
        if clap_vectors.ndim == 1:
            clap_vectors = clap_vectors.reshape(1, -1)

        n_samples = clap_vectors.shape[0]
        if HAS_UMAP and self.reducer is not None and n_samples >= 4:
            if hasattr(self.reducer, 'n_neighbors') and self.reducer.n_neighbors >= n_samples:
                self.reducer.n_neighbors = max(2, n_samples - 1)
            dna_coords = self.reducer.fit_transform(clap_vectors)
            self._is_reducer_fitted = True
        elif HAS_UMAP and self.reducer is not None and self._is_reducer_fitted:
            dna_coords = self.reducer.transform(clap_vectors)
        else:
            # 偽 3D 流形投影 (Deterministic Linear Projection)
            proj_matrix = np.sin(np.arange(clap_vectors.shape[1] * 3).reshape(clap_vectors.shape[1], 3) * 0.12)
            dna_coords = np.dot(clap_vectors, proj_matrix)

        dna_min = np.min(dna_coords, axis=0)
        dna_max = np.max(dna_coords, axis=0)
        range_val = dna_max - dna_min
        range_val[range_val < 1e-8] = 1.0
        normalized_dna = np.clip((dna_coords - dna_min) / range_val, 0.0, 1.0)
        return normalized_dna

    def generate_track_seed(self, audio_path: str, dna_coord: np.ndarray) -> int:
        """
        根據音訊頭部數據與 3D DNA 座標生成確定性 32-bit 隨機種子 (供 p5.js / WebGL 使用)
        """
        header_hash = "00000000"
        if os.path.exists(audio_path):
            try:
                with open(audio_path, "rb") as f:
                    header = f.read(1024 * 64)
                header_hash = hashlib.sha256(header).hexdigest()
            except Exception:
                pass
                
        coord_str = f"{dna_coord[0]:.5f}_{dna_coord[1]:.5f}_{dna_coord[2]:.5f}"
        final_hash = hashlib.sha256(f"{header_hash}_{coord_str}".encode('utf-8')).hexdigest()
        return int(final_hash[:8], 16)
