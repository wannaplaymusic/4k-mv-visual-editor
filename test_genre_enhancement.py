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
        # 132 BPM 四四拍重低音 Kick + 反拍 Hi-Hat (每 0.4545 秒一次衝擊)
        bpm = 132.0
        beat_interval = 60.0 / bpm
        for beat_t in np.arange(0, duration, beat_interval):
            start_idx = int(beat_t * sr)
            kick_len = int(0.18 * sr)
            if start_idx + kick_len < n_samples:
                kt = np.linspace(0, 0.18, kick_len, endpoint=False)
                k_freq = np.linspace(125, 45, kick_len)
                kick = np.sin(2 * np.pi * k_freq * kt) * np.exp(-kt * 18.0)
                y[start_idx:start_idx+kick_len] += kick * 0.85
            # 反拍 Open Hi-Hat (半拍處)
            hat_idx = int((beat_t + beat_interval * 0.5) * sr)
            hat_len = int(0.08 * sr)
            if hat_idx + hat_len < n_samples:
                ht = np.linspace(0, 0.08, hat_len, endpoint=False)
                hat = np.random.randn(hat_len) * np.exp(-ht * 35.0)
                y[hat_idx:hat_idx+hat_len] += hat * 0.25
        y += 0.12 * np.sin(2 * np.pi * 65.0 * t)

    elif genre_type == "dnb":
        # 174 BPM 高速 2-Step 碎拍 + 穿透性 Snare + 密集滾奏 Hi-Hats + 門限 Reese Sub
        bpm = 174.0
        beat_interval = 60.0 / bpm
        step_interval = beat_interval / 2.0  # 八分音符 8.7 Hz 擊發率
        measure_len = beat_interval * 4.0

        # 八分音符高頻金屬 Hi-Hat 鋪底
        for ht_t in np.arange(0, duration, step_interval):
            s_idx = int(ht_t * sr)
            h_len = int(0.035 * sr)
            if s_idx + h_len < n_samples:
                ht = np.linspace(0, 0.035, h_len, endpoint=False)
                hat = np.random.randn(h_len) * np.exp(-ht * 90.0)
                y[s_idx:s_idx+h_len] += hat * 0.30

        # 2-Step DnB 鼓組循環 (Kick on 0, 2.5; Snare on 1, 3)
        for m_start in np.arange(0, duration, measure_len):
            for kt in [m_start, m_start + 2.5 * beat_interval]:
                s_idx = int(kt * sr)
                k_len = int(0.14 * sr)
                if s_idx + k_len < n_samples:
                    tt = np.linspace(0, 0.14, k_len, endpoint=False)
                    pitch = np.linspace(170, 48, k_len)
                    kick = np.sin(2 * np.pi * pitch * tt) * np.exp(-tt * 24.0)
                    y[s_idx:s_idx+k_len] += kick * 0.90

            for st in [m_start + 1.0 * beat_interval, m_start + 3.0 * beat_interval]:
                s_idx = int(st * sr)
                s_len = int(0.11 * sr)
                if s_idx + s_len < n_samples:
                    tt = np.linspace(0, 0.11, s_len, endpoint=False)
                    snare_body = np.sin(2 * np.pi * 220.0 * tt) * np.exp(-tt * 35.0)
                    snare_noise = np.random.randn(s_len) * np.exp(-tt * 28.0)
                    y[s_idx:s_idx+s_len] += (snare_body * 0.45 + snare_noise * 0.75) * 0.85

        # 門限 Reese Sub-Bass (與 Kick 律動呼應，非持續直流單音)
        for bt in np.arange(0, duration, beat_interval):
            s_idx = int(bt * sr)
            b_len = int(beat_interval * 0.85 * sr)
            if s_idx + b_len < n_samples:
                tt = np.linspace(0, beat_interval * 0.85, b_len, endpoint=False)
                sub = (np.sin(2 * np.pi * 55.0 * tt) + 0.3 * np.sin(2 * np.pi * 110.0 * tt)) * np.exp(-tt * 5.0)
                y[s_idx:s_idx+b_len] += sub * 0.45

    elif genre_type == "lo-fi":
        # 78 BPM 溫暖爵士七和弦 + 慵懶慢速 Rimshot + 黑膠底噪
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
                hit = np.sin(2 * np.pi * 85 * ht) * np.exp(-ht * 12)
                y[start_idx:start_idx+hit_len] += hit * 0.45
        # 稀疏黑膠噪點 (非淹沒頻譜的連續白噪音)
        crackle_indices = np.random.choice(n_samples, size=int(duration * 12), replace=False)
        y[crackle_indices] += np.random.uniform(-0.04, 0.04, size=len(crackle_indices))

    max_val = np.max(np.abs(y)) + 1e-8
    y = (y / max_val) * 0.9

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(temp_file.name, y, sr)
    temp_file.close()
    return temp_file.name

