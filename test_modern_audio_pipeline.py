import os
import sys
import tempfile
import numpy as np
import soundfile as sf
import librosa

from audio_analyzer import (
    oklab_to_srgb,
    AdvancedProceduralPalette,
    BallisticFilter,
    HarmonicChordAnalyzer,
    AudioBeatDetector,
    LiveAudioBeatDetector,
    AudioAnalyzer
)
from audio_stem_separator import AudioStemSeparator


def test_oklab_color():
    print("--- [測試 1: Oklab 感知色彩空間] ---")
    r, g, b = oklab_to_srgb(0.7, 0.1, 0.1)
    assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
    print(f"  ✅ Oklab (0.7, 0.1, 0.1) -> sRGB ({r}, {g}, {b})")

    palette = AdvancedProceduralPalette("cyber_test_seed")
    hue, sat, hex_c = palette.get_color(0, 'major')
    assert hex_c.startswith("#") and len(hex_c) == 7
    print(f"  ✅ 調色盤樣式: {palette.style} | 根音 C 色彩: {hex_c} (Hue: {hue:.1f}°, Sat: {sat:.2f})")


def test_ballistic_filter():
    print("\n--- [測試 2: BallisticFilter 非對稱動態衰減] ---")
    filt = BallisticFilter(attack_ms=10.0, release_ms=200.0, fps=60.0)
    # 起音測試 (0 -> 1)
    attack_val = filt.process(1.0)
    # 釋音測試 (1 -> 0)
    release_filt = BallisticFilter(attack_ms=10.0, release_ms=200.0, fps=60.0)
    release_filt.state = 1.0
    decay_val = release_filt.process(0.0)
    
    # 檢查起音速度遠快於釋音速度 (Attack 階躍響應比率高於 Decay 殘留)
    attack_delta = attack_val - 0.0
    decay_delta = 1.0 - decay_val
    print(f"  ✅ 1 幀響應 - 起音變化量: {attack_delta:.4f} vs 釋音變化量: {decay_delta:.4f}")
    assert attack_delta > decay_delta, "起音響應速度必須快於釋音釋放速度"


def test_chord_analyzer():
    print("\n--- [測試 3: CQT 諧波和弦引擎] ---")
    analyzer = HarmonicChordAnalyzer()
    sr = 22050
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    
    # 合成 C Major (C4=261.63Hz, E4=329.63Hz, G4=392.00Hz)
    y_c_maj = (np.sin(2 * np.pi * 261.63 * t) +
               np.sin(2 * np.pi * 329.63 * t) +
               np.sin(2 * np.pi * 392.00 * t)).astype(np.float32)
    
    chords, qualities = analyzer.analyze(y_c_maj, sr=sr, hop_length=1024)
    print(f"  ✅ 合成 C Major 辨識結果前 3 幀: {chords[:3]}, 性質: {qualities[:3]}")
    assert "C" in chords[0] or "C" in chords[1], f"和弦辨識預期含 C，得到: {chords[:3]}"


