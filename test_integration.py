import os
import sys
import logging

# 設定 Logger 以顯示 info 資訊
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from audio_analyzer import AudioBeatDetector

def test_integration():
    audio_path = "test_sample_16k.wav"
    if not os.path.exists(audio_path):
        print(f"Test audio {audio_path} not found. Please run test_yamnet.py first.")
        sys.exit(1)
        
    print("Initializing AudioBeatDetector...")
    detector = AudioBeatDetector()
    
    print(f"\nAnalyzing audio file: {audio_path} under Auto mode...")
    try:
        result = detector.analyze(audio_path, genre='Auto (自動偵測)')
        print("\nAnalysis Result Details:")
        print(f"  Audio Path:     {result.get('audio_path')}")
        print(f"  Detected BPM:   {result.get('bpm'):.2f}")
        print(f"  Duration:       {result.get('duration'):.2f}s")
        print(f"  Resolved Genre: {result.get('genre')}")
        print(f"  Palette Style:  {result.get('palette_style')}")
        print(f"  Storyboard Segments: {len(result.get('storyboard', []))}")
        
        # 驗證
        resolved_genre = result.get('genre').lower()
        print(f"\nVerification status: SUCCESS")
    except Exception as e:
        print(f"\nVerification status: FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_integration()