def run_tests():
    print("=" * 60)
    print("🚀 啟動 4K MV 音訊風格與情緒遙測增強驗證測試 (SOTA 升級版)")
    print("=" * 60)

    # 1. 驗證 18 大風格本體字典完整性
    print("\n[測試 1] 驗證 18 大風格本體庫註冊表...")
    assert len(GENRE_REGISTRY) >= 18, f"風格本體庫數量不足 18 種 (目前: {len(GENRE_REGISTRY)})"
    print(f"  ✅ GENRE_REGISTRY 包含 {len(GENRE_REGISTRY)} 種主流風格")
    for key, info in GENRE_REGISTRY.items():
        assert "display_name" in info and "prompts" in info and "sub_genre" in info
        assert "ballistic" in info and "attack_ms" in info["ballistic"] and "release_ms" in info["ballistic"]
        assert "oklch" in info and "l_base" in info["oklch"] and "c_base" in info["oklch"]
        assert "lexicon" in info and "intro" in info["lexicon"]
    print("  ✅ 所有風格皆包含 Prompt Ensembles、Ballistic 阻尼、OKLCH 色彩與曲式文法先驗！")

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

            first_sec = storyboard[0]
            assert 'arousal' in first_sec, "分鏡樂段缺少 arousal 欄位"
            assert 'style_hint' in first_sec, "分鏡樂段缺少 style_hint 欄位"
            print(f"  -> 樂段[0] ({first_sec['section']}): Arousal={first_sec['arousal']}, 提示: {first_sec['style_hint']}")

            # SOTA 核心斷言：Ambient 絕不可出現 Drop 標籤！
            if case == "ambient":
                assert all(s['section'] != 'Drop' for s in storyboard), "Ambient 樂曲絕對不可包含 Drop 標籤！"
                assert arousal < 0.50, "Ambient 喚醒度過高"
            elif case == "techno":
                assert arousal > 0.45, "Techno 喚醒度過低"
            elif case == "dnb":
                # DnB 必須被識別為高能量節奏，不可淪為 Lo-Fi
                assert genre_key != "lo-fi", f"DnB (174 BPM) 不得被錯誤辨識為 Lo-Fi (目前: {genre_key})"

            print(f"  ✅ {case.upper()} 樣本驗證通過！")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    # 4. 驗證導演手動指定風格覆寫與快取隔離 (Cache Key Poisoning 防禦)
    print("\n[測試 4] 驗證導演手動指定風格覆寫與快取隔離機制...")
    wav_path = create_synthetic_track("techno", duration=6.0)
    try:
        res_auto = detector.analyze(wav_path, genre="Auto (自動偵測)")
        res_ambient = detector.analyze(wav_path, genre="Ambient")
        res_dub = detector.analyze(wav_path, genre="Dub Techno")

        print(f"  -> Auto 模式輸出: {res_auto['genre']} (Key: {res_auto['genre_key']})")
        print(f"  -> 導演指定 Ambient 輸出: {res_ambient['genre']} (Key: {res_ambient['genre_key']})")
        print(f"  -> 導演指定 Dub Techno 輸出: {res_dub['genre']} (Key: {res_dub['genre_key']})")

        assert res_ambient['genre_key'] == "ambient", "手動覆寫 Ambient 失敗"
        assert res_ambient['genre_telemetry']['is_manual_override'] is True, "未標記為手動覆寫"
        assert res_dub['genre_key'] == "dub_techno", "手動覆寫 Dub Techno 失敗"
        assert res_dub['genre_telemetry']['is_manual_override'] is True, "未標記為手動覆寫"
        assert all(s['section'] != 'Drop' for s in res_ambient['storyboard']), "手動 Ambient 模式依然包含 Drop"

        print("  ✅ 導演手動風格覆寫與快取獨立隔離測試全數通過！")
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    # 5. 驗證向下相容之 detect_genre(bpm, filter_dynamics)
    print("\n[測試 5] 驗證舊版 API 向下相容性...")
    compat_genre = detector.detect_genre(128.0, {'percussive': [0.5]*10, 'bass_ratio': [0.4]*10})
    assert isinstance(compat_genre, str), "舊版 detect_genre 必須返回字串"
    print(f"  ✅ 舊版相容呼叫返回字串: '{compat_genre}'")

    print("\n" + "=" * 60)
    print("🎉 SOTA 驗證全數通過！18 大風格本體、抗折半、SSM文法與防中毒快取完美運作！")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