def test_audio_beat_detector_pipeline():
    print("\n--- [測試 4: 離線音訊分析完整管線 & 相容性] ---")
    sr = 44100
    duration = 12.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    
    # 合成具有結構段落的音訊 (前半段安靜 Intro，後半段高能 Drop)
    y = np.zeros(len(t), dtype=np.float32)
    # Intro 部分: 440Hz 長音
    y[:int(6.0 * sr)] = 0.2 * np.sin(2 * np.pi * 440.0 * t[:int(6.0 * sr)])
    # Drop 部分: 130 BPM Kick 衝擊
    for beat_t in np.arange(6.0, duration, 60.0 / 130.0):
        idx = int(beat_t * sr)
        k_len = int(0.15 * sr)
        if idx + k_len < len(y):
            kt = np.linspace(0, 0.15, k_len, endpoint=False)
            kick = np.sin(2 * np.pi * np.linspace(150, 40, k_len) * kt) * np.exp(-kt * 20.0)
            y[idx:idx+k_len] += kick * 0.9

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_wav = f.name
    try:
        sf.write(temp_wav, y, sr)
        detector = AudioBeatDetector()
        res = detector.analyze(temp_wav, genre='Auto (自動偵測)')
        
        # 1. 驗證頂層鍵
        for key in ['duration', 'bpm', 'beat_timestamps', 'filter_dynamics', 'spectrum', 'storyboard', 'genre']:
            assert key in res, f"缺少頂層鍵: {key}"
            
        # 2. 驗證 filter_dynamics 相容鍵
        fd = res['filter_dynamics']
        expected_fd_keys = [
            'times', 'sub_bass_ratio', 'bass_ratio', 'mid_ratio', 'high_ratio',
            'bass_energy', 'mid_energy', 'high_energy', 'total_energy',
            'percussive', 'harmonic', 'silence_fade', 'roughness', 'ethereal_index',
            'centroid_norm', 'stereo_width', 'chord_name', 'chord_hue', 'chord_saturation',
            'chord_brightness', 'chord_color_hex', 'palette_style', 'palette_base_hue', 'acoustic_meta'
        ]
        for fd_k in expected_fd_keys:
            assert fd_k in fd, f"filter_dynamics 缺少相容鍵: {fd_k}"
            
        print(f"  ✅ filter_dynamics 包含全部 {len(expected_fd_keys)} 個管線所需鍵名！")
        print(f"  ✅ 頻譜 64-bin 矩陣形狀: {len(res['spectrum'])} x {len(res['spectrum'][0])}")
        print(f"  ✅ SSM 結構分鏡段落數: {len(res['storyboard'])}")
        for sec in res['storyboard']:
            print(f"     - [{sec['start']}s - {sec['end']}s] {sec['section']} | Arousal: {sec['arousal']} | Hint: {sec['style_hint']}")
            assert sec['section'] in ['Intro', 'Build-up', 'Drop', 'Verse', 'Bridge', 'Outro']
            
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def test_stem_separator():
    print("\n--- [測試 5: 4-Stem 音軌分離模組] ---")
    separator = AudioStemSeparator()
    sr = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y_test = (0.5 * np.sin(2 * np.pi * 60.0 * t) + 0.3 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)
    
    stems = separator.separate(y_test, sr=sr)
    for stem_name in ['drums', 'bass', 'vocals', 'other']:
        assert stem_name in stems
        assert 'waveform' in stems[stem_name]
        assert 'envelope' in stems[stem_name]
        print(f"  ✅ 軌道 [{stem_name}]: 包絡點數 {len(stems[stem_name]['envelope'])}, 峰值 {np.max(stems[stem_name]['envelope']):.2f}")


def test_live_detector():
    print("\n--- [測試 6: LiveAudioBeatDetector 即時監聽狀態] ---")
    live = LiveAudioBeatDetector(sample_rate=44100, block_size=1024)
    status = live.get_filter_status()
    for k in ['sub_bass', 'bass', 'mid', 'high', 'is_silent', 'chord_name', 'chord_hue', 'chord_color_hex']:
        assert k in status, f"即時監聽缺少狀態鍵: {k}"
    print(f"  ✅ 即時監聽初始狀態正常: {status}")


def test_audio_analyzer_wrapper():
    print("\n--- [測試 7: VirtualAudioDeck 相容 AudioAnalyzer 封裝] ---")
    sr = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        sf.write(tmp_path, y, sr)
        deck_analyzer = AudioAnalyzer(tmp_path)
        res = deck_analyzer.analyze_full()
        assert deck_analyzer.duration > 0
        assert len(deck_analyzer.y) > 0
        print(f"  ✅ AudioAnalyzer 封裝相容性通過: 時長 {deck_analyzer.duration:.2f}s, 波形樣本數: {len(deck_analyzer.y)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    test_oklab_color()
    test_ballistic_filter()
    test_chord_analyzer()
    test_audio_beat_detector_pipeline()
    test_stem_separator()
    test_live_detector()
    test_audio_analyzer_wrapper()
    print("\n============================================================")
    print("🎉 現代音訊分析與音畫互動管線全單元測試 100% 通過！")
    print("============================================================")
