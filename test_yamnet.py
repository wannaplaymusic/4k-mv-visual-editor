import os
import sys
import urllib.request
import numpy as np
import librosa

# 1. 定義常數與路徑
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "yamnet.onnx")
MODEL_URL = "https://github.com/soham30rane/Deep-Multiclass-Audio-Classification/raw/main/UI/yamnet.onnx"

# YAMNet class index to target genre map
YAMNET_GENRE_MAP = {
    213: 'pop',          # Pop music
    214: 'pop',          # Hip hop music (map to pop for our storyboard compatibility)
    216: 'rock',         # Rock music
    217: 'rock',         # Heavy metal
    218: 'rock',         # Punk rock
    232: 'jazz',         # Jazz
    236: 'edm',          # Electronic music
    237: 'edm',          # House music
    238: 'techno',       # Techno
    240: 'dnb',          # Drum and bass
    242: 'edm',          # Electronic dance music
    243: 'ambient',      # Ambient music
}

GENRE_NAMES = {
    213: 'Pop music',
    214: 'Hip hop music',
    216: 'Rock music',
    217: 'Heavy metal',
    218: 'Punk rock',
    232: 'Jazz',
    236: 'Electronic music',
    237: 'House music',
    238: 'Techno',
    240: 'Drum and bass',
    242: 'Electronic dance music',
    243: 'Ambient music'
}

def download_model():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
        print(f"Created directory: {MODEL_DIR}")
    
    if not os.path.exists(MODEL_PATH):
        print(f"Downloading YAMNet ONNX model from {MODEL_URL}...")
        print("This may take a moment (approx. 15MB)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"Model downloaded successfully to {MODEL_PATH}")
    else:
        print(f"Model already exists at {MODEL_PATH}")

def run_inference(audio_path):
    # 確保 onnxruntime 可以載入
    try:
        import onnxruntime as ort
    except ImportError:
        print("Error: onnxruntime is not installed. Please run pip install onnxruntime first.")
        sys.exit(1)
        
    download_model()
    
    print(f"\nInitializing ONNX Runtime session for {MODEL_PATH}...")
    session = ort.InferenceSession(MODEL_PATH)
    
    # 獲取輸入與輸出節點名稱
    input_name = session.get_inputs()[0].name
    print(f"Input node name: {input_name}")
    print(f"Input shape: {session.get_inputs()[0].shape}")
    print(f"Output nodes: {[out.name for out in session.get_outputs()]}")
    
    # 載入 30 秒音訊並重採樣為 16kHz
    print(f"Loading 30s segment from {audio_path}...")
    try:
        # 載入第 30s 到第 60s
        y, sr = librosa.load(audio_path, sr=16000, offset=30.0, duration=30.0)
    except Exception as e:
        print(f"Failed to load with offset=30s: {e}. Trying from beginning...")
        y, sr = librosa.load(audio_path, sr=16000, duration=30.0)
        
    print(f"Loaded audio shape: {y.shape}, Sample Rate: {sr}")
    
    # YAMNet 接收 float32 一維 waveform [samples]
    waveform = y.astype(np.float32)
    
    # 執行推論
    # 官方/常見 YAMNet ONNX 通常有 3 個 outputs: scores, embeddings, log_mel
    print("Running inference...")
    outputs = session.run(None, {input_name: waveform})
    
    scores = outputs[0]  # shape (N, 521)
    print(f"Inference complete. Scores shape: {scores.shape}")
    
    # 取時間軸平均
    avg_scores = np.mean(scores, axis=0)  # shape (521,)
    
    # 印出前 10 高的類別
    top_indices = np.argsort(avg_scores)[::-1][:10]
    print("\nTop 10 AudioSet predictions:")
    for idx in top_indices:
        print(f"  Class {idx}: {avg_scores[idx]:.4f}")
        
    # 計算曲風映射
    genre_scores = {}
    for idx, mapped_genre in YAMNET_GENRE_MAP.items():
        score = avg_scores[idx]
        genre_scores[mapped_genre] = max(genre_scores.get(mapped_genre, 0.0), score)
        
    print("\nMapped Genre Scores:")
    for genre, score in sorted(genre_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {genre}: {score:.4f}")
        
    best_genre = max(genre_scores, key=genre_scores.get)
    best_score = genre_scores[best_genre]
    print(f"\nFinal AI Proposed Genre: {best_genre} (Confidence: {best_score:.4f})")

if __name__ == "__main__":
    test_file = "4AM Tollbooth.mp4"
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        
    if not os.path.exists(test_file):
        print(f"Test file {test_file} not found. Please provide an audio path.")
        sys.exit(1)
        
    run_inference(test_file)
