import os
import sys
import tempfile
import numpy as np
import soundfile as sf
import librosa

from audio_analyzer import AudioBeatDetector
from audio_fingerprint_engine import AudioFingerprintEngine, GENRE_REGISTRY

def create_synthetic_track(genre_type: str, duration: float = 12.0, sr: int = 22050) -> str:
    """ 根據風格特性合成特徵鮮明之音訊測試樣本 """
    n_samples = int(duration * sr)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    y = np.zeros(n_samples, dtype=np.float32)

    if genre_type == "ambient":
        # 空靈長音 Pad，無打擊樂，豐富低頻泛音
        for freq in [110.0, 165.0, 220.0, 330.0]:
            y += 0.2 * np.sin(2 * np.pi * freq * t + 0.5 * np.sin(2 * np.pi * 0.2 * t))
        envelope = np.sin(np.pi * t / duration)
        y *= envelope

    elif genre_type == "techno":
        # 132 BPM 四四拍重低音 Kick (每 0.4545 秒一次沖擊)
        bpm = 132.0
        beat_interval = 60.0 / bpm
        for beat_t in np.arange(0, duration, beat_interval):
            start_idx = int(beat_t * sr)
            kick_len = int(0.18 * sr)
            if start_idx + kick_len < n_samples:
                kt = np.linspace(0, 0.18, kick_len, endpoint=False)
                k_freq = np.linspace(120, 45, kick_len)
                kick = np.sin(2 * np.pi * k_freq * kt) * np.exp(-kt * 18.0)
                y[start_idx:start_idx+kick_len] += kick * 0.8
        y += 0.15 * np.sin(2 * np.pi * 65.0 * t)

    elif genre_type == "dnb":
        # 174 BPM 高速碎拍
        bpm = 174.0
        beat_interval = 60.0 / bpm
        for i, beat_t in enumerate(np.arange(0, duration, beat_interval)):
            start_idx = int(beat_t * sr)
            hit_len = int(0.12 * sr)
            if start_idx + hit_len < n_samples:
                ht = np.linspace(0, 0.12, hit_len, endpoint=False)
                if i % 2 == 0:
                    hit = np.sin(2 * np.pi * 140 * ht * np.exp(-ht*25)) * np.exp(-ht*15)
                else:
                    hit = (np.random.randn(hit_len) * 0.4 + np.sin(2 * np.pi * 200 * ht) * 0.6) * np.exp(-ht*20)
                y[start_idx:start_idx+hit_len] += hit * 0.7
        y += 0.2 * np.sin(2 * np.pi * 55.0 * t + 0.3 * np.sin(2 * np.pi * 4.0 * t))

    elif genre_type == "lo-fi":
        # 78 BPM 爵士和弦 + 輕微白噪音
        bpm = 78.0
        beat_interval = 60.0 / bpm
        for chord_freqs in [[130.81, 164.81, 196.00, 246.94], [116.54, 146.83, 174.61, 220.00]]:
            for f in chord_freqs:
                y += 0.08 * np.sin(2 * np.pi * f * t)
        for beat_t in np.arange(0, duration, beat_interval):
            start_idx = int(beat_t * sr)
            hit_len = int(0.15 * sr)
            if start_idx + hit_len < n_samples:
                ht = np.linspace(0, 0.15, hit_len, endpoint=False)
                hit = np.sin(2 * np.pi * 80 * ht) * np.exp(-ht * 10)
                y[start_idx:start_idx+hit_len] += hit * 0.4
        y += np.random.randn(n_samples) * 0.015

    max_val = np.max(np.abs(y)) + 1e-8
    y = (y / max_val) * 0.9

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(temp_file.name, y, sr)
    temp_file.close()
    return temp_file.name

def run_tests():
    print("=" * 60)
    print("🚀 啟動 4K MV 音訊風格與情緒遙測增強驗證測試")
    print("=" * 60)

    # 1. 驗證 16 大風格本體字典
    print("\n[測試 1] 驗證 16 大風格本體庫註冊表...")
    assert len(GENRE_REGISTRY) >= 16, "風格本體庫數量不足 16 種"
    print(f"  ✅ GENRE_REGISTRY 包含 {len(GENRE_REGISTRY)} 種主流風格")
    for key, info in GENRE_REGISTRY.items():
        assert "display_name" in info and "prompts" in info and "sub_genre" in info
    print("  ✅ 所有風格皆包含 Prompt Ensembles、子流派與情感座標先驗")

    # 2. 驗證指紋分類器推論能力
    print("\n[測試 2] 驗證指紋分類器推論能力...")
    engine = AudioFingerprintEngine()
    test_vec = np.random.randn(512).astype(np.float32)
    meta = {'percussive': 0.65, 'bass_ratio': 0.45, 'total_energy': 0.8, 'harmonic': 0.3}
    res = engine.classify_genre("non_existent.wav", vector=test_vec, bpm=132.0, acoustic_meta=meta)
    print(f"  ✅ 聲學流形推論輸出: {res['primary_genre']} | 子流派: {res['sub_genre']}")
    print(f"     Valence: {res['valence']}, Arousal: {res['arousal']}, 置信度: {res['confidence']}")
    assert -1.0 <= res['valence'] <= 1.0, "Valence 超出範圍"
    assert 0.0 <= res['arousal'] <= 1.0, "Arousal 超出範圍"

    # 3. 合成多風格音訊進行真實端到端管線測試
    detector = AudioBeatDetector()
    test_cases = ["ambient", "techno", "dnb", "lo-fi"]
    
    for case in test_cases:
        print(f"\n[測試 3-{case}] 合成並分析 {case.upper()} 音訊...")
        wav_path = create_synthetic_track(case, duration=10.0)
        try:
            analysis = detector.analyze(wav_path, genre='Auto (自動偵測)')
            
            genre_name = analysis.get('genre')
            genre_key = analysis.get('genre_key')
            telemetry = analysis.get('genre_telemetry', {})
            valence = analysis.get('valence')
            arousal = analysis.get('arousal')
            storyboard = analysis.get('storyboard', [])
            
            print(f"  -> 辨識結果: {genre_name} (Key: {genre_key})")
            print(f"  -> 情緒座標: Valence={valence}, Arousal={arousal}")
            print(f"  -> 拍速: {analysis.get('bpm'):.1f} BPM, 樂段數: {len(storyboard)}")
            
            assert genre_name is not None, "風格名稱不可為空"
            assert 'primary_genre' in telemetry, "缺少 telemetry"
            assert len(storyboard) > 0, "分鏡段落不可為空"

            # 檢驗時序風格調製
            first_sec = storyboard[0]
            assert 'arousal' in first_sec, "分鏡樂段缺少 arousal 欄位"
            assert 'style_hint' in first_sec, "分鏡樂段缺少 style_hint 欄位"
            print(f"  -> 樂段[0] ({first_sec['section']}): Arousal={first_sec['arousal']}, 提示: {first_sec['style_hint']}")

            # 風格合理性檢驗
            if case == "ambient":
                assert arousal < 0.50, "Ambient 喚醒度過高"
            elif case == "techno":
                assert arousal > 0.50, "Techno 喚醒度過低"

            print(f"  ✅ {case.upper()} 樣本驗證通過！")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    # 4. 驗證向下相容之 detect_genre(bpm, filter_dynamics)
    print("\n[測試 4] 驗證舊版 API 向下相容性...")
    compat_genre = detector.detect_genre(128.0, {'percussive': [0.5]*10, 'bass_ratio': [0.4]*10})
    assert isinstance(compat_genre, str), "舊版 detect_genre 必須返回字串"
    print(f"  ✅ 舊版相容呼叫返回字串: '{compat_genre}'")

    print("\n" + "=" * 60)
    print("🎉 所有測試全數通過！樂曲風格與情緒架構運行正常且無縫相容！")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
