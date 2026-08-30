import os
import sys
import gc
import time

# Disable web security & Chromium sandbox for QtWebEngine on macOS to prevent Mach port rendezvous crashes
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-web-security --enable-gpu --ignore-gpu-blocklist --enable-webgl --enable-accelerated-2d-canvas --disable-gpu-vsync --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling"
import json
import shutil
import logging
import subprocess
import re
import datetime
import base64
import io
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QCheckBox, QLabel, QSplitter, QTextEdit,
    QSlider, QComboBox, QListWidget, QListWidgetItem, QFileDialog,
    QProgressBar, QTabWidget, QMessageBox, QListView, QDialog,
    QGraphicsDropShadowEffect, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QSize, QRect, QTimer, QEventLoop, QUrl, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QTextCursor, QPixmap, QImage, QPainter, QPen, QFontMetrics, QPalette
from PIL import Image

from llm_director import LLMDirectorAgent
from ai_incubator_tab import AIIncubatorTab
from pixel_generator_tab import PixelModuleGeneratorTab
from shorts_exporter_tab import ShortsExporterTab

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("StandaloneInjector")

class AIStatusWorker(QThread):
    status_updated = pyqtSignal(dict)

    def run(self):
        try:
            from ai_engine_config import load_ai_config
            cfg = load_ai_config()
            gen_prov = cfg.get("provider", "kimi")
            
            agent = LLMDirectorAgent(model_name=cfg.get("director_model", "llama3"))
            status_info = agent.get_ollama_status()
            
            # Format hybrid status string
            prov_names = {
                "kimi": "🌙 Kimi",
                "deepseek_cloud": "🔮 DeepSeek",
                "ollama": "🚀 Ollama",
                "openai": "🌐 OpenAI"
            }
            gen_name = prov_names.get(gen_prov, gen_prov)
            if status_info.get("status") == "ready":
                status_info["message"] = f"導播: {status_info.get('model', 'llama3')} | 生成: {gen_name}"
            self.status_updated.emit(status_info)
        except Exception as e:
            self.status_updated.emit({
                "status": "offline",
                "message": f"AI 檢測異常 ({e})",
                "model": "llama3"
            })


# ----------------------------------------------------
# 🎬 AI 導演通告單可視化組件 (Director Call Sheet Panel)
# ----------------------------------------------------
class AIDirectorCallSheetWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            AIDirectorCallSheetWidget {
                background-color: #121216;
                border: 1px solid #3b0764;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 頂部標題與狀態
        header = QHBoxLayout()
        self.lbl_title = QLabel("🎬 AI 導演劇本：尚未排片 (點擊下方「AI 導演智能排片」生成)", self)
        self.lbl_title.setStyleSheet("font-weight: bold; color: #c084fc; font-size: 13px;")
        self.lbl_palette = QLabel("", self)
        self.lbl_palette.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_palette)
        layout.addLayout(header)

        # 導演構思理念
        self.lbl_statement = QLabel("", self)
        self.lbl_statement.setWordWrap(True)
        self.lbl_statement.setStyleSheet("color: #a1a1aa; font-style: italic; font-size: 11px;")
        layout.addWidget(self.lbl_statement)

        # 分鏡時間軸清單
        self.shots_list = QListWidget(self)
        self.shots_list.setFixedHeight(120)
        self.shots_list.setStyleSheet("""
            QListWidget {
                background-color: #09090b;
                border: 1px solid #27272a;
                border-radius: 6px;
                color: #e4e4e7;
                font-size: 11px;
            }
            QListWidget::item { padding: 4px; border-bottom: 1px solid #18181b; }
        """)
        layout.addWidget(self.shots_list)

    def update_call_sheet(self, script_data: dict, storyboard: list):
        """更新 AI 導演的排片內容到介面上"""
        theme = script_data.get("theme_title", "未命名主題")
        palette = script_data.get("color_palette_mood", "")
        statement = script_data.get("director_statement", "")
        
        self.lbl_title.setText(f"🎬 AI 導演美學世界觀：{theme}")
        self.lbl_palette.setText(f"🎨 色彩氛圍：{palette}" if palette else "")
        self.lbl_statement.setText(f"💡 導演理念：\"{statement}\"" if statement else "")
        
        self.shots_list.clear()
        shots = script_data.get("shot_list", [])
        
        for idx, shot in enumerate(shots):
            sec_time_str = ""
            if idx < len(storyboard):
                s = storyboard[idx]
                sec_time_str = f"[{s.get('start', 0):.1f}s - {s.get('end', 0):.1f}s] "
                
            sec_name = shot.get("section_name", f"Shot {idx+1}")
            mod_id = shot.get("assigned_module_id", "Unknown")
            framing = shot.get("framing_mode", "fill")
            fx_val = int(shot.get("target_fx_intensity", 0.5) * 100)
            trans = shot.get("transition_style", "luma_wipe")
            
            item_text = f"🎞️ {sec_time_str}{sec_name} ➔ 模組: {mod_id}  |  構圖: {framing.upper()}  |  轉場: {trans}  |  後製動態: {fx_val}%"
            self.shots_list.addItem(item_text)

class AIDirectorOrchestrationThread(QThread):
    script_ready = pyqtSignal(dict, dict) # script_data, analysis_data
    log_signal = pyqtSignal(str, bool)

    def __init__(self, audio_path: str, genre: str, available_modules: list, recent_keys: list):
        super().__init__()
        self.audio_path = audio_path
        self.genre = genre
        self.available_modules = available_modules
        self.recent_keys = recent_keys

    def run(self):
        try:
            self.log_signal.emit("🎵 正在深度解析音訊頻譜、BPM 與曲式結構...", False)
            from audio_analyzer import AudioBeatDetector
            detector = AudioBeatDetector()
            analysis = detector.analyze(self.audio_path, self.genre)

            self.log_signal.emit("🧠 正在喚醒本地 AI 導演大腦 (Llama3/DeepSeek) 撰寫全曲分鏡劇本...", False)
            from llm_director import LLMDirectorAgent
            agent = LLMDirectorAgent()
            script = agent.generate_director_script(analysis, self.available_modules, self.recent_keys)

            self.script_ready.emit(script, analysis)
        except Exception as e:
            self.log_signal.emit(f"❌ AI 導演排片失敗 ({e})，切換至專家回退模式...", True)
            try:
                from audio_analyzer import AudioBeatDetector
                detector = AudioBeatDetector()
                analysis = detector.analyze(self.audio_path, self.genre)
                from llm_director import LLMDirectorAgent
                agent = LLMDirectorAgent()
                script = agent._fallback_heuristic_script(analysis, self.available_modules, self.recent_keys)
                self.script_ready.emit(script, analysis)
            except Exception as e2:
                self.log_signal.emit(f"❌ 分析徹底失敗: {e2}", True)


# Global exception hook to catch uncaught PyQt slot exceptions and log them to app_debug.log
def exception_hook(exctype, value, tb):
    import traceback
    tb_list = traceback.format_exception(exctype, value, tb)
    tb_str = "".join(tb_list)
    # Log to console
    print(f"[CRITICAL EXCEPTION] {tb_str}", file=sys.stderr)
    # Log to file
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_debug.log")
        with open(log_path, "a", encoding="utf-8") as lf:
            import datetime
            lf.write(f"{datetime.datetime.now().isoformat()} - [CRITICAL EXCEPTION] {tb_str}\n")
    except:
        pass
    # Call default handler
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

# Add workspace directory to python path if not present
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from code_injector import CodeEditor, CustomWebEnginePage
from audio_analyzer import AudioBeatDetector

def get_local_base_url():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    return QUrl.fromLocalFile(os.path.join(workspace_dir, "dummy.html"))

MOCK_NATIVE_AUDIO_JS = """
// Native Web Audio API Mocking
(function() {
  const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;
  if (OriginalAudioContext && typeof OriginalAudioContext === 'function') {
    
    // Helpers to create mock nodes and params with no native prototype delegation
    function createMockNode(proto, extraProps) {
      const node = {
        _isMockNode: true,
        connect: function() { return this; },
        disconnect: function() { return this; },
        addEventListener: function() {},
        removeEventListener: function() {},
        dispatchEvent: function() { return true; },
        context: null,
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 2,
        channelCountMode: 'max',
        channelInterpretation: 'speakers'
      };

      if (extraProps) {
        Object.assign(node, extraProps);
      }

      return new Proxy(node, {
        get: function(target, prop) {
          if (prop in target) {
            return target[prop];
          }
          if (typeof prop === 'symbol' || prop === 'then' || prop === 'toJSON') {
            return undefined;
          }
          const param = createMockParam(1.0);
          target[prop] = param;
          return param;
        }
      });
    }

    function createMockParam(defaultValue) {
      const param = {
        _isMockParam: true,
        value: defaultValue !== undefined ? defaultValue : 1.0,
        defaultValue: defaultValue !== undefined ? defaultValue : 1.0,
        minValue: -3.4028234663852886e+38,
        maxValue: 3.4028234663852886e+38,
        setValueAtTime: function() { return this; },
        linearRampToValueAtTime: function() { return this; },
        exponentialRampToValueAtTime: function() { return this; },
        setTargetAtTime: function() { return this; },
        setValueCurveAtTime: function() { return this; },
        cancelScheduledValues: function() { return this; },
        cancelAndHoldAtTime: function() { return this; },
        chain: function() { return this; },
        connect: function() { return this; }
      };
      return param;
    }

    function createMockAnalyserNode() {
      const node = Object.create(Object.prototype);
      node._isMockNode = true;
      node.context = null;
      node.numberOfInputs = 1;
      node.numberOfOutputs = 1;
      node.channelCount = 2;
      node.channelCountMode = 'max';
      node.channelInterpretation = 'speakers';
      node.fftSize = 2048;
      node.frequencyBinCount = 1024;
      node.minDecibels = -90;
      node.maxDecibels = -30;
      node.smoothingTimeConstant = 0.8;
      node.connect = function() { return this; };
      node.disconnect = function() { return this; };
      node.getByteFrequencyData = function(array) {
        let lowVal = Math.round((window.audioLow || 0.5) * 255);
        let midVal = Math.round((window.audioMid || 0.5) * 255);
        let highVal = Math.round((window.audioHigh || 0.5) * 255);
        let len = array.length;
        for (let i = 0; i < len; i++) {
          if (i < len * 0.1) array[i] = lowVal;
          else if (i < len * 0.5) array[i] = midVal;
          else array[i] = highVal;
        }
      };
      node.getFloatFrequencyData = function(array) {
        let lowVal = -100 + (window.audioLow || 0.5) * 70;
        let midVal = -100 + (window.audioMid || 0.5) * 70;
        let highVal = -100 + (window.audioHigh || 0.5) * 70;
        let len = array.length;
        for (let i = 0; i < len; i++) {
          if (i < len * 0.1) array[i] = lowVal;
          else if (i < len * 0.5) array[i] = midVal;
          else array[i] = highVal;
        }
      };

      return new Proxy(node, {
        get: function(target, prop) {
          if (prop in target) {
            return target[prop];
          }
          if (typeof prop === 'symbol' || prop === 'then' || prop === 'toJSON') {
            return undefined;
          }
          const param = createMockParam(1.0);
          target[prop] = param;
          return param;
        }
      });
    }
    
    class MockAudioContext {
      constructor() {
        this._state = 'running';
        this._sampleRate = 44100;
        this._currentTime = 0;
        
        // Define mock listener as plain JS object to avoid native prototype conflicts
        const mockListener = {};
        Object.defineProperty(mockListener, 'positionX', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'positionY', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'positionZ', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'forwardX', { value: createMockParam(1), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'forwardY', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'forwardZ', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'upX', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'upY', { value: createMockParam(1), writable: true, configurable: true, enumerable: true });
        Object.defineProperty(mockListener, 'upZ', { value: createMockParam(0), writable: true, configurable: true, enumerable: true });
        
        mockListener.setPosition = function(x, y, z) {
          if (mockListener.positionX) mockListener.positionX.value = x;
          if (mockListener.positionY) mockListener.positionY.value = y;
          if (mockListener.positionZ) mockListener.positionZ.value = z;
        };
        mockListener.setOrientation = function(x, y, z, xUp, yUp, zUp) {
          if (mockListener.forwardX) mockListener.forwardX.value = x;
          if (mockListener.forwardY) mockListener.forwardY.value = y;
          if (mockListener.forwardZ) mockListener.forwardZ.value = z;
          if (mockListener.upX) mockListener.upX.value = xUp;
          if (mockListener.upY) mockListener.upY.value = yUp;
          if (mockListener.upZ) mockListener.upZ.value = zUp;
        };
        this._listener = mockListener;

        const mockDestination = createMockNode(null, {
          context: this,
          maxChannelCount: 2,
          numberOfInputs: 1,
          numberOfOutputs: 0
        });
        this._destination = mockDestination;
        
        // Define all methods as own enumerable properties in the constructor
        this.createAnalyser = () => createMockAnalyserNode();
        this.createGain = () => createMockNode(window.GainNode ? window.GainNode.prototype : null, { gain: createMockParam(1.0) });
        this.createDelay = () => createMockNode(window.DelayNode ? window.DelayNode.prototype : null, { delayTime: createMockParam(0.0) });
        this.createBiquadFilter = () => createMockNode(window.BiquadFilterNode ? window.BiquadFilterNode.prototype : null, { frequency: createMockParam(350), Q: createMockParam(1) });
        this.createDynamicsCompressor = () => createMockNode(window.DynamicsCompressorNode ? window.DynamicsCompressorNode.prototype : null, { threshold: createMockParam(-24) });
        this.createOscillator = () => createMockNode(window.OscillatorNode ? window.OscillatorNode.prototype : null, { frequency: createMockParam(440), start: function() {}, stop: function() {} });
        this.createMediaElementSource = () => createMockNode(null);
        this.createMediaStreamSource = () => createMockNode(null);
        this.createBufferSource = () => createMockNode(window.AudioBufferSourceNode ? window.AudioBufferSourceNode.prototype : null, { buffer: null, start: function() {}, stop: function() {} });
        
        this.createConvolver = () => createMockNode(window.ConvolverNode ? window.ConvolverNode.prototype : null, { buffer: null, normalize: true });
        this.createPanner = () => createMockNode(window.PannerNode ? window.PannerNode.prototype : null, { panningModel: 'equalpower', distanceModel: 'inverse' });
        this.createStereoPanner = () => createMockNode(window.StereoPannerNode ? window.StereoPannerNode.prototype : null, { pan: createMockParam(0.0) });
        this.createConstantSource = () => createMockNode(window.ConstantSourceNode ? window.ConstantSourceNode.prototype : null, { offset: createMockParam(1.0), start: function() {}, stop: function() {} });
        this.createWaveShaper = () => createMockNode(window.WaveShaperNode ? window.WaveShaperNode.prototype : null, { curve: null, oversample: 'none' });
        this.createChannelMerger = () => createMockNode(window.ChannelMergerNode ? window.ChannelMergerNode.prototype : null);
        this.createChannelSplitter = () => createMockNode(window.ChannelSplitterNode ? window.ChannelSplitterNode.prototype : null);
        
        this.createScriptProcessor = (bufferSize, numberOfInputChannels, numberOfOutputChannels) => {
          return createMockNode(window.ScriptProcessorNode ? window.ScriptProcessorNode.prototype : null, {
            bufferSize: bufferSize || 4096,
            numberOfInputs: numberOfInputChannels || 2,
            numberOfOutputs: numberOfOutputChannels || 2,
            onaudioprocess: null
          });
        };
        this.createIIRFilter = () => createMockNode(window.IIRFilterNode ? window.IIRFilterNode.prototype : null);
        this.createPeriodicWave = () => ({});
        this.suspend = () => Promise.resolve();
 
        this.createBuffer = (channels, length, sampleRate) => ({
          numberOfChannels: channels,
          length: length,
          sampleRate: sampleRate,
          duration: length / sampleRate,
          getChannelData: function() { return new Float32Array(length); }
        });
        
        this.decodeAudioData = function(audioData, successCallback, errorCallback) {
          const sampleRate = this._sampleRate || 44100;
          const dummyBuffer = this.createBuffer(1, sampleRate, sampleRate);
          if (successCallback) successCallback(dummyBuffer);
          return Promise.resolve(dummyBuffer);
        };
        this.resume = () => Promise.resolve();
        this.close = () => Promise.resolve();
        
        this.addEventListener = function() {};
        this.removeEventListener = function() {};
        this.dispatchEvent = function() { return true; };
        this.audioWorklet = {
          addModule: function() { return Promise.resolve(); }
        };
        
        return new Proxy(this, {
          get: function(target, prop) {
            if (prop in target) {
              return target[prop];
            }
            if (typeof prop === 'symbol' || prop === 'then' || prop === 'toJSON') {
              return undefined;
            }
            if (typeof prop === 'string' && (prop.startsWith('create') || prop === 'decodeAudioData')) {
              return function() {
                return createMockNode();
              };
            }
            return undefined;
          }
        });
      }
    }
 
    // No prototype connection to avoid native getter Illegal invocation conflicts
    Object.defineProperty(MockAudioContext.prototype, 'state', { get: function() { return this._state || 'running'; }, configurable: true });
    Object.defineProperty(MockAudioContext.prototype, 'sampleRate', { get: function() { return this._sampleRate || 44100; }, configurable: true });
    Object.defineProperty(MockAudioContext.prototype, 'currentTime', { get: function() { return this._currentTime || 0; }, configurable: true });
    Object.defineProperty(MockAudioContext.prototype, 'listener', { get: function() { return this._listener; }, configurable: true });
    Object.defineProperty(MockAudioContext.prototype, 'destination', { get: function() { return this._destination; }, configurable: true });

    // Override constructors to return mock instances and preserve native prototypes
    const constructors = [
      { name: 'AnalyserNode', create: () => createMockAnalyserNode() },
      { name: 'GainNode', create: () => createMockNode(window.GainNode ? window.GainNode.prototype : null, { gain: createMockParam(1.0) }) },
      { name: 'DelayNode', create: () => createMockNode(window.DelayNode ? window.DelayNode.prototype : null, { delayTime: createMockParam(0.0) }) },
      { name: 'BiquadFilterNode', create: () => createMockNode(window.BiquadFilterNode ? window.BiquadFilterNode.prototype : null, { frequency: createMockParam(350), Q: createMockParam(1) }) },
      { name: 'DynamicsCompressorNode', create: () => createMockNode(window.DynamicsCompressorNode ? window.DynamicsCompressorNode.prototype : null, { threshold: createMockParam(-24) }) },
      { name: 'OscillatorNode', create: () => createMockNode(window.OscillatorNode ? window.OscillatorNode.prototype : null, { frequency: createMockParam(440), start: function() {}, stop: function() {} }) },
      { name: 'ConvolverNode', create: () => createMockNode(window.ConvolverNode ? window.ConvolverNode.prototype : null, { buffer: null, normalize: true }) },
      { name: 'PannerNode', create: () => createMockNode(window.PannerNode ? window.PannerNode.prototype : null, { panningModel: 'equalpower', distanceModel: 'inverse' }) },
      { name: 'StereoPannerNode', create: () => createMockNode(window.StereoPannerNode ? window.StereoPannerNode.prototype : null, { pan: createMockParam(0.0) }) },
      { name: 'ConstantSourceNode', create: () => createMockNode(window.ConstantSourceNode ? window.ConstantSourceNode.prototype : null, { offset: createMockParam(1.0), start: function() {}, stop: function() {} }) },
      { name: 'WaveShaperNode', create: () => createMockNode(window.WaveShaperNode ? window.WaveShaperNode.prototype : null, { curve: null, oversample: 'none' }) }
    ];

    constructors.forEach(c => {
      window[c.name] = function() { return c.create(); };
    });

    window.AudioContext = MockAudioContext;
    window.webkitAudioContext = MockAudioContext;
    if (window.BaseAudioContext) {
      window.BaseAudioContext = MockAudioContext;
    }
    window.OfflineAudioContext = MockAudioContext;
    window.webkitOfflineAudioContext = MockAudioContext;

    // Symbol.hasInstance overrides to make mocks pass instanceof checks
    try {
      if (window.AudioParam) {
        Object.defineProperty(window.AudioParam, Symbol.hasInstance, {
          value: function(instance) { return instance && instance._isMockParam === true; },
          configurable: true
        });
      }
    } catch(e) {}
    try {
      if (window.AudioNode) {
        Object.defineProperty(window.AudioNode, Symbol.hasInstance, {
          value: function(instance) { return instance && instance._isMockNode === true; },
          configurable: true
        });
      }
    } catch(e) {}
    try {
      if (window.AudioContext) {
        Object.defineProperty(window.AudioContext, Symbol.hasInstance, {
          value: function(instance) { return instance && instance._isMockContext === true; },
          configurable: true
        });
      }
    } catch(e) {}
    try {
      if (window.BaseAudioContext) {
        Object.defineProperty(window.BaseAudioContext, Symbol.hasInstance, {
          value: function(instance) { return instance && instance._isMockContext === true; },
          configurable: true
        });
      }
    } catch(e) {}
  }
})();
"""

# p5.js v2.x backward compatibility shim — MUST be injected between p5.min.js and p5.sound/addon scripts
P5_V2_COMPAT_SHIM = """
// p5.js v2.x ← v1.x backward-compatibility bridge
// This shim restores APIs removed in p5 2.0 so legacy addon libraries (p5.sound, p5.func, etc.) can load.

// 0. 全域封鎖原生 JS 阻塞式對話框 (alert / confirm / prompt) 防止中斷渲染
if (typeof window !== 'undefined') {
  window.alert = function(msg) { console.log('[SUPPRESSED JS ALERT]', msg); };
  window.confirm = function(msg) { console.log('[SUPPRESSED JS CONFIRM]', msg); return true; };
  window.prompt = function(msg) { console.log('[SUPPRESSED JS PROMPT]', msg); return ''; };
  window.draw = window.draw || function() {};
  
  // 建立全域通用的 Virtual Audio Receiver 虛擬音訊接收物件工廠
  window.createMockSoundFile = window.createMockSoundFile || function() {
    return {
      _isMockSound: true,
      _isPlaying: false,
      play: function() { this._isPlaying = true; return this; },
      loop: function() { this._isPlaying = true; return this; },
      stop: function() { this._isPlaying = false; return this; },
      pause: function() { this._isPlaying = false; return this; },
      isPlaying: function() { return this._isPlaying !== false && window.isAudioPlaying !== false; },
      setVolume: function() { return this; },
      pan: function() { return this; },
      rate: function() { return 1.0; },
      disconnect: function() { return this; },
      connect: function() { return this; },
      onended: function() {},
      duration: function() { return window.totalAudioDuration || 180.0; },
      currentTime: function() { return (typeof window.custom_time_ms !== 'undefined' ? window.custom_time_ms / 1000 : (window.currentAudioTime || (window.frameCount ? window.frameCount / 60 : 0.0))); },
      getLevel: function() { return window.audioEnergy || window.beatEnergy || (typeof window.audioMid !== 'undefined' ? (window.audioLow + window.audioMid + window.audioHigh)/3 : 0.5); },
      getPeaks: function(n) { return new Float32Array(n || 5).fill(0); },
      buffer: { getChannelData: function() { return new Float32Array(1024).fill(0.5); }, duration: 180, sampleRate: 44100, numberOfChannels: 2 },
      isLoaded: function() { return true; },
      channels: function() { return 2; },
      sampleRate: function() { return 44100; },
      frames: function() { return 44100 * 180; },
      jump: function() {},
      setPath: function() {},
      setBuffer: function() {},
      processPeaks: function() { return Promise.resolve([]); },
      addCue: function() { return 0; },
      removeCue: function() {},
      clearCues: function() {},
      reverseBuffer: function() {},
      then: function(resolve) {
        if (resolve) setTimeout(() => resolve(this), 0);
        return this;
      }
    };
  };

  // 全域常數與全域滑鼠/畫面尺寸常數保底綁定 (防止 Legacy / Vanilla JS 模組 Uncaught ReferenceError: PI / mouseX is not defined)
  window.PI = Math.PI;
  window.TWO_PI = Math.PI * 2;
  window.HALF_PI = Math.PI / 2;
  window.QUARTER_PI = Math.PI / 4;
  window.TAU = Math.PI * 2;
  window.degrees = function(rad) { return rad * (180 / Math.PI); };
  window.radians = function(deg) { return deg * (Math.PI / 180); };

  if (typeof window.mouseX === 'undefined') {
    Object.defineProperty(window, 'mouseX', {
      get: function() {
        if (typeof window.simulatedMouseX !== 'undefined') return window.simulatedMouseX;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.activeInstances && p5.activeInstances[0]) || p5.instance);
        return (inst && typeof inst.mouseX === 'number') ? inst.mouseX : 250;
      },
      set: function(v) { window.simulatedMouseX = v; },
      configurable: true,
      enumerable: true
    });
  }
  if (typeof window.mouseY === 'undefined') {
    Object.defineProperty(window, 'mouseY', {
      get: function() {
        if (typeof window.simulatedMouseY !== 'undefined') return window.simulatedMouseY;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.activeInstances && p5.activeInstances[0]) || p5.instance);
        return (inst && typeof inst.mouseY === 'number') ? inst.mouseY : 250;
      },
      set: function(v) { window.simulatedMouseY = v; },
      configurable: true,
      enumerable: true
    });
  }
  if (typeof window.pmouseX === 'undefined') {
    Object.defineProperty(window, 'pmouseX', {
      get: function() { return (typeof window.simulatedMouseX !== 'undefined') ? window.simulatedMouseX : 250; },
      configurable: true,
      enumerable: true
    });
  }
  if (typeof window.pmouseY === 'undefined') {
    Object.defineProperty(window, 'pmouseY', {
      get: function() { return (typeof window.simulatedMouseY !== 'undefined') ? window.simulatedMouseY : 250; },
      configurable: true,
      enumerable: true
    });
  }
  if (typeof window.mouseIsPressed === 'undefined') {
    Object.defineProperty(window, 'mouseIsPressed', {
      get: function() { return false; },
      configurable: true,
      enumerable: true
    });
  }
}

// 0b. 全面封鎖與安全攔截電腦鏡頭 (Webcam / getUserMedia / createCapture)
if (typeof navigator !== 'undefined') {
  if (!navigator.mediaDevices) { navigator.mediaDevices = {}; }
  navigator.mediaDevices.getUserMedia = function() {
    return Promise.reject(new Error("Webcam hardware access is disabled in MV rendering engine"));
  };
  navigator.getUserMedia = function(constraints, success, error) {
    if (error) error(new Error("Webcam hardware access is disabled in MV rendering engine"));
  };
}

if (typeof p5 !== 'undefined') {
  // 0c. 安全 Stub p5.prototype.createCapture，回傳安全 Dummy 視訊像素物件，防止無鏡頭時崩潰或要求權限
  if (p5.prototype) {
    p5.prototype.createCapture = function(type, callback) {
      console.warn("[P5_COMPAT] createCapture called, providing mock dummy video element");
      var dummyVideo = (typeof document !== 'undefined') ? document.createElement('video') : {};
      dummyVideo.width = 640;
      dummyVideo.height = 480;
      dummyVideo.elt = dummyVideo;
      dummyVideo.play = function() {};
      dummyVideo.pause = function() {};
      dummyVideo.load = function() {};
      dummyVideo.hide = function() { return this; };
      dummyVideo.show = function() { return this; };
      dummyVideo.size = function(w, h) { this.width = w || 640; this.height = h || 480; return this; };
      dummyVideo.loadPixels = function() {
        if (!this.pixels) this.pixels = new Uint8Array(this.width * this.height * 4);
        return this;
      };
      dummyVideo.updatePixels = function() { return this; };
      dummyVideo.get = function() { return [0, 0, 0, 255]; };
      dummyVideo.pixels = new Uint8Array(640 * 480 * 4);
      if (typeof callback === 'function') {
        try { callback(dummyVideo); } catch(e) {}
      }
      return dummyVideo;
    };
  }

  // 0d. 安全相容舊版 Processing.js / Khan Academy 像素操作 (this.imageData.data & window.imageData)
  if (typeof window !== 'undefined') {
    var _origLoadPixels = p5.prototype ? p5.prototype.loadPixels : null;
    if (_origLoadPixels) {
      p5.prototype.loadPixels = function() {
        var res = _origLoadPixels.apply(this, arguments);
        var canvas = (this._renderer && this._renderer.elt) || document.querySelector('canvas');
        if (canvas) {
          try {
            var ctx = canvas.getContext('2d');
            if (ctx) {
              this.imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
              window.imageData = this.imageData;
            }
          } catch(e) {}
        }
        if (!this.imageData) {
          this.imageData = { data: this.pixels || new Uint8ClampedArray((this.width || 500) * (this.height || 500) * 4) };
          window.imageData = this.imageData;
        }
        return res;
      };
    }

    Object.defineProperty(window, 'imageData', {
      get: function() {
        var canvas = document.querySelector('canvas');
        if (canvas) {
          try {
            var ctx = canvas.getContext('2d');
            if (ctx) return ctx.getImageData(0, 0, canvas.width, canvas.height);
          } catch(e) {}
        }
        return { data: (typeof pixels !== 'undefined' && pixels) ? pixels : new Uint8ClampedArray((typeof width !== 'undefined' ? width : 500) * (typeof height !== 'undefined' ? height : 500) * 4) };
      },
      set: function(v) { this._customImageData = v; },
      configurable: true,
      enumerable: true
    });
  }

  // 1. Restore p5.prototype.registerMethod & p5.registerMethod (removed in v2.0, replaced by p5.registerAddon)
  var _registerMethodPolyfill = function(hookName, method) {
    if (typeof method !== 'function') return;
    p5.prototype._registeredMethods = p5.prototype._registeredMethods || {};
    if (!p5.prototype._registeredMethods[hookName]) {
      p5.prototype._registeredMethods[hookName] = [];
    }
    p5.prototype._registeredMethods[hookName].push(method);
  };
  if (p5.prototype && !p5.prototype.registerMethod) {
    p5.prototype._registeredMethods = p5.prototype._registeredMethods || {};
    p5.prototype.registerMethod = _registerMethodPolyfill;
  }
  if (!p5.registerMethod) {
    p5.registerMethod = _registerMethodPolyfill;
  }

  // 2. Restore p5.prototype._checkFileExtension (used by p5.sound loadSound)
  if (p5.prototype && !p5.prototype._checkFileExtension) {
    p5.prototype._checkFileExtension = function(path) {
      var ext = '';
      if (typeof path === 'string') {
        var idx = path.lastIndexOf('.');
        if (idx >= 0) ext = path.slice(idx + 1).toLowerCase();
      }
      return { ext: ext };
    };
  }
  // 3. Restore p5.prototype.registerPreloadMethod & p5.registerPreloadMethod
  var _registerPreloadPolyfill = function(methodName, prototype) {};
  if (p5.prototype && !p5.prototype.registerPreloadMethod) {
    p5.prototype.registerPreloadMethod = _registerPreloadPolyfill;
  }
  if (!p5.registerPreloadMethod) {
    p5.registerPreloadMethod = _registerPreloadPolyfill;
  }

  // 3b. Restore p5.prototype._validateParameters (removed in v2.0, required by p5.dom addon)
  if (p5.prototype && !p5.prototype._validateParameters) {
    p5.prototype._validateParameters = function() { return true; };
  }


  // 4. Make 'step' property configurable on p5.prototype to prevent "Cannot redefine property: step"
  if (p5.prototype) {
    try {
      var stepDesc = Object.getOwnPropertyDescriptor(p5.prototype, 'step');
      if (stepDesc && !stepDesc.configurable) {
        Object.defineProperty(p5.prototype, 'step', {
          value: stepDesc.value,
          writable: true,
          configurable: true,
          enumerable: stepDesc.enumerable
        });
      }
    } catch(e) {}
  }
  const skipGlobals = [
    'setup', 'draw', 'preload', 'windowResized', 'deviceMoved', 'deviceTurned', 'deviceShaken',
    'keyPressed', 'keyReleased', 'keyTyped', 'keyIsDown', 'mouseMoved', 'mouseDragged',
    'mousePressed', 'mouseReleased', 'mouseClicked', 'doubleClicked', 'mouseWheel',
    'touchStarted', 'touchMoved', 'touchEnded'
  ];
  for (var prop in p5.prototype) {
    if (typeof p5.prototype[prop] === 'function') {
      if (skipGlobals.indexOf(prop) !== -1) continue;
      (function(pName) {
        // Expose as actual configurable window property getter/setter with fallback storage
        try {
          var origPropDesc = Object.getOwnPropertyDescriptor(window, pName);
          if (origPropDesc && !origPropDesc.configurable) return;

          Object.defineProperty(window, pName, {
            get: function() {
              if (window['__' + pName] !== undefined) {
                return window['__' + pName];
              }
              var activeInst = window._p5Instance;
              if (!activeInst) {
                if (typeof p5.instance === 'object' && p5.instance) {
                  activeInst = p5.instance;
                } else if (p5.activeInstances && p5.activeInstances.length > 0) {
                  activeInst = p5.activeInstances[0];
                }
              }
              if (activeInst && typeof activeInst[pName] === 'function') {
                return activeInst[pName].bind(activeInst);
              }
              // Math & standalone utility fallbacks if called before p5 instance is initialized
              if (typeof Math[pName] === 'function') {
                return Math[pName].bind(Math);
              }
              if (pName === 'random') {
                return function(min, max) {
                  if (min === undefined) return Math.random();
                  if (max === undefined) {
                    if (Array.isArray(min)) return min[Math.floor(Math.random() * min.length)];
                    return Math.random() * min;
                  }
                  return min + Math.random() * (max - min);
                };
              }
              if (pName === 'noise') {
                return function(x, y, z) {
                  var v = Math.sin((x || 0) * 12.9898 + (y || 0) * 78.233 + (z || 0) * 37.719) * 43758.5453;
                  return v - Math.floor(v);
                };
              }
              if (pName === 'map') {
                return function(n, start1, stop1, start2, stop2) {
                  return ((n - start1) / (stop1 - start1)) * (stop2 - start2) + start2;
                };
              }
              if (pName === 'constrain') {
                return function(n, low, high) {
                  return Math.max(Math.min(n, high), low);
                };
              }
              if (pName === 'dist') {
                return function(x1, y1, x2, y2) {
                  return Math.hypot(x2 - x1, y2 - y1);
                };
              }
              if (pName === 'radians') {
                return function(deg) { return deg * (Math.PI / 180); };
              }
              if (pName === 'degrees') {
                return function(rad) { return rad * (180 / Math.PI); };
              }

              // Fallback to prototype execution if possible
              return function(...args) {
                var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
                if (inst && typeof inst[pName] === 'function') {
                  return inst[pName].apply(inst, args);
                }
              };
            },
            set: function(val) {
              window['__' + pName] = val;
              var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
              if (inst) {
                try { inst[pName] = val; } catch(e) {}
              }
            },
            configurable: true,
            enumerable: true
          });
        } catch (e) {
          // If defineProperty fails (e.g. read-only global), assign directly if writable
          try {
            window[pName] = function(...args) {
              var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
              if (inst && typeof inst[pName] === 'function') {
                return inst[pName].apply(inst, args);
              }
            };
          } catch(err) {}
        }
      })(prop);
    }
  }

  // Enforce Deterministic Seed (randomSeed & noiseSeed) for p5.js based on 32-bit Hash Seed
  if (p5.prototype && !p5.prototype._seedHooked) {
    p5.prototype._seedHooked = true;
    p5.prototype.registerMethod('pre', function() {
      if (!this._seedInitialized && typeof window.seed !== 'undefined') {
        this._seedInitialized = true;
        try {
          if (typeof this.randomSeed === 'function') this.randomSeed(window.seed);
          if (typeof this.noiseSeed === 'function') this.noiseSeed(window.seed);
        } catch(e) {
          console.warn('[SeedHook] Failed to initialize randomSeed/noiseSeed:', e);
        }
      }
    });
  }

  // Double check and ensure p5.Graphics.prototype has all drawing functions from p5.prototype.
  // In p5.js v2.x, Graphics prototype structure changed and some legacy addon modules expect all drawing methods on p5.Graphics instances.
  if (typeof p5.Graphics !== 'undefined' && p5.Graphics.prototype) {
    for (var gProp in p5.prototype) {
      if (typeof p5.prototype[gProp] === 'function' && typeof p5.Graphics.prototype[gProp] === 'undefined') {
        (function(funcName) {
          p5.Graphics.prototype[funcName] = function(...args) {
            if (this._renderer && typeof this._renderer[funcName] === 'function') {
              return this._renderer[funcName].apply(this._renderer, args);
            }
            if (p5.prototype[funcName]) {
              return p5.prototype[funcName].apply(this, args);
            }
          };
        })(gProp);
      }
    }
  }

  // Intercept createGraphics to dynamically patch any missing drawing methods on the returned graphics instance
  const origCreateGraphics = p5.prototype.createGraphics;
  if (origCreateGraphics) {
    p5.prototype.createGraphics = function(...args) {
      const g = origCreateGraphics.apply(this, args);
      if (g) {
        // Define all critical drawing methods directly on the instance to override any internal element-level null/stub placeholders
        const drawMethods = [
          'curveVertex', 'vertex', 'bezierVertex', 'quadraticVertex', 'beginShape', 'endShape',
          'stroke', 'fill', 'noStroke', 'noFill', 'background', 'ellipse', 'rect', 'line', 'point',
          'push', 'pop', 'translate', 'rotate', 'scale', 'angleMode', 'colorMode', 'rectMode', 'imageMode',
          'arc', 'triangle', 'quad', 'circle', 'square', 'bezier', 'curve',
          'erase', 'noErase', 'blendMode', 'tint', 'noTint', 'smooth', 'noSmooth',
          'strokeWeight', 'strokeCap', 'strokeJoin', 'ellipseMode',
          'textSize', 'textFont', 'textAlign', 'textStyle', 'text',
          'applyMatrix', 'resetMatrix', 'shearX', 'shearY',
          'image', 'copy', 'get', 'set', 'loadPixels', 'updatePixels',
          'color', 'lerpColor', 'red', 'green', 'blue', 'alpha', 'hue', 'saturation', 'brightness',
          'clear', 'filter'
        ];
        drawMethods.forEach(function(funcName) {
          if (typeof g[funcName] === 'function') return; // already a real function, skip
          g[funcName] = function(...fArgs) {
            if (g._renderer && typeof g._renderer[funcName] === 'function') {
              return g._renderer[funcName].apply(g._renderer, fArgs);
            }
            if (p5.prototype[funcName]) {
              return p5.prototype[funcName].apply(g, fArgs);
            }
          };
        });
        // Add legacy PGraphics method stubs (beginDraw / endDraw)
        g.beginDraw = g.beginDraw || function() { return this; };
        g.endDraw = g.endDraw || function() { return this; };

        // Ensure drawingContext is accessible on the graphics instance

        if (!g.drawingContext && g._renderer && g._renderer.drawingContext) {
          Object.defineProperty(g, 'drawingContext', {
            get: function() { return g._renderer.drawingContext; },
            configurable: true
          });
        }
      }
      return g;
    };
  }
  
  // 6. 確保 textFont 傳入未加載完成的字型、undefined 或結構不完整之字型時不發生 Uncaught TypeError 崩潰
  if (p5.prototype && p5.prototype.textFont) {
    const originalTextFont = p5.prototype.textFont;
    p5.prototype.textFont = function(font, size) {
      if (arguments.length > 0) {
        if (!font) {
          console.warn("[P5_COMPAT] textFont received undefined/null font, skipping to prevent crash");
          return this;
        }
        if (typeof font === 'object') {
          if (font.hasOwnProperty('font') && !font.font) {
            console.warn("[P5_COMPAT] textFont: p5.Font.font is not loaded yet, skipping");
            return this;
          }
          if (font.font && !font.font.data && !font.font.tables) {
            console.warn("[P5_COMPAT] textFont: opentype font data is missing, skipping");
            return this;
          }
        }
      }
      try {
        return originalTextFont.apply(this, arguments);
      } catch (e) {
        console.warn("[P5_COMPAT] Ignored textFont error:", e);
        return this;
      }
    };
  }

  // 6b. UI 雜訊與 UI 文字隱藏護欄 (非文字主導視覺模組自動隱藏輔助/狀態/操作提示文字)
  if (p5.prototype && p5.prototype.text) {
    const originalText = p5.prototype.text;
    const shouldHideText = function(str) {
      if (window.isTextVisualModule || window._isTypographyVisual) return false;
      if (str === null || str === undefined) return false;
      var s = String(str).trim();
      if (!s) return false;
      // 單一純符號標記 (長度 <= 2 且非純英數) 放行
      if (s.length <= 2 && !/^[a-zA-Z0-9]$/.test(s)) return false;
      // 非文字藝術模組時，凡包含英文字母或長度大於 2 之所有說明/狀態/除錯文字一律徹底隱藏
      if (/[a-zA-Z]/.test(s) || s.length > 2) return true;
      return false;
    };



    p5.prototype.text = function(str, x, y, x2, y2) {
      if (shouldHideText(str)) {
        return this;
      }
      try {
        return originalText.apply(this, arguments);
      } catch(e) {
        return this;
      }
    };

    // 亦於 Renderer2D / Renderer 原型進行雙重深層過濾，防止直接呼叫 renderer.text
    if (typeof p5.Renderer2D !== 'undefined' && p5.Renderer2D.prototype && p5.Renderer2D.prototype.text) {
      const origRendererText = p5.Renderer2D.prototype.text;
      p5.Renderer2D.prototype.text = function(str, x, y, x2, y2) {
        if (shouldHideText(str)) {
          return this;
        }
        try {
          return origRendererText.apply(this, arguments);
        } catch(e) {
          return this;
        }
      };
    }
  }


  
  // 7. 攔截並 Mock loadSound 以及 p5.SoundFile，防止遠端音訊加載發生 CORS 錯誤與未加載完成的 .play() 崩潰
  var createMockSoundFile = window.createMockSoundFile || function() {
    return {
      _isMockSound: true,
      _isPlaying: false,
      play: function() { this._isPlaying = true; return this; },
      loop: function() { this._isPlaying = true; return this; },
      stop: function() { this._isPlaying = false; return this; },
      pause: function() { this._isPlaying = false; return this; },
      isPlaying: function() { return this._isPlaying !== false && window.isAudioPlaying !== false; },
      setVolume: function() { return this; },
      pan: function() { return this; },
      rate: function() { return 1.0; },
      disconnect: function() { return this; },
      connect: function() { return this; },
      onended: function() {},
      duration: function() { return window.totalAudioDuration || 180.0; },
      currentTime: function() { return (typeof window.custom_time_ms !== 'undefined' ? window.custom_time_ms / 1000 : (window.currentAudioTime || (window.frameCount ? window.frameCount / 60 : 0.0))); },
      getLevel: function() { return window.audioEnergy || window.beatEnergy || (typeof window.audioMid !== 'undefined' ? (window.audioLow + window.audioMid + window.audioHigh)/3 : 0.5); },
      getPeaks: function(n) { return new Float32Array(n || 5).fill(0); },
      buffer: { getChannelData: function() { return new Float32Array(1024).fill(0.5); }, duration: 180, sampleRate: 44100, numberOfChannels: 2 },
      isLoaded: function() { return true; },
      channels: function() { return 2; },
      sampleRate: function() { return 44100; },
      frames: function() { return 44100 * 180; },
      jump: function() {},
      setPath: function() {},
      setBuffer: function() {},
      processPeaks: function() { return Promise.resolve([]); },
      addCue: function() { return 0; },
      removeCue: function() {},
      clearCues: function() {},
      reverseBuffer: function() {},
      then: function(resolve) {
        if (resolve) {
          setTimeout(() => resolve(this), 0);
        }
        return this;
      }
    };
  };
  window.createMockSoundFile = createMockSoundFile;

  if (p5.prototype) {
    p5.prototype.loadSound = function(path, successCallback, failureCallback) {
      console.log("[P5_COMPAT] loadSound hijacked for: " + path);
      const mockSound = createMockSoundFile();
      if (successCallback) {
        setTimeout(() => {
          try { successCallback(mockSound); } catch(e) {}
        }, 0);
      }
      return mockSound;
    };
  }
  const createMockSoundClass = function(name, methods = []) {
    return function() {
      console.log("[P5_COMPAT] Mock " + name + " instantiated");
      const obj = { _isMock: true };
      methods.forEach(m => {
        obj[m] = function() { return this; };
      });
      if (name === 'FFT') {
        obj.setInput = function() { return this; };
        obj.analyze = function() {
          let arr = new Array(1024).fill(0);
          let lowVal = Math.round((window.audioLow || 0.5) * 255);
          let midVal = Math.round((window.audioMid || 0.5) * 255);
          let highVal = Math.round((window.audioHigh || 0.5) * 255);
          let beatMod = (window.beatEnergy || 0.5) * 40;
          for (let i = 0; i < 100; i++) arr[i] = Math.min(255, Math.max(0, lowVal + (Math.random() * 20 - 10) + beatMod));
          for (let i = 100; i < 500; i++) arr[i] = Math.min(255, Math.max(0, midVal + (Math.random() * 15 - 7)));
          for (let i = 500; i < 1024; i++) arr[i] = Math.min(255, Math.max(0, highVal + (Math.random() * 10 - 5)));
          return arr;
        };
        obj.getEnergy = function(freq1, freq2) {
          if (typeof freq1 === 'string') {
            let f = freq1.toLowerCase();
            if (f === 'bass') return Math.round((window.audioLow || 0.5) * 255);
            if (f === 'lowmid') return Math.round(((window.audioLow + window.audioMid)/2 || 0.5) * 255);
            if (f === 'mid') return Math.round((window.audioMid || 0.5) * 255);
            if (f === 'highmid') return Math.round(((window.audioMid + window.audioHigh)/2 || 0.5) * 255);
            if (f === 'treble') return Math.round((window.audioHigh || 0.5) * 255);
          }
          let val = window.audioMid || 0.5;
          if (freq1 < 250) val = window.audioLow || 0.5;
          else if (freq1 > 2000) val = window.audioHigh || 0.5;
          return Math.round(val * 255);
        };
        obj.getLevel = function() { return window.audioEnergy || window.beatEnergy || window.audioMid || 0.5; };
      }
      if (name === 'Amplitude') {
        obj.setInput = function() { return this; };
        obj.getLevel = function() { return window.audioEnergy || window.beatEnergy || window.audioMid || 0.5; };
      }
      if (name === 'AudioIn') {
        obj.start = function() { return this; };
        obj.stop = function() { return this; };
        obj.getLevel = function() { return window.audioEnergy || window.beatEnergy || window.audioLow || 0.5; };
      }
      return obj;
    };
  };

  p5.SoundFile = function() {
    return createMockSoundFile();
  };
  p5.Oscillator = createMockSoundClass('Oscillator', ['start', 'stop', 'setType', 'freq', 'amp', 'disconnect', 'connect', 'pan', 'add', 'mult', 'scale']);
  p5.TriOsc = p5.Oscillator;
  p5.SinOsc = p5.Oscillator;
  p5.SqrOsc = p5.Oscillator;
  p5.SawOsc = p5.Oscillator;
  p5.Envelope = createMockSoundClass('Envelope', ['play', 'triggerAttack', 'triggerRelease', 'setRange', 'setADSR', 'setInput']);
  p5.FFT = createMockSoundClass('FFT');
  p5.Amplitude = createMockSoundClass('Amplitude');
  p5.AudioIn = createMockSoundClass('AudioIn');

  // 8. 攔截並 Mock loadFont，防止遠端字型加載發生 CORS 錯誤與未加載完成的 .textToPoints() 崩潰
  const createMockFont = function() {
    return {
      _isMockFont: true,
      font: { data: true, tables: {}, _font: {} },
      textToPoints: function() { return []; },
      textBounds: function(str, x, y, fontSize) {
        var len = (str && str.length) || 1;
        var sz = fontSize || 12;
        return { x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 };
      },
      getPath: function() { return { commands: [] }; },
      getOutline: function() { return []; },
      then: function(resolve) {
        if (resolve) {
          setTimeout(() => resolve(this), 0);
        }
        return this;
      }
    };
  };

  if (p5.prototype) {
    p5.prototype.loadFont = function(path, successCallback, failureCallback) {
      console.log("[P5_COMPAT] loadFont hijacked for: " + path);
      const mockFont = createMockFont();
      if (successCallback) {
        setTimeout(() => {
          try { successCallback(mockFont); } catch(e) {}
        }, 0);
      }
      return mockFont;
    };

    // 8b. 攔截並 Mock loadModel / 3D Geometry，防止 gltfModel 存取未定義崩潰
    if (!p5.prototype.loadModel) {
      p5.prototype.loadModel = function(path, normalize, successCallback, failureCallback) {
        console.log("[P5_COMPAT] loadModel hijacked for: " + path);
        const mockModel = {
          gltfModel: { scene: {}, scenes: [] },
          vertices: [],
          faces: [],
          computeNormals: function() { return this; },
          normalize: function() { return this; }
        };
        if (typeof normalize === 'function') {
          setTimeout(() => normalize(mockModel), 0);
        } else if (typeof successCallback === 'function') {
          setTimeout(() => successCallback(mockModel), 0);
        }
        return mockModel;
      };
    }
  }
  
  // 9. 補全 PVector 類別（為相容於舊版 Processing 轉譯的作品，防止全域變數宣告時 Temporal Dead Zone 崩潰）
  if (typeof window.PVector === 'undefined') {
    window.PVector = class PVector {
      constructor(x, y, z) {
        this.x = x || 0;
        this.y = y || 0;
        this.z = z || 0;
      }
      static dist(v1, v2) {
        return Math.sqrt((v1.x - v2.x) ** 2 + (v1.y - v2.y) ** 2 + (v1.z - v2.z) ** 2);
      }
      static random2D() {
        const angle = Math.random() * Math.PI * 2;
        return new PVector(Math.cos(angle), Math.sin(angle));
      }
      set(x, y, z) {
        if (x instanceof PVector) {
          this.x = x.x || 0;
          this.y = x.y || 0;
          this.z = x.z || 0;
        } else {
          this.x = x || 0;
          this.y = y || 0;
          this.z = z || 0;
        }
        return this;
      }
      copy() {
        return new PVector(this.x, this.y, this.z);
      }
      add(v) {
        if (v instanceof PVector) {
          this.x += v.x;
          this.y += v.y;
          this.z += v.z;
        } else {
          this.x += arguments[0] || 0;
          this.y += arguments[1] || 0;
          this.z += arguments[2] || 0;
        }
        return this;
      }
      sub(v) {
        if (v instanceof PVector) {
          this.x -= v.x;
          this.y -= v.y;
          this.z -= v.z;
        } else {
          this.x -= arguments[0] || 0;
          this.y -= arguments[1] || 0;
          this.z -= arguments[2] || 0;
        }
        return this;
      }
      mult(n) {
        this.x *= n;
        this.y *= n;
        this.z *= n;
        return this;
      }
      div(n) {
        this.x /= n;
        this.y /= n;
        this.z /= n;
        return this;
      }
      mag() {
        return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
      }
      normalize() {
        const m = this.mag();
        if (m !== 0 && m !== 1) {
          this.div(m);
        }
        return this;
      }
      limit(max) {
        if (this.mag() > max) {
          this.normalize();
          this.mult(max);
        }
        return this;
      }
      heading() {
        return Math.atan2(this.y, this.x);
      }
    };
  }

  // 10. 攔截 HTMLInputElement.prototype.size 的寫入，防止 p5.js createInput() 預設傳入 0 或無參數時引發 IndexSizeError 崩潰
  if (typeof HTMLInputElement !== 'undefined') {
    try {
      let originalSet = null;
      let desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'size');
      if (desc && desc.set) {
        originalSet = desc.set;
      } else {
        desc = Object.getOwnPropertyDescriptor(Element.prototype, 'size');
        if (desc && desc.set) originalSet = desc.set;
      }
      
      Object.defineProperty(HTMLInputElement.prototype, 'size', {
        get: function() {
          const val = this.getAttribute('size');
          return val !== null ? parseInt(val, 10) : 20;
        },
        set: function(val) {
          let intVal = parseInt(val, 10);
          if (isNaN(intVal) || intVal <= 0) {
            intVal = 20;
          }
          if (originalSet) {
            try {
              originalSet.call(this, intVal);
            } catch (e) {
              this.setAttribute('size', intVal);
            }
          } else {
            this.setAttribute('size', intVal);
          }
        },
        configurable: true,
        enumerable: true
      });
      console.log("[P5_COMPAT] HTMLInputElement.prototype.size override applied successfully");
    } catch (e) {
      console.warn("[P5_COMPAT] Failed to override HTMLInputElement.prototype.size:", e);
    }
  }

  // 11. 全域 chroma 攔截與自癒代理，防止 chroma(val) 拋出格式錯誤或回傳之 color 物件缺失 .css() 方法引發崩潰
  (function() {
    let internalChroma = undefined;
    
    // 定義動態包裝函數，可隨時就地執行
    window.ensureChromaWrapped = function() {
      if (typeof internalChroma === 'function' && !internalChroma._wrapped) {
        console.log("[P5_COMPAT] chroma function wrapped dynamically");
        const originalChroma = internalChroma;
        
        const wrapped = function(...args) {
          try {
            let res = originalChroma.apply(this, args);
            if (res && typeof res === 'object') {
              return wrapChromaColor(res);
            }
            return res;
          } catch (e) {
            console.warn("[P5_COMPAT] chroma invocation failed, returning mock:", e);
            return createMockChromaColor();
          }
        };
        
        Object.assign(wrapped, originalChroma);
        wrapped.prototype = originalChroma.prototype;
        wrapped._wrapped = true;
        
        // 直接賦值給 internalChroma，setter 也會同步更新
        internalChroma = wrapped;
      }
    };

    let chromaGetterActive = false;
    Object.defineProperty(window, 'chroma', {
      get: function() {
        if (!chromaGetterActive && internalChroma && typeof internalChroma === 'function' && !internalChroma._wrapped) {
          chromaGetterActive = true;
          try { window.ensureChromaWrapped(); } catch(e) {}
          chromaGetterActive = false;
        }
        return internalChroma;
      },
      set: function(val) {
        internalChroma = val;
      },
      configurable: true
    });

    // 額外 Hook setup/preload/draw，在執行任何 p5 生命週期前，二度強制包裝 chroma！
    // NOTE: 不使用 Object.defineProperty 以避免與 p5.js v2 內部的 property redefinition 衝突
    //       (此前使用 defineProperty 會導致 955 筆 "Cannot redefine property: setup" 錯誤)
    if (p5.prototype) {
      const hookP5Lifecycle = function(methodName) {
        if (typeof p5.prototype[methodName] === 'function') {
          const original = p5.prototype[methodName];
          p5.prototype[methodName] = function() {
            try { window.ensureChromaWrapped(); } catch(e) {}
            return original.apply(this, arguments);
          };
        }
        // 不再對未定義的方法使用 defineProperty getter/setter，
        // 改為在 p5 instance 建立後的 predraw hook 中確保 chroma 被包裝
      };
      
      hookP5Lifecycle('setup');
      hookP5Lifecycle('preload');
      hookP5Lifecycle('draw');
      
      // 備用：透過 registerMethod('pre') 在每次 draw 前確保 chroma 被包裝
      try {
        if (typeof p5.prototype.registerMethod === 'function') {
          p5.prototype.registerMethod('pre', function() {
            try { window.ensureChromaWrapped(); } catch(e) {}
          });
        }
      } catch(e) {}
    }

    function wrapChromaColor(colorObj) {
      if (!colorObj.css) {
        colorObj.css = function(format) {
          if (typeof colorObj.hex === 'function') return colorObj.hex();
          if (typeof colorObj.toString === 'function') return colorObj.toString();
          return "rgba(0,0,0,1)";
        };
      }
      const chainMethods = ['alpha', 'darken', 'brighten', 'saturate', 'desaturate', 'set'];
      chainMethods.forEach(method => {
        if (typeof colorObj[method] === 'function' && !colorObj[method]._wrapped) {
          const orig = colorObj[method];
          colorObj[method] = function(...args) {
            try {
              let next = orig.apply(this, args);
              if (next && typeof next === 'object') {
                return wrapChromaColor(next);
              }
              return next;
            } catch (e) {
              return colorObj;
            }
          };
          colorObj[method]._wrapped = true;
        }
      });
      return colorObj;
    }

    function createMockChromaColor() {
      return {
        _isMock: true,
        css: function() { return "rgba(0,0,0,1)"; },
        hex: function() { return "#000000"; },
        alpha: function() { return this; },
        darken: function() { return this; },
        brighten: function() { return this; },
        saturate: function() { return this; },
        desaturate: function() { return this; },
        set: function() { return this; },
        get: function() { return 0; }
      };
    }
  })();
}

// Double check and explicitly define key p5 drawing functions directly on window in case prototype enumeration missed them
(function() {
  // 12. Processing legacy matrix & style compatibility aliases (pushMatrix -> push, popMatrix -> pop)
  const legacyAliases = {
    'pushMatrix': 'push',
    'popMatrix': 'pop',
    'pushStyle': 'push',
    'popStyle': 'pop',
    'resetShader': 'resetShader'
  };
  Object.keys(legacyAliases).forEach(alias => {
    const target = legacyAliases[alias];
    if (typeof window[alias] === 'undefined') {
      window[alias] = function(...args) {
        var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
        if (inst && typeof inst[target] === 'function') {
          return inst[target].apply(inst, args);
        } else if (typeof window[target] === 'function') {
          return window[target].apply(window, args);
        }
      };
    }
    if (typeof p5 !== 'undefined' && p5.prototype && typeof p5.prototype[alias] === 'undefined') {
      p5.prototype[alias] = function(...args) {
        if (typeof this[target] === 'function') {
          return this[target].apply(this, args);
        }
      };
    }
  });

  const criticalFuncs = [
    'curveVertex', 'vertex', 'bezierVertex', 'quadraticVertex', 'beginShape', 'endShape', 'stroke', 'fill', 'noStroke', 'noFill',
    'background', 'ellipse', 'rect', 'line', 'point', 'push', 'pop', 'translate', 'rotate', 'scale', 'bezier', 'curve',
    'pushMatrix', 'popMatrix', 'pushStyle', 'popStyle'
  ];

  criticalFuncs.forEach(funcName => {
    if (!(funcName in window)) {
      Object.defineProperty(window, funcName, {
        get: function() {
          var activeInst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
          if (activeInst && typeof activeInst[funcName] === 'function') {
            return activeInst[funcName].bind(activeInst);
          }
          return function(...args) {
            var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
            if (inst && typeof inst[funcName] === 'function') {
              return inst[funcName].apply(inst, args);
            }
          };
        },
        set: function(val) {
          var inst = window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
          if (inst) {
            inst[funcName] = val;
          }
        },
        configurable: true,
        enumerable: true
      });
    }
  });
  
  // 12. 為 WebGLRenderingContext / WebGL2RenderingContext 補上非標準 uniform1..4 的相容 alias 護欄
  if (typeof WebGLRenderingContext !== 'undefined') {
    const glProto = WebGLRenderingContext.prototype;
    if (!glProto.uniform1) glProto.uniform1 = function(loc, v0) { return this.uniform1f(loc, v0); };
    if (!glProto.uniform2) glProto.uniform2 = function(loc, v0, v1) { return this.uniform2f(loc, v0, v1); };
    if (!glProto.uniform3) glProto.uniform3 = function(loc, v0, v1, v2) { return this.uniform3f(loc, v0, v1, v2); };
    if (!glProto.uniform4) glProto.uniform4 = function(loc, v0, v1, v2, v3) { return this.uniform4f(loc, v0, v1, v2, v3); };
  }
  if (typeof WebGL2RenderingContext !== 'undefined') {
    const glProto = WebGL2RenderingContext.prototype;
    if (!glProto.uniform1) glProto.uniform1 = function(loc, v0) { return this.uniform1f(loc, v0); };
    if (!glProto.uniform2) glProto.uniform2 = function(loc, v0, v1) { return this.uniform2f(loc, v0, v1); };
    if (!glProto.uniform3) glProto.uniform3 = function(loc, v0, v1, v2) { return this.uniform3f(loc, v0, v1, v2); };
    if (!glProto.uniform4) glProto.uniform4 = function(loc, v0, v1, v2, v3) { return this.uniform4f(loc, v0, v1, v2, v3); };
  }

  // 13. BMWalker (Generative Walker) 類別補全護欄
  if (typeof window.BMWalker === 'undefined') {
    window.BMWalker = class BMWalker {
      constructor() {
        this.pos = (typeof createVector === 'function') ? createVector(0, 0) : { x: 0, y: 0 };
        this.vel = (typeof createVector === 'function') ? createVector(0, 0) : { x: 0, y: 0 };
        this.markers = [];
      }
      walk() {}
      display() {}
      update() {}
    };
  }

  // 14. tlogo (Turtle Logo) 物件補全護欄
  if (typeof window.tlogo === 'undefined') {
    window.tlogo = {
      fd: function() {}, bk: function() {}, rt: function() {}, lt: function() {},
      pu: function() {}, pd: function() {}, setxy: function() {}, home: function() {},
      cs: function() {}, clean: function() {}, penUp: function() {}, penDown: function() {}
    };
  }

  const _createMockSound = function() {
    return {
      _isMockSound: true,
      play: function() { return this; },
      stop: function() { return this; },
      pause: function() { return this; },
      loop: function() { return this; },
      isPlaying: function() { return false; },
      setVolume: function() { return this; },
      pan: function() { return this; },
      rate: function() { return this; },
      disconnect: function() { return this; },
      connect: function() { return this; },
      onended: function() {},
      duration: function() { return 180.0; },
      currentTime: function() { return 0.0; },
      then: function(resolve) {
        if (resolve) {
          setTimeout(() => resolve(this), 0);
        }
        return this;
      }
    };
  };

  const _createMockFont = function() {
    return {
      _isMockFont: true,
      font: { data: true, tables: {}, _font: {} },
      textToPoints: function() { return []; },
      textBounds: function(str, x, y, fontSize) {
        var len = (str && str.length) || 1;
        var sz = fontSize || 12;
        return { x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 };
      },
      getPath: function() { return { commands: [] }; },
      getOutline: function() { return []; },
      then: function(resolve) {
        if (resolve) {
          setTimeout(() => resolve(this), 0);
        }
        return this;
      }
    };
  };

  // 15. click 與 dir 全域未宣告變數護欄
  if (typeof window.dir === 'undefined') { window.dir = 0; }
  if (typeof window.click === 'undefined') {
    window.click = _createMockSound();
  }

  // 16. 全域音訊變數初始化與 MediaElement.prototype.play 免疫防禦
  ['sound', 'audio', 'song', 'snd', 'player', 'track', 'voice', 'mySound', 'sample', 'music'].forEach(function(k) {
    if (typeof window[k] === 'undefined') {
      window[k] = _createMockSound();
    }
  });
  ['font', 'myFont', 'f', 'fnt', 'defaultFont'].forEach(function(k) {
    if (typeof window[k] === 'undefined') {
      window[k] = _createMockFont();
    }
  });

  if (typeof HTMLMediaElement !== 'undefined' && HTMLMediaElement.prototype) {
    HTMLMediaElement.prototype.play = function() { return Promise.resolve(); };
    HTMLMediaElement.prototype.pause = function() {};
  }
  if (typeof window.Audio !== 'undefined' && window.Audio.prototype) {
    window.Audio.prototype.play = function() { return Promise.resolve(); };
    window.Audio.prototype.pause = function() {};
  }

  // 17. p5.Font.prototype textToPoints & textBounds 防禦
  if (typeof p5 !== 'undefined' && p5.Font && p5.Font.prototype) {
    const origTextToPoints = p5.Font.prototype.textToPoints;
    p5.Font.prototype.textToPoints = function(...args) {
      if (!this || !this.font || (!this.font.data && !this.font.tables && !this.font._font)) {
        return [];
      }
      try {
        return origTextToPoints ? origTextToPoints.apply(this, args) : [];
      } catch(e) {
        return [];
      }
    };
    if (!p5.Font.prototype.textBounds) {
      p5.Font.prototype.textBounds = function(str, x, y, fontSize) {
        var len = (str && str.length) || 1;
        var sz = fontSize || 12;
        return { x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 };
      };
    }
  }

  // 18. frameCount 可寫入 Setter 支援（防止 Java 轉譯之作品賦值 frameCount = 0 觸發唯讀 Getter 報錯）
  try {
    let _customFrameCount = undefined;
    Object.defineProperty(window, 'frameCount', {
      get: function() {
        if (_customFrameCount !== undefined) return _customFrameCount;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
        if (inst && typeof inst.frameCount === 'number') return inst.frameCount;
        return 0;
      },
      set: function(val) {
        _customFrameCount = val;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
        if (inst) {
          try { inst.frameCount = val; } catch(e) {}
          if (typeof inst._setProperty === 'function') {
            try { inst._setProperty('frameCount', val); } catch(e) {}
          }
        }
      },
      configurable: true,
      enumerable: true
    });
  } catch(e) {}
})();
"""

MOCK_P5_JS = """
// p5.sound Mock/Stub Compatibility Layer
if (typeof window !== 'undefined') {
  window.P3D = window.P3D || "webgl";
  window.OPENGL = window.OPENGL || "webgl";
  window.P2D = window.P2D || "p2d";
  window.JAVA2D = window.JAVA2D || "p2d";
  ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].forEach(function(k) {
    if (typeof window[k] === 'undefined') window[k] = k.toLowerCase();
  });
  ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z'].forEach(function(k) {
    if (typeof window[k] === 'undefined') window[k] = 0;
  });
  (function() {
    var _audioChannels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
    var _sliderIdx = 0;

    function _createAudioBoundElement(min, max, defVal, step) {
      var _ch = _audioChannels[(_sliderIdx++) % _audioChannels.length];
      var _min = min !== undefined ? Number(min) : 0;
      var _max = max !== undefined ? Number(max) : 100;
      var _val = defVal !== undefined ? Number(defVal) : (_min + _max) / 2;
      var _step = step !== undefined ? Number(step) : 0;
      var _listeners = {};

      var el = function() { return _sp; };
      el.position = el.style = el.size = el.parent = el.option = el.texture = function() { return el; };
      el.id = function() { return ""; };
      el.class = function() { return el; };
      el.show = el.hide = function() { return el; };
      el.mousePressed = el.mouseClicked = el.html = function() { return el; };
      el.changed = el.input = function(cb) { if (typeof cb === 'function') _listeners['change'] = cb; return el; };
      el.on = el.off = el.addEventListener = el.removeEventListener = el.listen = function() { return el; };
      el.width = 100; el.height = 100;
      el[Symbol.iterator] = function* () { yield el; };

      el.value = function(newVal) {
        if (newVal !== undefined) {
          _val = Number(newVal);
          return el;
        }
        var norm = typeof window[_ch] !== 'undefined' ? Number(window[_ch]) : 0.5;
        var dynVal = _min + norm * (_max - _min);
        if (_step > 0) {
          dynVal = Math.round((dynVal - _min) / _step) * _step + _min;
        }
        return dynVal;
      };

      var handler = {
        get: function(t, p) {
          if (p === 'value') return t.value;
          if (p === 'slider') return t;
          if (p === 'elt') return { value: t.value(), style: {} };
          if (p in t) return t[p];
          if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
          return _sp;
        }
      };
      return new Proxy(el, handler);
    }

    var _do = function() { return _sp; };
    _do.position = _do.style = _do.size = _do.parent = _do.option = _do.texture = function() { return _sp; };
    _do.id = function() { return ""; };
    _do.class = _do.mousePressed = _do.mouseClicked = _do.html = _do.changed = _do.input = function() { return _sp; };
    _do.on = _do.off = _do.addEventListener = _do.removeEventListener = _do.listen = function() { return _sp; };
    _do.value = function() { return 0; };
    _do.width = 100; _do.height = 100;
    _do[Symbol.iterator] = function* () { yield _sp; };
    var _dh = {
      get: function(t, p) {
        if (p === 'slider') return _sp;
        if (p in t) return t[p];
        if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
        return _sp;
      },
      apply: function() { return _sp; },
      construct: function() { return _sp; }
    };
    var _sp = typeof Proxy !== 'undefined' ? new Proxy(_do, _dh) : _do;

    if (typeof createSlider === 'undefined') {
      window.createSlider = function(min, max, defVal, step) {
        return _createAudioBoundElement(min, max, defVal, step);
      };
    }
    if (typeof createP === 'undefined') window.createP = function() { return _sp; };
    if (typeof createDiv === 'undefined') window.createDiv = function() { return _sp; };
    if (typeof createButton === 'undefined') window.createButton = function() { return _sp; };
    if (typeof createInput === 'undefined') window.createInput = function(defVal) { return _createAudioBoundElement(0, 100, defVal || 50, 1); };
    if (typeof createSelect === 'undefined') window.createSelect = function() { return _createAudioBoundElement(0, 5, 0, 1); };
    if (typeof createCheckbox === 'undefined') window.createCheckbox = function() { return _createAudioBoundElement(0, 1, 0, 1); };
    if (typeof createRadio === 'undefined') window.createRadio = function() { return _createAudioBoundElement(0, 5, 0, 1); };
    if (typeof createColorPicker === 'undefined') window.createColorPicker = function() { return _sp; };
    if (typeof createElement === 'undefined') window.createElement = function() { return _sp; };
    if (typeof select === 'undefined') window.select = function() { return _sp; };
    if (typeof selectAll === 'undefined') window.selectAll = function() { return []; };
    window.Pause = window.Pause || _sp;
    window.Play = window.Play || _sp;
    window.Reset = window.Reset || _sp;
  })();
  if (typeof window.cnv === 'undefined') window.cnv = typeof createDiv !== 'undefined' ? createDiv() : { width: 1422, height: 800, parent: function(){}, position: function(){}, style: function(){} };
  if (typeof window.inner1 === 'undefined') window.inner1 = window.cnv;
  if (typeof window.eyePic === 'undefined') window.eyePic = window.cnv;
  if (typeof window.myColor === 'undefined') window.myColor = '#ffffff';
  if (typeof window.grainAmount === 'undefined') window.grainAmount = 0;
  const _createMockSound = function() {
    return {
      _isMockSound: true,
      play: function() { return this; },
      stop: function() { return this; },
      pause: function() { return this; },
      loop: function() { return this; },
      isPlaying: function() { return false; },
      setVolume: function() { return this; },
      pan: function() { return this; },
      rate: function() { return this; },
      disconnect: function() { return this; },
      connect: function() { return this; },
      onended: function() {},
      duration: function() { return 180.0; },
      currentTime: function() { return 0.0; },
      then: function(resolve) { if (resolve) setTimeout(() => resolve(this), 0); return this; }
    };
  };
  const _createMockFont = function() {
    return {
      _isMockFont: true,
      font: { data: true, tables: {}, _font: {} },
      textToPoints: function() { return []; },
      textBounds: function(str, x, y, fontSize) {
        var len = (str && str.length) || 1;
        var sz = fontSize || 12;
        return { x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 };
      },
      getPath: function() { return { commands: [] }; },
      getOutline: function() { return []; },
      then: function(resolve) { if (resolve) setTimeout(() => resolve(this), 0); return this; }
    };
  };

  ['res','scr','gap','asd','nPoints','scaledT','_count','angleStepMax','objs','X0','pg','starColor','clr2','typ','largX',
   'paper','pg2','col1','col2','S_actual','maxD','looping','sinput','SZ','medRadius','minRadius','maxRadius','locations',
   'grid_size','circle_diams','dots','points','particles','cells','stars','nodes','current_img','img','imgs','moon',
   'bg','font','tex','cols','rows','pal','palette','pos','vel','acc','colors','dirs','movers','lines','curves','boxes',
   'shapes','polygons','vectors','shaderProgram','sh','dwidth','dheight','kRadiusFactor','minDistFactor','nbrParticles',
   'reference','catSpeed','tt','_shiftAmp','_shifAmp','BG_C','FG','areas','aryCornerXy','pad','nx','ny','nz','nw',
   'allowedLetters','validWords','currentLetters','activeIndex','lettersWord','bars','frames','photo','cover','orient','ovel','start','orthoview','num',
   'mobile','buildings','curSeed','px','py','pz','dx','dy','dz','vx','vy','vz','cx','cy','cz','sx','sy','sz','fx','fy','wx','wy','rx','ry','rz',
   'noiseGra','aryRegionRect','numRegionRect','regionClearanceRatio','minRegionX','maxRegionX','minRegionY','maxRegionY',
   '_minW','_maxW','_minWidth','_bgWidth','_points','_obj','_xy','_numObject','_clearanceRatio','_splitRatio',
   'noiseSeedInit','noiseSpeed','noiseFreq','thetaFreq','thetaInit',
   'sound','audio','song','snd','player','track','voice','mySound','sample','music','myFont','f','fnt','defaultFont'].forEach(function(k) {
    if (typeof window[k] === 'undefined') {
      if (['objs','dots','points','particles','cells','stars','nodes','locations','colors','dirs','movers','lines','curves','boxes','shapes','polygons','vectors','pal','palette','circle_diams','imgs','areas','aryCornerXy','bars','frames','currentLetters','validWords','buildings','aryRegionRect','_obj','_xy','noiseSeedInit'].includes(k)) {
        window[k] = [];
      } else if (['sound','audio','song','snd','player','track','voice','mySound','sample','music'].includes(k)) {
        window[k] = _createMockSound();
      } else if (['font','myFont','f','fnt','defaultFont'].includes(k)) {
        window[k] = _createMockFont();
      } else if (k === 'scr') {
        window[k] = window.cnv;
      } else if (['img', 'moon', 'photo', 'cover'].includes(k)) {
        window[k] = { width: 100, height: 100, resize: function(w,h){ if(w) this.width=w; if(h) this.height=h; return this; }, loadPixels: function(){}, updatePixels: function(){}, get: function(){ return [0,0,0,0]; }, set: function(){}, copy: function(){}, mask: function(){}, filter: function(){}, pixels: new Uint8ClampedArray(100*100*4), canvas: (typeof document !== 'undefined' ? document.createElement('canvas') : null) };
      } else if (['orient', 'ovel', 'start'].includes(k)) {
        window[k] = { x: 0, y: 0, z: 0, add: function(){ return this; }, mult: function(){ return this; }, sub: function(){ return this; } };
      } else if (['pg', 'pg2', 'paper', 'noiseGra'].includes(k)) {
        window[k] = { width: 100, height: 100, beginDraw: function(){}, endDraw: function(){}, background: function(){}, image: function(){}, get: function(){ return this; }, loadPixels: function(){}, updatePixels: function(){}, pixels: [], resize: function(w,h){ if(w) this.width=w; if(h) this.height=h; return this; }, imageMode: function(){}, fill: function(){}, stroke: function(){}, noFill: function(){}, noStroke: function(){}, rect: function(){}, ellipse: function(){}, line: function(){}, point: function(){}, push: function(){}, pop: function(){}, translate: function(){}, rotate: function(){}, scale: function(){}, textSize: function(){}, textAlign: function(){}, text: function(){}, clear: function(){} };
      } else if (['starColor', 'clr2', 'myColor', 'col1', 'col2', 'bg', 'BG_C', 'FG'].includes(k)) {
        window[k] = '#ffffff';
      } else if (k === 'allowedLetters') {
        window[k] = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
      } else if (k === 'looping') {
        window[k] = true;
      } else if (k === 'orthoview' || k === 'mobile') {
        window[k] = false;
      } else if (k === 'angleStepMax' || k === 'numRegionRect') {
        window[k] = 1;
      } else if (k === 'curSeed') {
        window[k] = Math.floor(Math.random() * 999999);
      } else if (k === 'regionClearanceRatio' || k === '_clearanceRatio' || k === '_splitRatio') {
        window[k] = 0.5;
      } else {
        window[k] = 0;
      }
    }
  });
  window.addEventListener('unhandledrejection', function(event) {
    event.preventDefault();
  });
  if (typeof Element !== 'undefined' && Element.prototype && !Element.prototype.size) {
    Element.prototype.size = function() { return this; };
  }
  // MediaElement play immunity
  if (typeof HTMLMediaElement !== 'undefined' && HTMLMediaElement.prototype) {
    HTMLMediaElement.prototype.play = function() { return Promise.resolve(); };
    HTMLMediaElement.prototype.pause = function() {};
  }
  if (typeof window.Audio !== 'undefined' && window.Audio.prototype) {
    window.Audio.prototype.play = function() { return Promise.resolve(); };
    window.Audio.prototype.pause = function() {};
  }
  // _renderer.getTexture immunity
  if (typeof window._renderer !== 'undefined' && window._renderer && typeof window._renderer.getTexture !== 'function') {
    window._renderer.getTexture = function() { return { update: function(){}, bindTexture: function(){}, unbindTexture: function(){} }; };
  }
  // frameCount setter support
  try {
    let _customFrameCount = undefined;
    Object.defineProperty(window, 'frameCount', {
      get: function() {
        if (_customFrameCount !== undefined) return _customFrameCount;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
        if (inst && typeof inst.frameCount === 'number') return inst.frameCount;
        return 0;
      },
      set: function(val) {
        _customFrameCount = val;
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
        if (inst) {
          try { inst.frameCount = val; } catch(e) {}
          if (typeof inst._setProperty === 'function') {
            try { inst._setProperty('frameCount', val); } catch(e) {}
          }
        }
      },
      configurable: true,
      enumerable: true
    });
  } catch(e) {}
  if (typeof p5 !== 'undefined') {
    if (p5.Image && p5.Image.prototype) {
      if (!('gifProperties' in p5.Image.prototype)) {
        Object.defineProperty(p5.Image.prototype, 'gifProperties', {
          get: function() { return this._gifProps || { display: true, numFrames: 1, loopCount: 0, frameRate: 30, frames: [] }; },
          set: function(val) { this._gifProps = val; },
          configurable: true
        });
      }
      if (!p5.Image.prototype.resize) {
        p5.Image.prototype.resize = function(w, h) {
          if (w) this.width = w;
          if (h) this.height = h;
          return this;
        };
      }
      if (!p5.Image.prototype.loadPixels) p5.Image.prototype.loadPixels = function() {};
      if (!p5.Image.prototype.updatePixels) p5.Image.prototype.updatePixels = function() {};
      if (!p5.Image.prototype.get) p5.Image.prototype.get = function() { return [0, 0, 0, 0]; };
      if (!p5.Image.prototype.set) p5.Image.prototype.set = function() {};
      if (!p5.Image.prototype.mask) p5.Image.prototype.mask = function() {};
      if (!p5.Image.prototype.filter) p5.Image.prototype.filter = function() {};
      if (!p5.Image.prototype.copy) p5.Image.prototype.copy = function() {};
      if (!p5.Image.prototype.blend) p5.Image.prototype.blend = function() {};
    }
    if (p5.Graphics && p5.Graphics.prototype) {
      if (!p5.Graphics.prototype.imageMode) p5.Graphics.prototype.imageMode = function() {};
    }
  }
}
if (typeof p5 !== 'undefined') {
  // Helper: create a mock audio node with connect/disconnect for p5.sound internal use
  var _mockAudioNode = function() {
    return { connect: function(){return this;}, disconnect: function(){return this;}, gain: {value:1, setValueAtTime:function(){}} };
  };
  p5.AudioIn = function() {
    this.output = _mockAudioNode();
    this.input = _mockAudioNode();
    this.start = function() {};
    this.connect = function() {};
    this.disconnect = function() {};
    this.getLevel = function() {
      return window.audioLow || 0.5;
    };
  };
  p5.Amplitude = function() {
    this.output = _mockAudioNode();
    this.input = _mockAudioNode();
    this.setInput = function() {};
    this.connect = function() {};
    this.disconnect = function() {};
    this.getLevel = function() {
      return window.beatEnergy || window.audioMid || 0.5;
    };
  };
  p5.FFT = function() {
    this.output = _mockAudioNode();
    this.input = _mockAudioNode();
    this.setInput = function() {};
    this.connect = function() {};
    this.disconnect = function() {};
    this.analyze = function() {
      let arr = new Array(1024).fill(0);
      let lowVal = Math.round((window.audioLow || 0.5) * 255);
      let midVal = Math.round((window.audioMid || 0.5) * 255);
      let highVal = Math.round((window.audioHigh || 0.5) * 255);
      let beatMod = (window.beatEnergy || 0.5) * 40;
      for (let i = 0; i < 100; i++) arr[i] = Math.min(255, Math.max(0, lowVal + (Math.random() * 20 - 10) + beatMod));
      for (let i = 100; i < 500; i++) arr[i] = Math.min(255, Math.max(0, midVal + (Math.random() * 15 - 7)));
      for (let i = 500; i < 1024; i++) arr[i] = Math.min(255, Math.max(0, highVal + (Math.random() * 10 - 5)));
      return arr;
    };
    this.getEnergy = function(freq1, freq2) {
      if (typeof freq1 === 'string') {
        let f = freq1.toLowerCase();
        if (f === 'bass') return Math.round((window.audioLow || 0.5) * 255);
        if (f === 'lowmid') return Math.round(((window.audioLow + window.audioMid)/2 || 0.5) * 255);
        if (f === 'mid') return Math.round((window.audioMid || 0.5) * 255);
        if (f === 'highmid') return Math.round(((window.audioMid + window.audioHigh)/2 || 0.5) * 255);
        if (f === 'treble') return Math.round((window.audioHigh || 0.5) * 255);
      }
      let val = window.audioMid || 0.5;
      if (freq1 < 250) val = window.audioLow || 0.5;
      else if (freq1 > 2000) val = window.audioHigh || 0.5;
      return Math.round(val * 255);
    };
    this.getLevel = function() {
      return window.audioEnergy || window.beatEnergy || window.audioMid || 0.5;
    };
  };

  // Mock p5.SoundFile to act as a reactive Virtual Audio Receiver
  p5.SoundFile = function(path, successCallback, errorCallback) {
    console.log('[Mock] p5.SoundFile created for:', path);
    this.output = _mockAudioNode();
    this.input = _mockAudioNode();
    this._isPlaying = false;
    this.isLoaded = function() { return true; };
    this.isPlaying = function() { return this._isPlaying !== false && window.isAudioPlaying !== false; };
    this.play = function() { this._isPlaying = true; return this; };
    this.loop = function() { this._isPlaying = true; return this; };
    this.stop = function() { this._isPlaying = false; return this; };
    this.pause = function() { this._isPlaying = false; return this; };
    this.setVolume = function() { return this; };
    this.pan = function() { return this; };
    this.rate = function() { return 1; };
    this.duration = function() { return window.totalAudioDuration || 180.0; };
    this.currentTime = function() { return (typeof window.custom_time_ms !== 'undefined' ? window.custom_time_ms / 1000 : (window.currentAudioTime || (window.frameCount ? window.frameCount / 60 : 0.0))); };
    this.getLevel = function() { return window.audioEnergy || window.beatEnergy || (typeof window.audioMid !== 'undefined' ? (window.audioLow + window.audioMid + window.audioHigh)/3 : 0.5); };
    this.jump = function() {};
    this.channels = function() { return 2; };
    this.sampleRate = function() { return 44100; };
    this.frames = function() { return 44100 * 180; };
    this.getPeaks = function(n) { return new Float32Array(n || 5).fill(0); };
    this.reverseBuffer = function() {};
    this.onended = function() {};
    this.connect = function() {};
    this.disconnect = function() {};
    this.setPath = function() {};
    this.setBuffer = function() {};
    this.processPeaks = function() { return Promise.resolve([]); };
    this.addCue = function() { return 0; };
    this.removeCue = function() {};
    this.clearCues = function() {};
    if (successCallback) setTimeout(() => { try { successCallback(this); } catch(e) {} }, 10);
  };

  // Override loadSound globally
  if (typeof window.loadSound === 'undefined') {
    window.loadSound = function(path, successCallback, errorCallback) {
      console.log('[Mock] loadSound intercepted for:', path);
      var mockSound = new p5.SoundFile(path, successCallback, errorCallback);
      return mockSound;
    };
  }
  // Also patch on p5.prototype for instance mode
  if (p5.prototype) {
    p5.prototype.loadSound = function(path, successCallback, errorCallback) {
      console.log('[Mock] p5.prototype.loadSound intercepted for:', path);
      var mockSound = new p5.SoundFile(path, successCallback, errorCallback);
      return mockSound;
    };
    p5.prototype.createCapture = p5.prototype.createCapture || function() {
      const v = document.createElement('video');
      v.play = function(){}; v.pause = function(){};
      const mockCap = { elt: v, hide: function(){ return mockCap; }, size: function(){ return mockCap; }, position: function(){ return mockCap; }, loop: function(){ return mockCap; }, volume: function(){ return mockCap; } };
      return mockCap;
    };
  }

  // Implement p5.prototype.registerMethod shim for p5.js 2.x compatibility
  var _registerMethodPolyfill = function(hookName, method) {
    if (typeof method !== 'function') return;
    if (p5.prototype) {
      p5.prototype._registeredMethods = p5.prototype._registeredMethods || {};
      if (!p5.prototype._registeredMethods[hookName]) {
        p5.prototype._registeredMethods[hookName] = [];
      }
      p5.prototype._registeredMethods[hookName].push(method);
    }
    const hookMapping = {
      'init': 'presetup',
      'pre': 'predraw',
      'post': 'postdraw',
      'remove': 'remove'
    };
    const newHookName = hookMapping[hookName];
    if (newHookName && typeof p5.registerAddon === 'function') {
      p5.registerAddon((p5Instance, fn, lifecycles) => {
        if (!lifecycles) return;
        const oldHook = lifecycles[newHookName];
        lifecycles[newHookName] = function() {
          if (typeof oldHook === 'function') oldHook.call(this);
          method.call(this);
        };
      });
    }
  };
  if (p5.prototype && !p5.prototype.registerMethod) {
    p5.prototype.registerMethod = _registerMethodPolyfill;
  }
  if (!p5.registerMethod) {
    p5.registerMethod = _registerMethodPolyfill;
  }
  // Expose mock DOM createP/createDiv helpers directly to window to prevent "reading position" errors
  var createDummyDom = function(tag, ...createArgs) {
    let dummyEl = document.createElement(tag === 'slider' || tag === 'colorpicker' || tag === 'checkbox' || tag === 'radio' ? 'input' : (tag || 'div'));
    dummyEl.style.setProperty('display', 'none', 'important');
    dummyEl.style.setProperty('visibility', 'hidden', 'important');
    dummyEl.style.setProperty('opacity', '0', 'important');
    dummyEl.style.setProperty('pointer-events', 'none', 'important');
    dummyEl.style.setProperty('position', 'absolute', 'important');
    dummyEl.style.setProperty('top', '-99999px', 'important');
    dummyEl.style.setProperty('left', '-99999px', 'important');
    dummyEl.style.setProperty('width', '0px', 'important');
    dummyEl.style.setProperty('height', '0px', 'important');
    dummyEl.style.setProperty('z-index', '-99999', 'important');
    
    // Add stub methods to emulate p5.Element
    dummyEl.elt = dummyEl;
    dummyEl.class = function() { return this; };
    let dummyIdVal = '';
    const idFn = function(val) {
      if (val === undefined) return dummyIdVal || dummyEl.getAttribute('id') || '';
      dummyIdVal = String(val);
      dummyEl.setAttribute('id', dummyIdVal);
      return dummyEl;
    };
    idFn.toString = function() { return dummyIdVal; };
    idFn.valueOf = function() { return dummyIdVal; };
    Object.defineProperty(dummyEl, 'id', {
      get: function() { return idFn; },
      set: function(val) {
        dummyIdVal = String(val);
        dummyEl.setAttribute('id', dummyIdVal);
      },
      configurable: true
    });
    dummyEl.parent = function() { return this; };
    dummyEl.position = function() { return this; };
    dummyEl.size = function() { return this; };
    
    const originalStyle = dummyEl.style;
    Object.defineProperty(dummyEl, 'style', {
      value: function(prop, val) {
        if (arguments.length === 0) return originalStyle;
        if (arguments.length === 1 && typeof prop === 'string') {
          return originalStyle[prop] || originalStyle.getPropertyValue(prop);
        }
        if (prop && typeof prop === 'object') {
          for (let k in prop) {
            originalStyle.setProperty(k, prop[k]);
          }
        } else if (typeof prop === 'string' && val !== undefined) {
          originalStyle.setProperty(prop, val);
        }
        return this;
      },
      writable: true,
      configurable: true
    });
    dummyEl.show = function() { return this; };
    dummyEl.hide = function() { return this; };
    dummyEl.html = function() { return this; };
    dummyEl.attribute = function() { return this; };
    dummyEl.removeAttribute = function() { return this; };
    
    // Mock input values linked to audio energy algorithms
    let boundProperty = 'audioLow';
    let manualVal = undefined;
    
    if (tag === 'slider') {
      let minVal = createArgs[0] !== undefined ? createArgs[0] : 0;
      let maxVal = createArgs[1] !== undefined ? createArgs[1] : 100;
      let defaultVal = createArgs[2] !== undefined ? createArgs[2] : (minVal + maxVal)/2;
      let stepVal = createArgs[3] !== undefined ? createArgs[3] : 0;
      
      const channels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
      boundProperty = channels[Math.floor(Math.random() * channels.length)];
      let phaseOffset = Math.random() * Math.PI * 2;
      let speedFactor = 0.5 + Math.random() * 1.5;
      
      Object.defineProperty(dummyEl, 'value', {
        value: function(val) {
          if (val !== undefined) {
            manualVal = Number(val);
            dummyEl.setAttribute('value', String(val));
            return this;
          }
          if (manualVal !== undefined) {
            let norm = window[boundProperty];
            if (typeof norm !== 'number') norm = 0.5;
            let delta = (norm - 0.5) * (maxVal - minVal) * 0.35;
            let res = Math.max(minVal, Math.min(maxVal, manualVal + delta));
            if (stepVal > 0) res = Math.round((res - minVal) / stepVal) * stepVal + minVal;
            return res;
          }
          let t = (window.custom_time_ms || 0) * 0.001;
          let norm = window[boundProperty];
          if (typeof norm !== 'number') norm = 0.5;
          let wave = 0.5 + 0.3 * Math.sin(t * speedFactor + phaseOffset) + (norm - 0.5) * 0.4;
          wave = Math.max(0, Math.min(1, wave));
          let computed = minVal + wave * (maxVal - minVal);
          if (stepVal > 0) computed = Math.round((computed - minVal) / stepVal) * stepVal + minVal;
          return computed;
        },
        writable: true,
        configurable: true
      });
    } else if (tag === 'checkbox') {
      let defaultChecked = createArgs[1] !== undefined ? Boolean(createArgs[1]) : false;
      let checkManual = undefined;
      dummyEl.checked = function(val) {
        if (val !== undefined) {
          checkManual = Boolean(val);
          return this;
        }
        if (checkManual !== undefined) return checkManual;
        let band = (window.audioLow || 0.5);
        return band > 0.48 || (window.isBeat || false);
      };
      Object.defineProperty(dummyEl, 'value', {
        value: function(val) { return dummyEl.checked(val); },
        writable: true,
        configurable: true
      });
    } else if (tag === 'button') {
      dummyEl._callbacks = [];
      dummyEl.mousePressed = function(cb) {
        if (typeof cb === 'function') dummyEl._callbacks.push(cb);
        window._activeMockButtons = window._activeMockButtons || [];
        if (!window._activeMockButtons.includes(dummyEl)) window._activeMockButtons.push(dummyEl);
        return this;
      };
      dummyEl.mouseClicked = dummyEl.mousePressed;
      Object.defineProperty(dummyEl, 'value', {
        value: function() { return 1; },
        writable: true,
        configurable: true
      });
    } else if (tag === 'select') {
      dummyEl._options = [];
      dummyEl._selectedVal = undefined;
      dummyEl.option = function(name, val) {
        let actualVal = val !== undefined ? val : name;
        dummyEl._options.push({ name: name, value: actualVal });
        const opt = document.createElement('option');
        opt.value = actualVal;
        opt.text = name;
        dummyEl.appendChild(opt);
        return dummyEl;
      };
      dummyEl.selected = function(val) {
        if (val !== undefined) {
          dummyEl._selectedVal = val;
          return this;
        }
        if (dummyEl._selectedVal !== undefined) return dummyEl._selectedVal;
        if (dummyEl._options.length === 0) return '';
        let idx = Math.floor((window.audioMid || 0.5) * dummyEl._options.length) % dummyEl._options.length;
        return dummyEl._options[idx].value;
      };
      Object.defineProperty(dummyEl, 'value', {
        value: function(val) { return dummyEl.selected(val); },
        writable: true,
        configurable: true
      });
    } else {
      Object.defineProperty(dummyEl, 'value', {
        value: function(val) {
          if (val === undefined) return "0.5";
          return this;
        },
        writable: true,
        configurable: true
      });
    }
    
    dummyEl.input = function(callback) {
      setInterval(() => {
        if (typeof callback === 'function') {
          try { callback.call(dummyEl); } catch(e){}
        }
      }, 50);
      return this;
    };
    dummyEl.changed = function(callback) {
      setInterval(() => {
        if (typeof callback === 'function') {
          try { callback.call(dummyEl); } catch(e){}
        }
      }, 100);
      return this;
    };
    dummyEl.mouseMoved = function() { return this; };
    if (!dummyEl.mousePressed) dummyEl.mousePressed = function() { return this; };
    dummyEl.mouseReleased = function() { return this; };
    if (!dummyEl.mouseClicked) dummyEl.mouseClicked = function() { return this; };
    dummyEl.disable = function() { return dummyEl; };
    dummyEl.enable = function() { return dummyEl; };
    dummyEl.css = function(prop, val) {
      if (typeof prop === 'object') {
        Object.assign(dummyEl.style, prop);
      } else if (prop && val !== undefined) {
        dummyEl.style[prop] = val;
      }
      return dummyEl;
    };

    // Append to body but hidden
    if (document.body) {
      document.body.appendChild(dummyEl);
    } else {
      window.addEventListener('DOMContentLoaded', () => {
        document.body.appendChild(dummyEl);
      });
    }
    
    return dummyEl;
  };
  
  window.createP = () => createDummyDom('p');
  window.createDiv = () => createDummyDom('div');
  window.createButton = (...args) => createDummyDom('button', ...args);
  window.createSpan = () => createDummyDom('span');
  window.createSlider = (...args) => createDummyDom('slider', ...args);
  window.createCheckbox = (...args) => createDummyDom('checkbox', ...args);
  window.createSelect = (...args) => {
    var el = createDummyDom('select', ...args);
    return _ensureDomStub(el);
  };
  window.createRadio = (...args) => createDummyDom('radio', ...args);
  window.createInput = (...args) => createDummyDom('input', ...args);
  window.createColorPicker = (...args) => createDummyDom('colorpicker', ...args);
  
  if (p5.prototype) {
    p5.prototype.createP = () => createDummyDom('p');
    p5.prototype.createDiv = () => createDummyDom('div');
    p5.prototype.createButton = (...args) => createDummyDom('button', ...args);
    p5.prototype.createSpan = () => createDummyDom('span');
    p5.prototype.createSlider = (...args) => createDummyDom('slider', ...args);
    p5.prototype.createCheckbox = (...args) => createDummyDom('checkbox', ...args);
    p5.prototype.createSelect = function(...args) {
      var el = createDummyDom('select', ...args);
      return _ensureDomStub(el);
    };
    p5.prototype.createRadio = (...args) => createDummyDom('radio', ...args);
    p5.prototype.createInput = (...args) => createDummyDom('input', ...args);
    p5.prototype.createColorPicker = (...args) => createDummyDom('colorpicker', ...args);


    if (typeof p5.Element !== 'undefined' && p5.Element.prototype) {
      if (!p5.Element.prototype.option) {
        p5.Element.prototype.option = function(name, val) {
          if (this.elt) {
            const opt = document.createElement('option');
            opt.value = val !== undefined ? val : name;
            opt.text = name;
            this.elt.appendChild(opt);
          }
          return this;
        };
      }
      if (!p5.Element.prototype.selected) p5.Element.prototype.selected = function() { return this.value ? this.value() : ''; };
      if (!p5.Element.prototype.disable) p5.Element.prototype.disable = function() { return this; };
      if (!p5.Element.prototype.enable) p5.Element.prototype.enable = function() { return this; };
      if (!p5.Element.prototype.css) {
        p5.Element.prototype.css = function(prop, val) {
          if (this.elt && this.elt.style) {
            if (typeof prop === 'object') Object.assign(this.elt.style, prop);
            else if (prop && val !== undefined) this.elt.style[prop] = val;
          }
          return this;
        };
      }
    }

    
    // Wrap color() to automatically auto-correct invalid hexadecimal color strings (e.g. 5-digit #e56b6)
    const origColor = p5.prototype.color;
    p5.prototype.color = function(...args) {
      if (args.length === 1 && typeof args[0] === 'string') {
        let cStr = args[0].trim();
        if (cStr.startsWith('#')) {
          let hex = cStr.substring(1);
          if (hex.length === 5) {
            args[0] = '#' + hex + '0';
          } else if (hex.length === 7) {
            args[0] = '#' + hex + '0';
          }
        }
      }
      var inst = this || window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
      try {
        if (inst && inst._renderer && typeof origColor === 'function') {
          return origColor.apply(inst, args);
        }
      } catch(e) {}
      
      try {
        if (inst && typeof origColor === 'function') {
          return origColor.apply(inst, [0, 0, 0]);
        }
      } catch(err) {}

      // Robust fallback p5.Color-like structure
      return {
        _isMockColor: true,
        levels: [0, 0, 0, 255],
        _array: [0, 0, 0, 1],
        mode: 'rgb',
        maxes: { rgb: [255, 255, 255, 255] },
        setAlpha: function() { return this; },
        setRed: function() { return this; },
        setGreen: function() { return this; },
        setBlue: function() { return this; },
        setHeading: function() { return this; },
        toString: function() { return 'rgba(0,0,0,1)'; }
      };
    };
  }

  // Inject robust chromotome mock as a fallback to prevent ReferenceError: chromotome is not defined
  if (typeof window.chromotome === 'undefined') {
    window.chromotome = {
      get: function(name) {
        const fallbacks = [
          { name: "default", colors: ["#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff"], stroke: "#1a1a1a", background: "#f4f1de" },
          { name: "warm", colors: ["#e9dbce", "#d77a61", "#223843", "#eff1f3", "#dbd3d8"], stroke: "#333333", background: "#fdfbd4" },
          { name: "cool", colors: ["#22223b", "#c9ada7", "#4a4e69", "#9a8c98", "#f2e9e4"], stroke: "#000000", background: "#e0e4cc" }
        ];
        if (name) {
          const match = fallbacks.find(p => p.name === name);
          if (match) return match;
        }
        return fallbacks[Math.floor(Math.random() * fallbacks.length)];
      },
      getAll: function() {
        return [
          { name: "default", colors: ["#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff"] },
          { name: "warm", colors: ["#e9dbce", "#d77a61", "#223843", "#eff1f3", "#dbd3d8"] }
        ];
      }
    };
  }

  // 1. Safe Property Redefine Guard to prevent 'Cannot redefine property' errors
  const origDefineProperty = Object.defineProperty;
  Object.defineProperty = function(obj, prop, descriptor) {
    if (descriptor && typeof descriptor === 'object') {
      descriptor = Object.assign({}, descriptor);
      descriptor.configurable = true;
    }
    try {
      return origDefineProperty(obj, prop, descriptor);
    } catch (e) {
      try {
        if (descriptor && 'value' in descriptor) {
          obj[prop] = descriptor.value;
        }
      } catch(err) {}
      return obj;
    }
  };


  // Restore p5.Renderer prototype _setAttributes for p5.js v2 backward compatibility
  if (typeof p5 !== 'undefined') {
    ['Renderer', 'Renderer2D', 'RendererGL'].forEach(rName => {
      if (p5[rName] && p5[rName].prototype && !p5[rName].prototype._setAttributes) {
        p5[rName].prototype._setAttributes = function() { return this; };
      }
    });
  }


  // Safe device motion/orientation event wrappers for p5.prototype & window
  if (typeof p5 !== 'undefined' && p5.prototype) {
    ['_handleMotion', '_ondevicemotion', '_ondeviceorientation'].forEach(function(mName) {
      if (p5.prototype[mName]) {
        var origMotion = p5.prototype[mName];
        p5.prototype[mName] = function(e) {
          if (!e || typeof e !== 'object') {
            e = { type: 'devicemotion', acceleration: {x:0, y:0, z:0}, accelerationIncludingGravity: {x:0, y:0, z:0}, rotationRate: {alpha:0, beta:0, gamma:0} };
          }
          try {
            return origMotion.call(this, e);
          } catch(err) {
            return this;
          }
        };
      }
    });
  }

  // Intercept window devicemotion and deviceorientation event dispatching
  if (typeof window !== 'undefined' && window.addEventListener) {
    var dummyMotionEvent = { type: 'devicemotion', acceleration: {x:0, y:0, z:0}, accelerationIncludingGravity: {x:0, y:0, z:0}, rotationRate: {alpha:0, beta:0, gamma:0} };
    var dummyOrientEvent = { type: 'deviceorientation', alpha: 0, beta: 0, gamma: 0 };
    window.addEventListener('devicemotion', function(e) {
      if (!e) e = dummyMotionEvent;
    }, true);
    window.addEventListener('deviceorientation', function(e) {
      if (!e) e = dummyOrientEvent;
    }, true);
  }





  // SVG / 2D / WebGL Renderer parameter guard for p5.prototype.createCanvas
  if (p5.prototype) {
    const origCreateCanvas = p5.prototype.createCanvas;
    if (origCreateCanvas) {
      p5.prototype.createCanvas = function(w, h, renderer) {
        if (typeof renderer === 'string') {
          var rLower = renderer.toLowerCase();
          if (rLower === 'svg') {
            renderer = typeof window.SVG !== 'undefined' ? window.SVG : undefined;
          } else if (rLower === 'p5.renderer2d' || rLower === '2d' || rLower === 'p2d') {
            renderer = undefined;
          } else if (rLower === 'webgl' || rLower === 'p3d' || rLower === 'opengl') {
            renderer = 'webgl';
          }
        } else if (typeof p5 !== 'undefined' && (renderer === p5.Renderer2D || renderer === p5.Renderer)) {
          renderer = undefined;
        }
        try {
          return origCreateCanvas.call(this, w, h, renderer);
        } catch(e) {
          console.warn('[P5_COMPAT] createCanvas failed with renderer parameter, fallback to 2D:', e);
          try {
            return origCreateCanvas.call(this, w, h);
          } catch(err) {
            return this;
          }
        }
      };
    }
  }

  // Intercept window pointer/mouse event getBoundingClientRect calls
  if (typeof window !== 'undefined' && window.addEventListener) {
    window.addEventListener('pointermove', function(e) {
      if (e && typeof e.getBoundingClientRect !== 'function') {
        e.getBoundingClientRect = function() {
          return { top: 0, left: 0, width: window.innerWidth || 800, height: window.innerHeight || 800 };
        };
      }
    }, true);
  }


  if (p5.prototype) {
    const origColor = p5.prototype.color;
    p5.prototype.color = function(...args) {
      if (args.length === 1 && typeof args[0] === 'string') {
        let cStr = args[0].trim();
        if (cStr.startsWith('#')) {
          let hex = cStr.substring(1);
          if (hex.length === 5) {
            args[0] = '#' + hex + '0';
          }
        }
      }
      var inst = this || window._p5Instance || (p5.activeInstances && p5.activeInstances[0]) || p5.instance;
      try {
        if (inst && inst._renderer && typeof origColor === 'function') {
          return origColor.apply(inst, args);
        }
      } catch(e) {}
      try {
        if (inst && typeof origColor === 'function') {
          return origColor.apply(inst, [0, 0, 0]);
        }
      } catch(err) {}
      return {
        _isMockColor: true,
        levels: [0, 0, 0, 255],
        _array: [0, 0, 0, 1],
        mode: 'rgb',
        maxes: { rgb: [255, 255, 255, 255] },
        setAlpha: function() { return this; },
        setRed: function() { return this; },
        setGreen: function() { return this; },
        setBlue: function() { return this; },
        setHeading: function() { return this; },
        toString: function() { return 'rgba(0,0,0,1)'; }
      };
    };
  }

  // 2. Global fallback getters for commonly missing creative coding variables
  const fallbackVars = {
    bodymovin: typeof window.bodymovin !== 'undefined' ? window.bodymovin : (window.lottie || { loadAnimation: function() { return { play: function(){}, stop: function(){}, setSpeed: function(){}, setDirection: function(){}, destroy: function(){} }; } }),
    quadraticVertex: typeof window.quadraticVertex !== 'undefined' ? window.quadraticVertex : function(...args) {},
    patternColors: typeof window.patternColors !== 'undefined' ? window.patternColors : function() { return ['#ffffff', '#000000']; },
    rough: { canvas: function() { return {}; } },
    Delaunay: { from: function() { return { triangles: [], halfedges: [] }; } },
    spectral: (function() {
      var SpecColor = function(r, g, b) { this.r = r || 0; this.g = g || 0; this.b = b || 0; };
      SpecColor.prototype.toArray = function() { return [this.r, this.g, this.b]; };
      return {
        Color: SpecColor,
        palette: function() { return []; },
        mix: function(c1, c2, f) { return c1 || c2; }
      };
    })(),

    Handsfree: function() { this.start = function(){}; this.on = function(){}; },
    THREE: typeof window.THREE !== 'undefined' ? window.THREE : {
      Scene: function() { this.add = function(){}; },
      PerspectiveCamera: function() {},
      WebGLRenderer: function() { this.setSize = function(){}; this.render = function(){}; this.domElement = document.createElement('canvas'); },
      BoxGeometry: function() {},
      MeshBasicMaterial: function() {},
      Mesh: function() {},
      AudioLoader: function() { this.load = function(){}; }
    },
    VERT: 'void main() {}',
    UPDATE_VERT: 'void main() {}',
    UPDATE_FRAG: 'void main() {}',
    println: typeof window.println !== 'undefined' ? window.println : function(...args) {},
    shorten: function(list) { if (Array.isArray(list)) { list.pop(); return list; } return []; },

    append: function(list, val) { if (Array.isArray(list)) { list.push(val); return list; } return [val]; },
    concat: function(a, b) { return (Array.isArray(a) ? a : []).concat(Array.isArray(b) ? b : []); },
    subset: function(list, start, count) { return Array.isArray(list) ? list.slice(start, count ? start + count : undefined) : []; },
    reverse: function(list) { return Array.isArray(list) ? list.reverse() : []; },
    splice: function(list, value, index) { if (Array.isArray(list)) { list.splice(index, 0, value); return list; } return [value]; },
    OSN: { noise2D: function(){return 0;}, noise3D: function(){return 0;}, noise4D: function(){return 0;} },

    world: { step: function(){}, gravity: {y: 0}, createEntity: function(){ return {}; } },

    enabledMods: [],
    isMobile: false,
    settings: {},
    langCode: 'en',
    mountControl: function(){},
    mountGrid: function(){},
    table1: [],
    w: window.innerWidth || 1080,
    leaderboardWidth: 800,
    curveTightness: function(){},
    curve: function(){},
    _angleMode: 'radians',
    masterVolume: function(v) { return v !== undefined ? v : 1.0; },
    touchX: typeof window.mouseX !== 'undefined' ? window.mouseX : 0,


    vc: typeof window.vc !== 'undefined' ? window.vc : { getColor: function() { return (typeof color === 'function' ? color(255) : '#ffffff'); }, getPalette: function() { return []; } },
    epiColors: typeof window.epiColors !== 'undefined' ? window.epiColors : { getColor: function() { return (typeof color === 'function' ? color(255) : '#ffffff'); }, getPalette: function() { return []; } },

    Canvas: typeof window.Canvas !== 'undefined' ? window.Canvas : { w: 800, h: 800, resize: function(){}, show: function(){}, hide: function(){} },

    planck: typeof window.planck !== 'undefined' ? window.planck : { World: function() { this.createBody = function(){ return { createFixture: function(){} }; }; } },
    touchY: typeof window.mouseY !== 'undefined' ? window.mouseY : 0,

    canvas: typeof window.canvas !== 'undefined' ? window.canvas : document.querySelector('canvas') || document.createElement('canvas'),

    brush: { bleed: function(){return this;}, stroke: function(){return this;}, fill: function(){return this;}, circle: function(){return this;}, rect: function(){return this;} },
    split: function(str, delim) { return typeof str === 'string' ? str.split(delim) : []; },
    CirclePacker: function() { this.add = function(){}; this.update = function(){}; },
    SkeletonBuilder: function() { this.build = function(){return {};}; this.addBone = function(){return this;}; },
    Q5: function() { return createGraphics(100, 100); },


    Tweakpane: function() { this.addInput = function(){return this;}; this.addFolder = function(){return this;}; this.on = function(){return this;}; },
    Pane: function() { this.addInput = function(){return this;}; this.addFolder = function(){return this;}; this.on = function(){return this;}; },
    csg: { subtract: function(a){return a;}, union: function(a){return a;}, intersect: function(a){return a;} },

    BI_font: 'sans-serif',
    font: 'sans-serif',
    d: 0,
    Pause: false,
    get textureOverlay() {
      if (typeof window.textureOverlay !== 'undefined') return window.textureOverlay;
      if (typeof createGraphics === 'function') {
        try { return createGraphics(100, 100); } catch(e) {}
      }
      return null;
    }
  };

  // Mock THREE.AudioLoader specifically even if THREE is defined
  if (window.THREE && typeof window.THREE.AudioLoader === 'undefined') {
    window.THREE.AudioLoader = function() { this.load = function(){}; };
  }

  // Ensure getConstant fallback for Tone.js (both AudioContext and webkitAudioContext)
  const _mockChainNode = function() {
    return {
      chain: function() { return this; },
      connect: function() { return this; },
      disconnect: function() { return this; },
      dispose: function() { return this; },
      gain: { value: 1, setValueAtTime: function() {} }
    };
  };
  ['AudioContext', 'webkitAudioContext'].forEach(ctxName => {
    if (typeof window[ctxName] === 'function' && window[ctxName].prototype) {
      window[ctxName].prototype.getConstant = window[ctxName].prototype.getConstant || function() { return _mockChainNode(); };
    }
  });

  // [FIX] Patch AudioNode prototypes with Tone.js .chain() method
  // Root cause: p5.sound.min.js embeds Tone.js which calls getConstant(1).chain(gain).
  // Tone.Context's own getConstant() returns a native AudioBufferSourceNode which has
  // .connect() but NOT .chain(). The above fallback is skipped because Tone.Context
  // already defines getConstant. So we inject .chain() directly onto AudioNode types.
  const _toneChainPolyfill = function(...nodes) {
    let current = this;
    for (const node of nodes) {
      if (current && typeof current.connect === 'function') {
        try { current.connect(node.input ? node.input : node); } catch(e) {}
      }
      current = node;
    }
    return this;
  };
  [
    typeof AudioBufferSourceNode !== 'undefined' ? AudioBufferSourceNode : null,
    typeof GainNode !== 'undefined' ? GainNode : null,
    typeof OscillatorNode !== 'undefined' ? OscillatorNode : null,
    typeof BiquadFilterNode !== 'undefined' ? BiquadFilterNode : null,
    typeof DelayNode !== 'undefined' ? DelayNode : null,
    typeof DynamicsCompressorNode !== 'undefined' ? DynamicsCompressorNode : null,
    typeof WaveShaperNode !== 'undefined' ? WaveShaperNode : null,
    typeof ConvolverNode !== 'undefined' ? ConvolverNode : null,
    typeof ConstantSourceNode !== 'undefined' ? ConstantSourceNode : null,
    typeof StereoPannerNode !== 'undefined' ? StereoPannerNode : null,
  ].forEach(NodeClass => {
    if (NodeClass && NodeClass.prototype && !NodeClass.prototype.chain) {
      NodeClass.prototype.chain = _toneChainPolyfill;
    }
  });
  // Also patch the base AudioNode prototype if available (catches all subclasses)
  if (typeof AudioNode !== 'undefined' && AudioNode.prototype && !AudioNode.prototype.chain) {
    AudioNode.prototype.chain = _toneChainPolyfill;
  }

  // Fallback for tone/p5.sound audio context wrappers
  if (typeof p5 !== 'undefined') {
    p5.prototype._angleMode = p5.prototype._angleMode || 'radians';
  }


  Object.keys(fallbackVars).forEach(vName => {
    if (typeof window[vName] === 'undefined') {
      try {
        Object.defineProperty(window, vName, {
          get: function() { return fallbackVars[vName]; },
          set: function(val) { fallbackVars[vName] = val; },
          configurable: true
        });
      } catch(e) {
        window[vName] = fallbackVars[vName];
      }
    }
  });



  // Inject OPC Mock APIs (OpenProcessing Control Library)
  if (typeof window.OPC === 'undefined') {
    const _opcDummy = function() { return window.OPC; };
    const _opcHandler = {
      get: function(target, prop) {
        if (prop in target) return target[prop];
        if (['slider', 'toggle', 'color', 'select', 'text', 'palette', 'range'].includes(prop)) {
          return function(name, value) {
            if (name && typeof value !== 'undefined' && typeof window[name] === 'undefined') {
              window[name] = value;
            }
            return window.OPC;
          };
        }
        return function() { return window.OPC; };
      }
    };
    window.OPC = new Proxy({
      slider: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
      button: function() { return window.OPC; },
      toggle: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
      color: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
      select: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
      text: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
      title: function() { return window.OPC; },
      header: function() { return window.OPC; },
      separator: function() { return window.OPC; },
      collapsed: function() { return window.OPC; },
      bezier: function() { return window.OPC; },
      setGlobal: function(name, value) { if (name) window[name] = value; }
    }, _opcHandler);
  }

  // Inject Processing Matrix Aliases (pushMatrix -> push, popMatrix -> pop)
  ['pushMatrix', 'popMatrix', 'pushStyle', 'popStyle'].forEach(alias => {
    const target = alias.startsWith('pop') ? 'pop' : 'push';
    if (typeof window[alias] === 'undefined') {
      window[alias] = function(...args) {
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && ((p5.activeInstances && p5.activeInstances[0]) || p5.instance));
        if (inst && typeof inst[target] === 'function') {
          return inst[target].apply(inst, args);
        } else if (typeof window[target] === 'function') {
          return window[target].apply(window, args);
        }
      };
    }
  });

  // Inject Scribble Mock APIs
  if (typeof window.Scribble === 'undefined') {
    window.Scribble = function() {
      this.roughness = 1;
      this.bowing = 1;
      this.maxOffset = 2;
      this.numEllipseSteps = 10;
      this.scribbleLine = function(x1, y1, x2, y2) { if (typeof line === 'function') line(x1, y1, x2, y2); };
      this.scribbleCurve = function(x1, y1, x2, y2, x3, y3, x4, y4) { if (typeof bezier === 'function') bezier(x1, y1, x2, y2, x3, y3, x4, y4); };
      this.scribbleRect = function(x, y, w, h) { if (typeof rect === 'function') rect(x, y, w, h); };
      this.scribbleRoundedRect = function(x, y, w, h, r) { if (typeof rect === 'function') rect(x, y, w, h, r); };
      this.scribbleEllipse = function(x, y, w, h) { if (typeof ellipse === 'function') ellipse(x, y, w, h); };
      this.scribbleFilling = function(x, y, w, h) {};
    };
    var Scribble = window.Scribble;
  }
  if (typeof p5 !== 'undefined') {
    p5.Scribble = window.Scribble;
    if (p5.prototype && !p5.prototype.Scribble) p5.prototype.Scribble = window.Scribble;
  }

  // Inject p5.pattern Mock API stub to prevent 'pattern.patternColors is not a function'
  var _mockPatternFunc = function() { return function() { return _mockPatternFunc; }; };
  _mockPatternFunc.patternColors = function() { return _mockPatternFunc; };
  _mockPatternFunc.patternAngle = function() { return _mockPatternFunc; };
  _mockPatternFunc.patternScale = function() { return _mockPatternFunc; };
  if (typeof window.pattern === 'undefined') {
    window.pattern = _mockPatternFunc;
  }
  if (typeof p5 !== 'undefined' && p5.prototype) {
    if (!p5.prototype.pattern) p5.prototype.pattern = _mockPatternFunc;
    if (!p5.prototype.patternColors) p5.prototype.patternColors = function() { return this; };
    if (!p5.prototype.patternAngle) p5.prototype.patternAngle = function() { return this; };
    if (!p5.prototype.patternScale) p5.prototype.patternScale = function() { return this; };
  }
  if (typeof p5 !== 'undefined' && p5.Graphics && p5.Graphics.prototype) {
    if (!p5.Graphics.prototype.pattern) p5.Graphics.prototype.pattern = _mockPatternFunc;
    if (!p5.Graphics.prototype.patternColors) p5.Graphics.prototype.patternColors = function() { return this; };
    if (!p5.Graphics.prototype.patternAngle) p5.Graphics.prototype.patternAngle = function() { return this; };
    if (!p5.Graphics.prototype.patternScale) p5.Graphics.prototype.patternScale = function() { return this; };
  }



  // Polyfill p5.Font prototype methods for p5.js v2 font API compatibility
  if (typeof p5 !== 'undefined' && p5.Font && p5.Font.prototype) {
    p5.Font.prototype.textToPoints = p5.Font.prototype.textToPoints || function() { return []; };
    p5.Font.prototype.textBounds = p5.Font.prototype.textBounds || function() { return { x: 0, y: 0, w: 0, h: 0, advance: 0 }; };
  }
  // Ensure loadFont wrapper injects font stubs safely
  if (typeof p5 !== 'undefined' && p5.prototype && p5.prototype.loadFont) {
    const origLoadFont = p5.prototype.loadFont;
    p5.prototype.loadFont = function(path, successCallback, failureCallback) {
      const wrapSuccess = function(font) {
        if (font) {
          font.textToPoints = font.textToPoints || function() { return []; };
          font.textBounds = font.textBounds || function() { return { x: 0, y: 0, w: 0, h: 0, advance: 0 }; };
        }
        if (typeof successCallback === 'function') successCallback(font);
      };
      try {
        const res = origLoadFont.call(this, path, wrapSuccess, failureCallback);
        if (res) {
          res.textToPoints = res.textToPoints || function() { return []; };
          res.textBounds = res.textBounds || function() { return { x: 0, y: 0, w: 0, h: 0, advance: 0 }; };
        }
        return res;
      } catch(e) {
        var dummyFont = { textToPoints: function() { return []; }, textBounds: function() { return { x: 0, y: 0, w: 0, h: 0, advance: 0 }; } };
        if (typeof successCallback === 'function') successCallback(dummyFont);
        return dummyFont;
      }
    };
  }


  // Polyfill p5.Matrix prototype methods for p5.js v2 matrix API compatibility

  if (typeof p5 !== 'undefined' && p5.Matrix && p5.Matrix.prototype) {
    if (!p5.Matrix.prototype.rotate) p5.Matrix.prototype.rotate = function() { return this; };
    if (!p5.Matrix.prototype.rotateX) p5.Matrix.prototype.rotateX = function() { return this; };
    if (!p5.Matrix.prototype.rotateY) p5.Matrix.prototype.rotateY = function() { return this; };
    if (!p5.Matrix.prototype.rotateZ) p5.Matrix.prototype.rotateZ = function() { return this; };
  }

  // Prevent friendly errors check crashes

  if (typeof p5 !== 'undefined') {
    p5._friendlyError = function() {};
  }

  // Mock Navigator Beacon API
  if (navigator && !navigator.sendBeacon) {
    navigator.sendBeacon = function() { return true; };
  } else if (navigator) {
    const origSendBeacon = navigator.sendBeacon;
    navigator.sendBeacon = function(url, data) {
      try {
        return origSendBeacon.apply(this, arguments);
      } catch(e) {
        console.warn('sendBeacon failed:', e);
        return true;
      }
    };
  }

  // ============================================================
  // Additional Mock/Stubs for crash-immune sandbox execution
  // ============================================================

  // 13. loadShader / createShader mock — prevents "Cannot read 'setUniform' of undefined" (15x)
  if (typeof p5 !== 'undefined' && p5.prototype) {
    if (!p5.prototype._origLoadShader) {
      p5.prototype._origLoadShader = p5.prototype.loadShader;
    }
    p5.prototype.loadShader = function(vertPath, fragPath, successCallback, failureCallback) {
      console.log('[P5_COMPAT] loadShader hijacked for:', vertPath, fragPath);
      var mockShader = {
        _isMockShader: true,
        setUniform: function() { return this; },
        set: function() { return this; },
        isStrokeShader: function() { return false; },
        isTextureShader: function() { return false; },
        bindShader: function() {},
        unbindShader: function() {},
        _vertSrc: 'void main() { gl_Position = vec4(0.0); }',
        _fragSrc: 'precision mediump float; void main() { gl_FragColor = vec4(0.0,0.0,0.0,1.0); }',
        then: function(resolve) { if (resolve) setTimeout(() => resolve(this), 0); return this; }
      };
      if (successCallback) setTimeout(() => { try { successCallback(mockShader); } catch(e) {} }, 0);
      return mockShader;
    };
    if (!p5.prototype.createShader || p5.prototype.createShader._isMockPatched) {
      // Only wrap if not already patched
    } else {
      var origCreateShader = p5.prototype.createShader;
      p5.prototype.createShader = function(vert, frag) {
        try {
          var shader = origCreateShader.call(this, vert, frag);
          if (shader) return shader;
        } catch(e) {
          console.warn('[P5_COMPAT] createShader failed, returning mock:', e);
        }
        return {
          _isMockShader: true,
          setUniform: function() { return this; },
          set: function() { return this; },
          isStrokeShader: function() { return false; },
          isTextureShader: function() { return false; },
          bindShader: function() {},
          unbindShader: function() {}
        };
      };
      p5.prototype.createShader._isMockPatched = true;
    }
  }

  // 14. loadJSON / loadStrings / loadTable failure fallback — prevents "Cannot read 'data'/'0'/'getRowCount' of undefined" (39+ errors)
  if (typeof p5 !== 'undefined' && p5.prototype) {
    var origLoadJSON = p5.prototype.loadJSON;
    if (origLoadJSON) {
      p5.prototype.loadJSON = function(path, successCallback, failureCallback) {
        var wrappedFailure = function(err) {
          console.warn('[PreloadGuard] loadJSON failed for: ' + path + ', using empty object');
          var fallback = {};
          if (successCallback) successCallback(fallback);
          if (failureCallback) failureCallback(err);
          return fallback;
        };
        try {
          return origLoadJSON.call(this, path, successCallback, wrappedFailure);
        } catch(e) {
          return wrappedFailure(e);
        }
      };
    }

    var origLoadStrings = p5.prototype.loadStrings;
    if (origLoadStrings) {
      p5.prototype.loadStrings = function(path, successCallback, failureCallback) {
        var wrappedFailure = function(err) {
          console.warn('[PreloadGuard] loadStrings failed for: ' + path + ', using empty array');
          var fallback = [];
          if (successCallback) successCallback(fallback);
          if (failureCallback) failureCallback(err);
          return fallback;
        };
        try {
          return origLoadStrings.call(this, path, successCallback, wrappedFailure);
        } catch(e) {
          return wrappedFailure(e);
        }
      };
    }

    var origLoadTable = p5.prototype.loadTable;
    if (origLoadTable) {
      p5.prototype.loadTable = function(path, optionsOrCb) {
        var args = Array.prototype.slice.call(arguments);
        // Find the failure callback position
        var lastArg = args[args.length - 1];
        var hasCb = typeof lastArg === 'function';
        var wrappedFailure = function(err) {
          console.warn('[PreloadGuard] loadTable failed for: ' + path + ', using mock table');
          var mockTable = {
            columns: [],
            rows: [],
            getRowCount: function() { return 0; },
            getColumnCount: function() { return 0; },
            getRow: function() { return { get: function() { return ''; }, getNum: function() { return 0; } }; },
            getColumn: function() { return []; },
            getObject: function() { return {}; },
            getArray: function() { return []; },
            getString: function() { return ''; },
            getNum: function() { return 0; },
            findRow: function() { return null; },
            findRows: function() { return []; },
            matchRow: function() { return null; },
            matchRows: function() { return []; }
          };
          return mockTable;
        };
        try {
          return origLoadTable.apply(this, args);
        } catch(e) {
          return wrappedFailure(e);
        }
      };
    }
  }

  // 15. Global polyfills for missing p5 functions (int, curvePoint, size, etc.)
  if (typeof window.int === 'undefined') {
    window.int = function(n, radix) {
      if (typeof n === 'number') return Math.floor(n);
      if (typeof n === 'boolean') return n ? 1 : 0;
      if (typeof n === 'string') return parseInt(n, radix || 10) || 0;
      if (Array.isArray(n)) return n.map(function(v) { return window.int(v, radix); });
      return 0;
    };
    if (typeof p5 !== 'undefined' && p5.prototype && !p5.prototype.int) {
      p5.prototype.int = window.int;
    }
  }

  if (typeof window.size === 'undefined') {
    window.size = function(w, h, mode) {
      if (typeof createCanvas === 'function') {
        try { return createCanvas(w, h, mode); } catch(e) {}
      }
    };
  }
  if (typeof window.curvePoint === 'undefined') {
    window.curvePoint = function(a, b, c, d, t) {
      var t2 = t * t, t3 = t2 * t;
      return 0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
    };
  }
  if (typeof window.curveTangent === 'undefined') {
    window.curveTangent = function(a, b, c, d, t) {
      var t2 = t * t;
      return 0.5 * ((-a + c) + 2 * (2 * a - 5 * b + 4 * c - d) * t + 3 * (-a + 3 * b - 3 * c + d) * t2);
    };
  }

  // 15b. Restore missing getTexture on RendererGL
  if (typeof p5 !== 'undefined' && p5.RendererGL && p5.RendererGL.prototype) {
    if (!p5.RendererGL.prototype.getTexture) {
      p5.RendererGL.prototype.getTexture = function(img) {
        return { bind: function() {}, unbind: function() {}, update: function() {} };
      };
    }
  }




  // 16. select() / selectAll() / createElement() DOM stubs
  if (typeof p5 !== 'undefined' && p5.prototype) {
    var _ensureDomStub = function(el) {
      if (!el) return el;
      if (typeof el.style === 'object' && typeof el.style !== 'function') {
        // Wrap native style as callable for p5.Element compatibility
        var nativeStyle = el.style;
        var styleFunc = function(prop, val) {
          if (arguments.length === 0) return nativeStyle;
          if (arguments.length === 1) return nativeStyle[prop] || '';
          nativeStyle.setProperty(prop, val);
          return el;
        };
        // Don't overwrite if already a function (from createDummyDom)
      }
      ['position', 'size', 'parent', 'class', 'addClass', 'removeClass', 'show', 'hide',
       'html', 'attribute', 'removeAttribute', 'changed', 'input', 'mousePressed',
       'mouseOver', 'mouseOut', 'touchStarted', 'dragOver', 'option', 'selected', 'disable', 'enable', 'css'].forEach(function(m) {
        if (typeof el[m] !== 'function') {
          el[m] = function() { return el; };
        }
      });


      if (typeof el.value !== 'function') {
        var storedVal = el.getAttribute ? (el.getAttribute('value') || '') : '';
        el.value = function(v) {
          if (v === undefined) return storedVal;
          storedVal = v;
          return el;
        };
      }
      return el;
    };

    if (!p5.prototype.select || typeof p5.prototype.select !== 'function') {
      p5.prototype.select = function(selector) {
        try {
          var el = document.querySelector(selector);
          return el ? _ensureDomStub(el) : null;
        } catch(e) { return null; }
      };
    }
    if (!p5.prototype.selectAll || typeof p5.prototype.selectAll !== 'function') {
      p5.prototype.selectAll = function(selector) {
        try {
          var els = document.querySelectorAll(selector);
          return Array.from(els).map(function(el) { return _ensureDomStub(el); });
        } catch(e) { return []; }
      };
    }
    if (!p5.prototype.createElement || typeof p5.prototype.createElement !== 'function') {
      p5.prototype.createElement = function(tag, content) {
        var el = document.createElement(tag || 'div');
        if (content) el.innerHTML = content;
        el.style.setProperty('display', 'none', 'important');
        _ensureDomStub(el);
        if (document.body) document.body.appendChild(el);
        return el;
      };
    }

    // Expose globally too
    if (typeof window.select === 'undefined') {
      window.select = function(selector) {
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && p5.instance);
        if (inst && typeof inst.select === 'function') return inst.select(selector);
        try { var el = document.querySelector(selector); return el ? _ensureDomStub(el) : null; } catch(e) { return null; }
      };
    }
    if (typeof window.selectAll === 'undefined') {
      window.selectAll = function(selector) {
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && p5.instance);
        if (inst && typeof inst.selectAll === 'function') return inst.selectAll(selector);
        try { return Array.from(document.querySelectorAll(selector)).map(_ensureDomStub); } catch(e) { return []; }
      };
    }
    if (typeof window.createElement === 'undefined') {
      window.createElement = function(tag, content) {
        var inst = window._p5Instance || (typeof p5 !== 'undefined' && p5.instance);
        if (inst && typeof inst.createElement === 'function') return inst.createElement(tag, content);
        var el = document.createElement(tag || 'div');
        if (content) el.innerHTML = content;
        _ensureDomStub(el);
        return el;
      };
    }
  }

  // 17. p5.prototype.loadSVG stub
  if (typeof p5 !== 'undefined' && p5.prototype && !p5.prototype.loadSVG) {
    p5.prototype.loadSVG = function(path, successCallback, failureCallback) {
      console.warn('[P5_COMPAT] loadSVG is not available, returning mock');
      var mockSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      mockSvg.setAttribute('width', '100');
      mockSvg.setAttribute('height', '100');
      if (successCallback) setTimeout(function() { successCallback(mockSvg); }, 0);
      return mockSvg;
    };
  }

  // 18. Additional p5.sound mock classes (Delay, Reverb, Filter, Noise, etc.)
  if (typeof p5 !== 'undefined') {
    var _soundChainStub = function() {
      return { connect: function(){return this;}, disconnect: function(){return this;}, chain: function(){return this;}, dispose: function(){return this;}, process: function(){return this;}, amp: function(){return this;}, drywet: function(){return this;}, set: function(){return this;} };
    };
    if (!p5.Delay) p5.Delay = function() { return _soundChainStub(); };
    if (!p5.Reverb) p5.Reverb = function() { return _soundChainStub(); };
    if (!p5.Filter) p5.Filter = function() { var s = _soundChainStub(); s.freq = function(){return this;}; s.res = function(){return this;}; s.setType = function(){return this;}; return s; };
    if (!p5.LowPass) p5.LowPass = p5.Filter;
    if (!p5.HighPass) p5.HighPass = p5.Filter;
    if (!p5.BandPass) p5.BandPass = p5.Filter;
    if (!p5.Noise) p5.Noise = function() { return { start: function(){return this;}, stop: function(){return this;}, connect: function(){return this;}, disconnect: function(){return this;}, amp: function(){return this;}, pan: function(){return this;} }; };
    if (!p5.Gain) p5.Gain = function() { return _soundChainStub(); };
    if (!p5.Compressor) p5.Compressor = function() { return _soundChainStub(); };
    if (!p5.Panner3D) p5.Panner3D = function() { return _soundChainStub(); };
    if (!p5.EQ) p5.EQ = function() { var s = _soundChainStub(); s.bands = []; return s; };
    if (!p5.Convolver) p5.Convolver = function() { return _soundChainStub(); };
    if (!p5.Phrase) p5.Phrase = function() { return { sequence: [] }; };
    if (!p5.Part) p5.Part = function() { return { start: function(){}, stop: function(){}, addPhrase: function(){}, loop: function(){} }; };
    if (!p5.Score) p5.Score = function() { return { start: function(){}, stop: function(){}, loop: function(){} }; };
    if (!p5.SoundRecorder) p5.SoundRecorder = function() { return { record: function(){}, stop: function(){}, save: function(){} }; };
    if (!p5.PeakDetect) p5.PeakDetect = function() { return { update: function(){}, onPeak: function(){}, isDetected: false }; };
    if (!p5.MonoSynth) p5.MonoSynth = function() { return { play: function(){return this;}, noteAttack: function(){return this;}, noteRelease: function(){return this;}, setADSR: function(){return this;}, connect: function(){return this;}, disconnect: function(){return this;} }; };
    if (!p5.PolySynth) p5.PolySynth = function() { return { play: function(){return this;}, noteAttack: function(){return this;}, noteRelease: function(){return this;}, setADSR: function(){return this;}, connect: function(){return this;}, disconnect: function(){return this;}, notes: {} }; };
  }

  // 19. Global unhandledrejection absorber — prevents sandbox crash on unhandled promise rejections
  window.addEventListener('unhandledrejection', function(event) {
    if (event && event.reason) {
      var msg = String(event.reason);
      // Absorb known non-fatal p5/addon errors to keep sandbox running
      var absorbPatterns = [
        "Cannot read properties of undefined",
        "Cannot read properties of null",
        "Cannot set property",
        "is not a function",
        "is not defined",
        "has already been declared",
        "Cannot redefine property",
        "which has only a getter",
        "Cannot create property",
        "is not valid JSON",
        "JSON.parse",
        "Unable to create depth textures"



      ];
      for (var i = 0; i < absorbPatterns.length; i++) {
        if (msg.indexOf(absorbPatterns[i]) !== -1) {
          // Quietly absorb non-fatal unhandled rejections without cluttering log output
          event.preventDefault();
          return;
        }
      }
    }
  });
}

// ============================================================
// p5.js preload guardrail: wrap loadImage/loadFont to prevent
// preload() from hanging when assets fail to load
// ============================================================
(function() {
  if (typeof p5 === 'undefined' || !p5.prototype) return;
  
  // Wrap loadImage to gracefully handle missing images
  var origLoadImage = p5.prototype.loadImage;
  if (origLoadImage) {
    var _createSafePlaceholder = function(self) {
      var placeholder;
      try {
        placeholder = self.createImage(4, 4);
        placeholder.loadPixels();
        for (var i = 0; i < placeholder.pixels.length; i++) placeholder.pixels[i] = 0;
        placeholder.updatePixels();
      } catch(e) {
        // If createImage fails, create a raw mock with all necessary properties
        placeholder = {
          width: 4, height: 4,
          pixels: new Uint8ClampedArray(4 * 4 * 4),
          canvas: document.createElement('canvas'),
          drawingContext: null,
          _isMockImage: true,
          loadPixels: function() {},
          updatePixels: function() {},
          resize: function(w, h) { this.width = w || this.width; this.height = h || this.height; return this; },
          get: function(x, y, w, h) {
            if (arguments.length <= 2) return [0, 0, 0, 0];
            return _createSafePlaceholder(self);
          },
          set: function() {},
          copy: function() {},
          mask: function() {},
          filter: function() {},
          save: function() {},
          blend: function() {},
          then: function(resolve) { if (resolve) setTimeout(function() { resolve(placeholder); }, 0); return this; }
        };
        placeholder.canvas.width = 4;
        placeholder.canvas.height = 4;
        placeholder.drawingContext = placeholder.canvas.getContext('2d');
      }
      // Ensure all critical properties exist even on real p5.Image
      if (placeholder && typeof placeholder.resize !== 'function') {
        placeholder.resize = function(w, h) {
          if (typeof this.width !== 'undefined') this.width = w || this.width;
          if (typeof this.height !== 'undefined') this.height = h || this.height;
          return this;
        };
      }
      if (placeholder && typeof placeholder.get !== 'function') {
        placeholder.get = function() { return [0, 0, 0, 0]; };
      }
      if (placeholder && typeof placeholder.loadPixels !== 'function') {
        placeholder.loadPixels = function() {};
      }
      return placeholder;
    };
    
    p5.prototype.loadImage = function(path, successCallback, failureCallback) {
      var self = this;
      var wrappedFailure = function(err) {
        console.warn('[PreloadGuard] loadImage failed for: ' + path + ', using placeholder');
        var placeholder = _createSafePlaceholder(self);
        if (successCallback) successCallback(placeholder);
        if (failureCallback) failureCallback(err);
        return placeholder;
      };
      try {
        var result = origLoadImage.call(this, path, successCallback, wrappedFailure);
        // Ensure the returned object always has critical properties
        // (p5.js v2 may return a Promise or a p5.Image with delayed loading)
        if (result && typeof result === 'object') {
          if (typeof result.width === 'undefined') result.width = 1;
          if (typeof result.height === 'undefined') result.height = 1;
          if (typeof result.resize !== 'function') result.resize = function(w, h) { this.width = w; this.height = h; return this; };
          if (typeof result.loadPixels !== 'function') result.loadPixels = function() {};
          if (typeof result.get !== 'function') result.get = function() { return [0, 0, 0, 0]; };
        }
        return result || _createSafePlaceholder(self);
      } catch(e) {
        return wrappedFailure(e);
      }
    };
  }

  
  // Wrap loadFont to gracefully handle missing fonts
  var origLoadFont = p5.prototype.loadFont;
  if (origLoadFont) {
    p5.prototype.loadFont = function(path, successCallback, failureCallback) {
      var wrappedFailure = function(err) {
        console.warn('[PreloadGuard] loadFont failed for: ' + path + ', using sans-serif fallback');
        if (failureCallback) failureCallback(err);
      };
      try {
        var fRes = origLoadFont.call(this, path, successCallback, wrappedFailure);
        if (fRes && typeof fRes === 'object') {
          if (typeof fRes.textToPoints !== 'function') fRes.textToPoints = function() { return []; };
          if (typeof fRes.textBounds !== 'function') fRes.textBounds = function() { return { x: 0, y: 0, w: 0, h: 0, advance: 0 }; };
        }
        return fRes;
      } catch(e) {
        wrappedFailure(e);
        return { textToPoints: function() { return []; }, textBounds: function() { return { x: 0, y: 0, w: 0, h: 0 }; } };
      }
    };
  }

  
  // Wrap loadModel to gracefully handle missing 3D models
  var origLoadModel = p5.prototype.loadModel;
  if (origLoadModel) {
    p5.prototype.loadModel = function(path, successCallback, failureCallback) {
      var wrappedFailure = function(err) {
        console.warn('[PreloadGuard] loadModel failed for: ' + path);
        if (failureCallback) failureCallback(err);
      };
      try {
        return origLoadModel.call(this, path, successCallback, wrappedFailure, '.obj');
      } catch(e) {
        wrappedFailure(e);
        return null;
      }
    };
  }

  // Wrap p5.prototype.get to gracefully handle undefined/unloaded image contexts
  var origGet = p5.prototype.get;
  if (origGet) {
    var p5GetWrapper = function(...args) {
      // Create a robust fallback object with a mock vertices property
      var createFallback = function(self) {
        var dummy = null;
        try {
          dummy = self && typeof self.createImage === 'function' ? self.createImage(1, 1) : null;
        } catch(e) {}
        if (!dummy && window._p5Instance) {
          try { dummy = window._p5Instance.createImage(1, 1); } catch(e) {}
        }
        if (!dummy) {
          // Absolute fallback plain object to prevent "reading vertices" crash
          dummy = {
            width: 1,
            height: 1,
            pixels: [0, 0, 0, 0],
            loadPixels: function() {},
            updatePixels: function() {},
            get: function() { return [0, 0, 0, 255]; },
            vertices: [] // Restores the missing array
          };
        } else {
          dummy.loadPixels();
          dummy.vertices = dummy.vertices || [];
        }
        return dummy;
      };

      try {
        var res = origGet.apply(this || window._p5Instance, args);
        if (res && typeof res === 'object') {
          res.vertices = res.vertices || [];
        }
        return res;
      } catch(e) {
        console.warn('[PreloadGuard] get() errored, using fallback: ', e);
        return createFallback(this);
      }
    };

    p5.prototype.get = p5GetWrapper;

    // Direct window global method override for modular/legacy scopes
    try {
      Object.defineProperty(window, 'get', {
        get: function() {
          return p5GetWrapper;
        },
        set: function(val) {
          if (window._p5Instance) {
            window._p5Instance.get = val;
          }
        },
        configurable: true
      });
    } catch(e) {}
  }

  // Dynamic Background Hijacking & Smart Adapter
  if (p5.prototype) {
    const originalBackground = p5.prototype.background;
    let lastR = 10, lastG = 10, lastB = 12;
    p5.prototype.background = function(...args) {
      if (window.currentChordColor) {
        // Check if the original background call is a static color (black, white, simple grayscale, etc.)
        let isStatic = false;
        if (args.length === 1) {
          let a = args[0];
          if (a === 0 || a === 255 || a === 'white' || a === 'black' || a === '#000' || a === '#000000' || a === '#fff' || a === '#ffffff') {
            isStatic = true;
          }
        } else if (args.length === 3) {
          let r = args[0], g = args[1], b = args[2];
          if ((r === 0 && g === 0 && b === 0) || (r === 255 && g === 255 && b === 255)) {
            isStatic = true;
          }
        }
        
        if (isStatic) {
          let hex = window.currentChordColor;
          // Parse hex color (standard #RRGGBB)
          let targetR = parseInt(hex.slice(1, 3), 16) || 10;
          let targetG = parseInt(hex.slice(3, 5), 16) || 10;
          let targetB = parseInt(hex.slice(5, 7), 16) || 12;
          
          // Modulate based on audioLow/beatEnergy to create a gentle dynamic breathing background
          let energy = window.audioLow || 0.5;
          let scale = 0.12 + 0.28 * energy; // Pulse dark colors in sync with bass
          
          // If original background was white/bright, scale it to bright range
          if (args[0] === 255 || args[0] === 'white' || (args[0] === 255 && args[1] === 255 && args[2] === 255)) {
            scale = 0.72 + 0.28 * energy;
          }
          
          let bgR = Math.round(targetR * scale);
          let bgG = Math.round(targetG * scale);
          let bgB = Math.round(targetB * scale);
          
          // Photosensitive Safe Mode: Suppress high-frequency beat pulses & apply temporal low-pass filter
          if (window.photosensitiveSafe) {
            let safeScale = 0.22;
            if (args[0] === 255 || args[0] === 'white' || (args[0] === 255 && args[1] === 255 && args[2] === 255)) {
              safeScale = 0.65;
            }
            let rawSafeR = Math.round(targetR * safeScale);
            let rawSafeG = Math.round(targetG * safeScale);
            let rawSafeB = Math.round(targetB * safeScale);
            
            // Temporal exponential low-pass filter (coefficient 0.05)
            lastR = lastR + (rawSafeR - lastR) * 0.05;
            lastG = lastG + (rawSafeG - lastG) * 0.05;
            lastB = lastB + (rawSafeB - lastB) * 0.05;
            
            bgR = Math.round(lastR);
            bgG = Math.round(lastG);
            bgB = Math.round(lastB);
          }
          
          let alpha = args.length === 2 ? args[1] : (args.length === 4 ? args[3] : undefined);
          if (alpha !== undefined) {
            return originalBackground.call(this, bgR, bgG, bgB, alpha);
          }
          return originalBackground.call(this, bgR, bgG, bgB);
        }
      }
      return originalBackground.apply(this, args);
    };
  }
})();

// ============================================================
// Loading timeout watchdog: detects and recovers from stuck loading screens
// ============================================================
(function() {
  var LOADING_TIMEOUT_MS = 8000;  // 8 seconds max loading time
  var CHECK_INTERVAL_MS = 500;
  var loadingWatchdogTimer = null;
  var startTime = Date.now();
  
  function isStuckOnLoading() {
    var body = document.body;
    if (!body) return false;
    
    var canvas = document.querySelector('canvas');
    // Include #p5_loading which is the default p5.js loading screen element
    var loadingEls = document.querySelectorAll('.loading, #loading, #p5_loading, [class*="loader"], [class*="spinner"]');
    var bodyText = (body.innerText || '').toLowerCase().trim();
    
    // Pattern 1: No canvas rendered yet
    if (!canvas && (Date.now() - startTime) > LOADING_TIMEOUT_MS) {
      console.warn('[LoadingWatchdog] No canvas found after ' + LOADING_TIMEOUT_MS + 'ms');
      return true;
    }
    
    // Pattern 2: Loading overlay still visible (including p5_loading)
    if (loadingEls.length > 0) {
      for (var i = 0; i < loadingEls.length; i++) {
        var el = loadingEls[i];
        var style = window.getComputedStyle(el);
        if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0) {
          console.warn('[LoadingWatchdog] Loading overlay still visible: ', el.id || el.className);
          return true;
        }
      }
    }
    
    // Pattern 3: Body only shows "loading" text
    if (bodyText === 'loading' || bodyText === 'loading...' || bodyText === 'loading…') {
      return true;
    }
    
    return false;
  }
  
  function forceUnstick() {
    console.warn('[LoadingWatchdog] Attempting to force-unstick the sketch...');
    
    // Remove all loading overlays including #p5_loading
    var loadingEls = document.querySelectorAll('.loading, #loading, #p5_loading, [class*="loader"], [class*="spinner"]');
    for (var i = 0; i < loadingEls.length; i++) {
      loadingEls[i].style.display = 'none';
    }
    
    // Force p5.js to skip preload and proceed to setup
    // p5 uses an internal _preloadCount; when it reaches 0, _setup is called
    try {
      // Method 1: Find the global p5 instance and force it through
      var instances = window._p5Instance ? [window._p5Instance] : [];
      // Also check for p5 instances stored in the global scope
      if (instances.length === 0 && typeof p5 !== 'undefined' && p5.instance) {
        instances.push(p5.instance);
      }
      
      for (var j = 0; j < instances.length; j++) {
        var inst = instances[j];
        if (inst && inst._setupDone === false) {
          console.warn('[LoadingWatchdog] Forcing p5 preload completion...');
          // Reset the preload counter to force setup
          inst._pixelDensity = inst._pixelDensity || 1;
          if (typeof inst._decrementPreload === 'function') {
            for (var k = 0; k < 20; k++) {
              try { inst._decrementPreload(); } catch(e) { break; }
            }
          } else {
            inst._setupDone = true;
            try { inst._setup(); } catch(e) { console.warn('[LoadingWatchdog] _setup error:', e); }
            try { inst._draw(); } catch(e) { console.warn('[LoadingWatchdog] _draw error:', e); }
          }
        }
      }
      // If still no canvas created, force create a fallback canvas so watchdog passes
      if (!document.querySelector('canvas') && typeof createCanvas === 'function') {
        try {
          createCanvas(window.innerWidth || 800, window.innerHeight || 600);
          console.warn('[LoadingWatchdog] Created emergency fallback canvas');
        } catch(e) {}
      }
    } catch(e) {
      console.warn('[LoadingWatchdog] Force p5 setup failed:', e);
    }

    
    // Signal to Python side that loading timed out
    window.__loading_timed_out = true;
  }
  
  // Start watchdog after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      startTime = Date.now();
    });
  }
  
  loadingWatchdogTimer = setInterval(function() {
    if ((Date.now() - startTime) > LOADING_TIMEOUT_MS) {
      if (isStuckOnLoading()) {
        forceUnstick();
      }
      clearInterval(loadingWatchdogTimer);
    }
  }, CHECK_INTERVAL_MS);
  
  // Also clear the watchdog once a canvas with content is confirmed
  var successCheckTimer = setInterval(function() {
    var canvas = document.querySelector('canvas');
    if (canvas && canvas.width > 0 && canvas.height > 0) {
      // Also hide p5_loading if canvas exists
      var p5Loading = document.getElementById('p5_loading');
      if (p5Loading) p5Loading.style.display = 'none';
      clearInterval(loadingWatchdogTimer);
      clearInterval(successCheckTimer);
    }
    if ((Date.now() - startTime) > LOADING_TIMEOUT_MS + 2000) {
      clearInterval(successCheckTimer);
    }
  }, CHECK_INTERVAL_MS);

  // Universal Offline / Real-time Frame Parameters & Audio Feature Injection Bridge
  window.setFrameParams = function(t, isBeat, beatEnergy, audioLow, audioMid, audioHigh, moduleActiveTimeSec) {
    let activeTime = (typeof moduleActiveTimeSec !== 'undefined' && moduleActiveTimeSec !== null) ? moduleActiveTimeSec : t;
    window.custom_time_ms = activeTime * 1000;
    window.globalTime = t;
    window.moduleActiveTime = activeTime;
    window.time = activeTime;
    window.sub_bass = audioLow;
    window.bass_ratio = audioLow;
    window.audioLow = audioLow;
    window.audioMid = audioMid;
    window.audioHigh = audioHigh;
    window.percussive = beatEnergy;
    window.energy = (audioLow + audioMid + audioHigh) / 3;
    window.beatEnergy = beatEnergy;
    window.isBeat = isBeat;
    
    let w = typeof width !== 'undefined' ? width : 1280;
    let h = typeof height !== 'undefined' ? height : 720;
    
    if (isBeat) {
      window.simulatedMouseX = Math.random() * w;
      window.simulatedMouseY = Math.random() * h;
      if (typeof mousePressed === 'function') { try { mousePressed(); } catch(e) {} }
      if (typeof mouseClicked === 'function') { try { mouseClicked(); } catch(e) {} }
    } else {
      window.simulatedMouseX = w / 2 + (audioLow - 0.5) * w * 0.6;
      window.simulatedMouseY = h / 2 + (audioMid - 0.5) * h * 0.6;
    }
    
    if (typeof draw === 'function') {
      try { draw(); } catch(e) {}
    } else if (typeof redraw === 'function') {
      try { redraw(); } catch(e) {}
    }
    return "ok";
  };
})();
"""

MOCK_AUDIO_JS = MOCK_NATIVE_AUDIO_JS + "\n" + MOCK_P5_JS

class AppleScriptDialogThread(QThread):
    finished_dialog = pyqtSignal(str)
    
    def __init__(self, script):
        super().__init__()
        self.script = script
        
    def run(self):
        import subprocess
        try:
            proc = subprocess.run(['osascript', '-e', self.script], capture_output=True, text=True)
            if proc.returncode == 0:
                self.finished_dialog.emit(proc.stdout.strip())
            elif proc.returncode == 128:
                self.finished_dialog.emit("")
            else:
                self.finished_dialog.emit("__error__")
        except Exception:
            self.finished_dialog.emit("__error__")

def run_applescript_dialog_asynchronously(script):
    loop = QEventLoop()
    result = [None]
    
    def on_finished(val):
        result[0] = val
        loop.quit()
        
    thread = AppleScriptDialogThread(script)
    thread.finished_dialog.connect(on_finished)
    thread.start()
    
    loop.exec()
    thread.wait()
    
    if result[0] == "__error__":
        return None
    return result[0]

def select_file_macos(prompt, file_types):
    import sys
    if sys.platform != 'darwin':
        return None
    types_str = "{" + ", ".join(f'"{t}"' for t in file_types) + "}" if file_types else "{}"
    script = f'''
    tell current application
        activate
        set theFile to choose file of type {types_str} with prompt "{prompt}"
        POSIX path of theFile
    end tell
    '''
    return run_applescript_dialog_asynchronously(script)

def select_dir_macos(prompt):
    import sys
    if sys.platform != 'darwin':
        return None
    script = f'''
    tell current application
        activate
        set theFolder to choose folder with prompt "{prompt}"
        POSIX path of theFolder
    end tell
    '''
    return run_applescript_dialog_asynchronously(script)

def save_file_macos(prompt, default_name):
    import sys
    if sys.platform != 'darwin':
        return None
    script = f'''
    tell current application
        activate
        set theFile to choose file name with prompt "{prompt}" default name "{default_name}"
        POSIX path of theFile
    end tell
    '''
    return run_applescript_dialog_asynchronously(script)

def safe_get_open_file_name(parent, caption, directory, filter_str):
    import re
    extensions = re.findall(r'\*\.([a-zA-Z0-9]+)', filter_str)
    res = select_file_macos(caption, extensions)
    if res is not None:
        return res, ""
    return QFileDialog.getOpenFileName(parent, caption, directory, filter_str)

def safe_get_existing_directory(parent, caption, directory=""):
    res = select_dir_macos(caption)
    if res is not None:
        return res
    return QFileDialog.getExistingDirectory(parent, caption, directory)

def safe_get_save_file_name(parent, caption, directory, filter_str):
    import os
    default_name = os.path.basename(directory) if directory else "output.mp4"
    if not default_name or "." not in default_name:
        default_name = "output.mp4"
    res = save_file_macos(caption, default_name)
    if res is not None:
        return res, ""
    return QFileDialog.getSaveFileName(parent, caption, directory, filter_str)

class JSPreloadThread(QThread):
    log_signal = pyqtSignal(str, bool)
    finished_signal = pyqtSignal(dict)

    def __init__(self, cache_dir, libraries):
        super().__init__()
        self.cache_dir = cache_dir
        self.libraries = libraries

    def run(self):
        import urllib.request
        local_paths = {}
        for url, filename in self.libraries.items():
            local_path = os.path.join(self.cache_dir, filename)
            local_paths[url] = f"file://{urllib.request.pathname2url(local_path)}"
            if not os.path.exists(local_path) or os.path.getsize(local_path) < 1024:
                self.log_signal.emit(f"正在下載本地快取 JS 庫: {filename}...", False)
                try:
                    req = urllib.request.Request(
                        url, 
                        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        with open(local_path, "wb") as f:
                            f.write(response.read())
                    self.log_signal.emit(f"✅ {filename} 下載成功！", False)
                except Exception as e:
                    self.log_signal.emit(f"⚠️ {filename} 下載失敗 ({e})，渲染將回退至線上 CDN", True)
                    local_paths[url] = url  # Fallback to CDN URL
            else:
                # Already exists and is valid size, just resolve path
                pass
        self.finished_signal.emit(local_paths)

class WebBridge(QObject):
    """
    負責接收來自網頁端（JavaScript）所有日誌與報錯的橋樑
    """
    def __init__(self, app_parent):
        super().__init__()
        self.app = app_parent

    @pyqtSlot(str, str, int)
    def report_js_error(self, message, source, lineno):
        logger.error(f"❌ [JS ERROR] 在 {source} 第 {lineno} 行發生錯誤: {message}")
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"❌ [JS 錯誤] {message} (來源: {source}, 行: {lineno})", is_err=True)
        # Avoid blocking / hang in rendering by handling the crash
        if hasattr(self.app, 'handle_render_crash'):
            self.app.handle_render_crash(message)

    @pyqtSlot(str)
    def report_js_log(self, msg):
        # 防護：過濾 SVG 大量座標輸出與過長 Log，防止 Log 爆塞與終端機卡死
        if "<svg" in msg or "<polyline" in msg or "<path" in msg or len(msg) > 1000:
            return
        logger.info(f"💡 [JS LOG]: {msg}")
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"💡 [JS LOG]: {msg}")

class SpringFilter:
    def __init__(self, initial_val=0.0, stiffness=120.0, damping=15.0):
        self.x = initial_val
        self.v = 0.0
        self.target = initial_val
        self.k = stiffness
        self.d = damping

    def update(self, target_val, dt):
        self.target = target_val
        a = -self.k * (self.x - self.target) - self.d * self.v
        self.v += a * dt
        self.x += self.v * dt
        return self.x

OVERRIDE_16_9_JS = """
// Force WebGL to preserve drawing buffer for offscreen grab & set 2D willReadFrequently: true
if (typeof HTMLCanvasElement !== 'undefined') {
  const originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function(type, attributes) {
    if (type === 'webgl' || type === 'webgl2') {
      attributes = attributes || {};
      attributes.preserveDrawingBuffer = true;
    } else if (type === '2d') {
      attributes = attributes || {};
      attributes.willReadFrequently = true;
    }
    return originalGetContext.call(this, type, attributes);
  };
}

if (typeof CanvasGradient !== 'undefined' && CanvasGradient.prototype) {
  const _origAddColorStop = CanvasGradient.prototype.addColorStop;
  CanvasGradient.prototype.addColorStop = function(offset, color) {
    let safeOffset = Number(offset);
    if (isNaN(safeOffset)) safeOffset = 0;
    safeOffset = Math.max(0, Math.min(1, safeOffset));

    let safeColor = String(color || '#000000').trim();
    if (safeColor.startsWith('#')) {
      const hex = safeColor.slice(1);
      if (hex.length === 5) {
        safeColor = '#' + hex + hex[hex.length - 1];
      } else if (hex.length === 7) {
        safeColor = '#' + hex.slice(0, 6);
      } else if (hex.length !== 3 && hex.length !== 4 && hex.length !== 6 && hex.length !== 8) {
        safeColor = '#' + hex.padEnd(6, '0').slice(0, 6);
      }
    }
    try {
      return _origAddColorStop.call(this, safeOffset, safeColor);
    } catch (e) {
      try {
        return _origAddColorStop.call(this, safeOffset, '#000000');
      } catch (err) {}
    }
  };
}

if (typeof window.Scribble === 'undefined') {
  window.Scribble = function() {
    this.roughness = 1;
    this.bowing = 1;
    this.maxOffset = 2;
    this.numEllipseSteps = 10;
    this.scribbleLine = function(x1, y1, x2, y2) { if (typeof line === 'function') line(x1, y1, x2, y2); };
    this.scribbleCurve = function(x1, y1, x2, y2, x3, y3, x4, y4) { if (typeof bezier === 'function') bezier(x1, y1, x2, y2, x3, y3, x4, y4); };
    this.scribbleRect = function(x, y, w, h) { if (typeof rect === 'function') rect(x, y, w, h); };
    this.scribbleRoundedRect = function(x, y, w, h, r) { if (typeof rect === 'function') rect(x, y, w, h, r); };
    this.scribbleEllipse = function(x, y, w, h) { if (typeof ellipse === 'function') ellipse(x, y, w, h); };
    this.scribbleFilling = function(x, y, w, h) {};
  };
}

if (typeof p5 !== 'undefined') {
  // Force window dimensions to 1280x720 to bypass iframe size constraints
  Object.defineProperty(window, 'innerWidth', { get: function() { return 1280; }, set: function(val) {}, configurable: true });
  Object.defineProperty(window, 'innerHeight', { get: function() { return 720; }, set: function(val) {}, configurable: true });
  Object.defineProperty(window, 'windowWidth', { get: function() { return 1280; }, set: function(val) {}, configurable: true });
  Object.defineProperty(window, 'windowHeight', { get: function() { return 720; }, set: function(val) {}, configurable: true });
  
  if (p5.prototype) {
    p5.prototype.windowWidth = 1280;
    p5.prototype.windowHeight = 720;
    p5.prototype._windowWidth = 1280;
    p5.prototype._windowHeight = 720;
    p5.prototype.width = 1280;
    p5.prototype.height = 720;
  }

  const originalCreateCanvas = p5.prototype.createCanvas;
  p5.prototype.createCanvas = function(w, h, val) {
    let targetWidth = 1280;
    let targetHeight = 720;
    
    // 防呆保護：若模組在 setup 計算前傳入 0、NaN 或未定義之寬高，自動回退為標準虛擬畫布 1280x720
    if (!w || isNaN(w) || w <= 0) w = targetWidth;
    if (!h || isNaN(h) || h <= 0) h = targetHeight;
    
    // 依據 window.customScalingMode 所設定的模式進行智慧縮放
    let scale = 1.0;
    let dx = 0;
    let dy = 0;
    let mode = window.customScalingMode || "auto";
    if (w && h && w > 0 && h > 0) {
      if (mode === "contain_height") {
        scale = targetHeight / h;
        dx = (targetWidth - w * scale) / 2;
        dy = 0;
      } else if (mode === "contain_width") {
        scale = targetWidth / w;
        dx = 0;
        dy = (targetHeight - h * scale) / 2;
      } else if (mode === "cover") {
        scale = Math.max(targetWidth / w, targetHeight / h);
        dx = (targetWidth / 2) - (w / 2 * scale);
        dy = (targetHeight / 2) - (h / 2 * scale);
      } else if (mode === "stretch") {
        scale = null;
        dx = 0;
        dy = 0;
        this._customScaleX = targetWidth / w;
        this._customScaleY = targetHeight / h;
      } else { // "auto"
        let aspect = w / h;
        if (aspect < 1.5) {
          scale = targetHeight / h;
          dx = (targetWidth - w * scale) / 2;
          dy = 0;
        } else {
          scale = Math.max(targetWidth / w, targetHeight / h);
          dx = (targetWidth / 2) - (w / 2 * scale);
          dy = (targetHeight / 2) - (h / 2 * scale);
        }
      }
    }
    this._customScale = scale;
    this._customDx = dx;
    this._customDy = dy;
    
    let isGL = (val === 'webgl' || val === 'webgl2' || (typeof WEBGL !== 'undefined' && val === WEBGL));
    this._isGL = isGL;
    
    window.windowWidth = targetWidth;
    window.windowHeight = targetHeight;
    this.windowWidth = targetWidth;
    this.windowHeight = targetHeight;
    this._windowWidth = targetWidth;
    this._windowHeight = targetHeight;
    let canvas = originalCreateCanvas.call(this, targetWidth, targetHeight, val);
    
    // 覆寫 p5 實例與全域的寬高屬性，讓 sketch 的邊界計算代碼讀取到原始虛擬尺寸
    this.width = w;
    this.height = h;
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'width', { get: function() { return w; }, set: function(val) {}, configurable: true });
      Object.defineProperty(window, 'height', { get: function() { return h; }, set: function(val) {}, configurable: true });
    }
    this.pixelDensity(1);
    
    // 立即對繪圖上下文套用縮放與平移，使 setup 內發生的繪圖操作亦能正確滿版與居中 (僅限非 WebGL)
    if (!isGL) {
      if (scale !== null) {
        this.translate(dx, dy);
        this.scale(scale);
      } else {
        this.scale(this._customScaleX || 1.0, this._customScaleY || 1.0);
      }
    }
    
    // 注入動態滿版矩陣縮放 (Dynamic Coordinates Scaling)
    const pInst = this;
    const wrapDraw = function() {
      if (window.draw && !window._isDrawWrapped) {
        const originalDraw = window.draw;
        window.draw = function(...args) {
          if (!isGL) {
            pInst.push();
            pInst.resetMatrix();
            if (pInst._customScale !== undefined && pInst._customScale !== null) {
              pInst.translate(pInst._customDx || 0, pInst._customDy || 0);
              pInst.scale(pInst._customScale);
            } else {
              pInst.scale(pInst._customScaleX || 1.0, pInst._customScaleY || 1.0);
            }
          }
          let res = originalDraw.apply(this, args);
          if (!isGL) {
            pInst.pop();
          }
          return res;
        };
        window._isDrawWrapped = true;
      }
      
      if (pInst.draw && !pInst._isDrawWrapped) {
        const originalDraw = pInst.draw;
        pInst.draw = function(...args) {
          if (!isGL) {
            pInst.push();
            pInst.resetMatrix();
            if (pInst._customScale !== undefined && pInst._customScale !== null) {
              pInst.translate(pInst._customDx || 0, pInst._customDy || 0);
              pInst.scale(pInst._customScale);
            } else {
              pInst.scale(pInst._customScaleX || 1.0, pInst._customScaleY || 1.0);
            }
          }
          let res = originalDraw.apply(this, args);
          if (!isGL) {
            pInst.pop();
          }
          return res;
        };
        pInst._isDrawWrapped = true;
      }
    };
    wrapDraw();
    setTimeout(wrapDraw, 0);
    
    if (canvas && canvas.elt) {
      canvas.elt.style.setProperty('position', 'absolute', 'important');
      canvas.elt.style.setProperty('left', '50%', 'important');
      canvas.elt.style.setProperty('top', '50%', 'important');
      canvas.elt.style.setProperty('right', 'auto', 'important');
      canvas.elt.style.setProperty('bottom', 'auto', 'important');
      canvas.elt.style.setProperty('transform', 'translate(-50%, -50%)', 'important');
      
      canvas.elt.style.setProperty('width', '100vw', 'important');
      canvas.elt.style.setProperty('height', '100vh', 'important');
      canvas.elt.style.setProperty('max-width', 'none', 'important');
      canvas.elt.style.setProperty('max-height', 'none', 'important');
      canvas.elt.style.setProperty('object-fit', 'cover', 'important');
      canvas.elt.style.setProperty('margin', '0', 'important');
    }
    return canvas;
  };

  // Stub fullscreen to avoid browser permission exceptions in QWebEngineView
  p5.prototype.fullscreen = function(val) {
    if (typeof val === 'undefined') {
      return false;
    }
    return false;
  };

  // Intercept resizeCanvas to enforce 16:9 scaling and center alignment
  const originalResizeCanvas = p5.prototype.resizeCanvas;
  p5.prototype.resizeCanvas = function(w, h, val) {
    let targetWidth = 1280;
    let targetHeight = 720;
    window.windowWidth = targetWidth;
    window.windowHeight = targetHeight;
    let canvas = originalResizeCanvas.call(this, targetWidth, targetHeight, val);
    this.width = targetWidth;
    this.height = targetHeight;
    if (typeof window !== 'undefined') {
      window.width = targetWidth;
      window.height = targetHeight;
    }
    if (canvas && canvas.elt) {
      canvas.elt.style.setProperty('position', 'absolute', 'important');
      canvas.elt.style.setProperty('left', '50%', 'important');
      canvas.elt.style.setProperty('top', '50%', 'important');
      canvas.elt.style.setProperty('right', 'auto', 'important');
      canvas.elt.style.setProperty('bottom', 'auto', 'important');
      canvas.elt.style.setProperty('transform', 'translate(-50%, -50%)', 'important');
      canvas.elt.style.setProperty('width', '100vw', 'important');
      canvas.elt.style.setProperty('height', '100vh', 'important');
      canvas.elt.style.setProperty('max-width', 'none', 'important');
      canvas.elt.style.setProperty('max-height', 'none', 'important');
      canvas.elt.style.setProperty('object-fit', 'cover', 'important');
      canvas.elt.style.setProperty('margin', '0', 'important');
    }
    return canvas;
  };

  // Polyfill RendererGL createBuffers / drawBuffers for legacy WebGL geometries in p5.js 2.x
  if (typeof p5.Renderer !== 'undefined' && p5.Renderer.prototype) {
    try {
      Object.defineProperty(p5.Renderer.prototype, 'textures', {
        get: function() {
          if (!this._texturesArray) {
            this._texturesArray = [];
          }
          if (this._texturesArray && typeof this._texturesArray.push !== 'function') {
            try {
              this._texturesArray.push = function(...args) {
                return Array.prototype.push.apply(this, args);
              };
            } catch(e) {
              const fallbackArr = [];
              fallbackArr.push = function(...args) { return Array.prototype.push.apply(this, args); };
              return fallbackArr;
            }
          }
          return this._texturesArray;
        },
        set: function(val) { this._texturesArray = val; },
        configurable: true
      });
    } catch(e) {}
    p5.Renderer.prototype.createBuffers = p5.Renderer.prototype.createBuffers || function(id, geometry) {
      if (typeof p5.RendererGL !== 'undefined' && p5.RendererGL.prototype && typeof p5.RendererGL.prototype.createBuffers === 'function') {
        return p5.RendererGL.prototype.createBuffers.call(this, id, geometry);
      }
    };
    p5.Renderer.prototype.drawBuffers = p5.Renderer.prototype.drawBuffers || function(id) {
      if (typeof p5.RendererGL !== 'undefined' && p5.RendererGL.prototype && typeof p5.RendererGL.prototype.drawBuffers === 'function') {
        return p5.RendererGL.prototype.drawBuffers.call(this, id);
      }
    };
  }
  if (typeof p5.RendererGL !== 'undefined' && p5.RendererGL.prototype) {
    try {
      Object.defineProperty(p5.RendererGL.prototype, 'textures', {
        get: function() {
          if (!this._texturesArray) {
            this._texturesArray = [];
          }
          if (this._texturesArray && typeof this._texturesArray.push !== 'function') {
            try {
              this._texturesArray.push = function(...args) {
                return Array.prototype.push.apply(this, args);
              };
            } catch(e) {
              const fallbackArr = [];
              fallbackArr.push = function(...args) { return Array.prototype.push.apply(this, args); };
              return fallbackArr;
            }
          }
          return this._texturesArray;
        },
        set: function(val) { this._texturesArray = val; },
        configurable: true
      });
    } catch(e) {}
    p5.RendererGL.prototype.createBuffers = p5.RendererGL.prototype.createBuffers || function(id, geometry) {
      // In p5 v2, custom geometry buffer compiling is handled via model buffers or internal geometry objects.
      // We store the geometry object on a cache and let drawBuffers handle the mapping/drawing.
      this._customGeometries = this._customGeometries || {};
      this._customGeometries[id] = geometry;
      
      // Attempt to invoke native internal buffer compilation if available
      if (typeof this._createBuffers === 'function') {
        try { this._createBuffers(id, geometry); return; } catch(e) {}
      }
      
      const gl = this.GL || (typeof window !== 'undefined' ? (window.drawingContext || {}) : {});
      if (!gl) return;
      this._customBuffers = this._customBuffers || {};
      const buffers = this._customBuffers[id] || {};
      
      // Setup Vertex Buffer
      if (geometry.vertices && geometry.vertices.length > 0) {
        if (!buffers.vertex) buffers.vertex = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffers.vertex);
        const vertFloats = new Float32Array(geometry.vertices.flatMap(v => [v.x, v.y, v.z]));
        gl.bufferData(gl.ARRAY_BUFFER, vertFloats, gl.STATIC_DRAW);
        buffers.vertexCount = geometry.vertices.length;
      }
      
      // Setup Normals Buffer
      if (geometry.vertexNormals && geometry.vertexNormals.length > 0) {
        if (!buffers.normal) buffers.normal = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffers.normal);
        const normFloats = new Float32Array(geometry.vertexNormals.flatMap(n => [n.x, n.y, n.z]));
        gl.bufferData(gl.ARRAY_BUFFER, normFloats, gl.STATIC_DRAW);
      }
      
      // Setup Index (Faces) Buffer
      if (geometry.faces && geometry.faces.length > 0) {
        if (!buffers.index) buffers.index = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffers.index);
        const indexInts = new Uint16Array(geometry.faces.flat());
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indexInts, gl.STATIC_DRAW);
        buffers.indexCount = geometry.faces.flat().length;
      }
      
      this._customBuffers[id] = buffers;
    };
    
    p5.RendererGL.prototype.drawBuffers = p5.RendererGL.prototype.drawBuffers || function(id) {
      // If p5 has a native drawing route for compiled models, use it
      if (typeof this._drawBuffers === 'function') {
        try { this._drawBuffers(id); return; } catch(e) {}
      }
      
      const gl = this.GL;
      const buffers = this._customBuffers ? this._customBuffers[id] : null;
      if (!gl || !buffers) return;
      
      const shader = this._activeShader;
      if (!shader) return;
      
      // Bind Vertex Positions
      const positionLoc = gl.getAttribLocation(shader.glProgram, 'aPosition');
      if (positionLoc !== -1 && buffers.vertex) {
        gl.bindBuffer(gl.ARRAY_BUFFER, buffers.vertex);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);
      }
      
      // Bind Normals (crucial for 3D lighting calculations in vertex/fragment shaders!)
      const normalLoc = gl.getAttribLocation(shader.glProgram, 'aNormal');
      if (normalLoc !== -1 && buffers.normal) {
        gl.bindBuffer(gl.ARRAY_BUFFER, buffers.normal);
        gl.enableVertexAttribArray(normalLoc);
        gl.vertexAttribPointer(normalLoc, 3, gl.FLOAT, false, 0, 0);
      }
      
      // Draw Elements
      if (buffers.index) {
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffers.index);
        gl.drawElements(gl.TRIANGLES, buffers.indexCount, gl.UNSIGNED_SHORT, 0);
      }
    };
  }

  // Intercept the p5 start sequence to bind active instance before setup or preload runs
  if (p5.prototype._start) {
    const originalStart = p5.prototype._start;
    p5.prototype._start = function(...args) {
      window._p5Instance = this;
      return originalStart.apply(this, args);
    };
  }

  // Intercept the p5 background function to dynamically update the canvas CSS background color
  const originalBackground = p5.prototype.background;
  p5.prototype.background = function(...args) {
    let res = originalBackground.apply(this, args);
    if (this.canvas) {
      try {
        let col = this.color(...args);
        if (col && col.levels) {
          let r = col.levels[0];
          let g = col.levels[1];
          let b = col.levels[2];
          let a = col.levels[3] / 255;
          let colorStr = `rgba(${r}, ${g}, ${b}, ${a})`;
          this.canvas.style.setProperty('background-color', colorStr, 'important');
        }
      } catch(e) {}
    }
    return res;
  };

  // Smart unrelated text filter (FPS, debug, instructions, loading, prompts, credits)
  window.__isUnrelatedVisualText = function(content) {
    if (content === null || content === undefined) return false;
    let str = String(content).trim();
    if (!str || str.length === 0) return false;
    
    // FPS / frameRate indicators (e.g., "FPS: 60", "FPS: 59.9", "60 FPS", "frameRate: 60")
    if (/^(?:fps|framerate|frame\s*rate)\s*[:=]?\s*[\d\.]*/i.test(str)) return true;
    if (/^[\d\.]+\s*fps\b/i.test(str)) return true;
    if (/^fps\s*$/i.test(str)) return true;
    
    // Loading indicators
    if (/^loading(?:\s*[\.\w]*)?$/i.test(str)) return true;
    if (/^please\s+wait/i.test(str)) return true;
    if (/^esperando\b/i.test(str)) return true;
    
    // Interaction hints & instructions
    if (/(?:drag\s+wind|tap\s+to|click\s+to|press\s+['"\w]|hit\s+space|arrow\s+keys|use\s+mouse|hold\s+mouse|scroll\s+to|snapshot|screenshot|save\s+image|controls?|instructions?|touch\s+to\s+start|press\s+any\s+key)/i.test(str)) {
      return true;
    }
    // Interactive prompt warnings / game-over style dialog text
    if (/too\s+much\s+food|you\s+did\s+not\s+have\s+anything\s+else/i.test(str)) {
      return true;
    }
    // Debug / Param prints: e.g. "Speed: 1.5", "Radius = 100", "Volume: 50%"
    if (/^(?:speed|size|radius|color|count|frequency|volume|threshold|density|scale|zoom|particles|nodes|iteration|gravity|damping)\s*[:=]\s*[-+]?[\d\.]+/i.test(str)) {
      return true;
    }
    // Author watermarks / credits
    if (/^(?:by\s+[\w\s]+|author\s*:|code\s+by|created\s+by|designed\s+by|copyright|©|\(c\))\b/i.test(str)) {
      return true;
    }
    return false;
  };

  // Intercept p5.prototype.text to filter out unrelated UI text
  const originalP5Text = p5.prototype.text;
  if (originalP5Text) {
    p5.prototype.text = function(str, ...args) {
      if (window.__isUnrelatedVisualText(str)) {
        return this;
      }
      return originalP5Text.call(this, str, ...args);
    };
  }

  // Intercept the p5 constructor to capture the current active p5 instance
  const OriginalP5 = window.p5;
  const WrappedP5 = function(sketch, node, ...args) {
    let targetNode = node;
    if (typeof node === 'string') {
      let el = document.getElementById(node);
      if (!el) {
        console.log(`[P5_COMPAT] Target container ID "${node}" not found, creating a dummy div in body.`);
        el = document.createElement('div');
        el.id = node;
        document.body.appendChild(el);
      }
      targetNode = el;
    }
    const inst = new OriginalP5(sketch, targetNode, ...args);
    window._p5Instance = inst;
    return inst;
  };
  // Inherit all static properties & prototypes
  Object.setPrototypeOf(WrappedP5, OriginalP5);
  WrappedP5.prototype = OriginalP5.prototype;
  window.p5 = WrappedP5;
}

// Intercept 2D Canvas fillText and strokeText to suppress unrelated text
if (typeof CanvasRenderingContext2D !== 'undefined' && CanvasRenderingContext2D.prototype) {
  const origFillText = CanvasRenderingContext2D.prototype.fillText;
  if (origFillText) {
    CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
      if (typeof window.__isUnrelatedVisualText === 'function' && window.__isUnrelatedVisualText(text)) {
        return;
      }
      return origFillText.call(this, text, ...args);
    };
  }
  const origStrokeText = CanvasRenderingContext2D.prototype.strokeText;
  if (origStrokeText) {
    CanvasRenderingContext2D.prototype.strokeText = function(text, ...args) {
      if (typeof window.__isUnrelatedVisualText === 'function' && window.__isUnrelatedVisualText(text)) {
        return;
      }
      return origStrokeText.call(this, text, ...args);
    };
  }
}

// Inject universal CSS to hide all GUI controls, inputs, buttons, and floating non-canvas DOM text
(function() {
  const hideStyle = document.createElement('style');
  hideStyle.id = '__hide_controls_and_unrelated_ui__';
  hideStyle.textContent = `
    input, button, select, textarea, label, form, fieldset, nav,
    .dg, .lil-gui, .qs_main, .opc-control, #opc-control-panel, .control-panel, .gui-container,
    [class*="gui"], [id*="gui"], [class*="control"], [id*="control"],
    [class*="instruction"], [id*="instruction"], [class*="info"], [id*="info"],
    [class*="fps"], [id*="fps"], [class*="overlay"], [id*="overlay"],
    [class*="tooltip"], [id*="tooltip"] {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
      position: absolute !important;
      top: -99999px !important;
      left: -99999px !important;
      width: 0px !important;
      height: 0px !important;
      z-index: -99999 !important;
    }
    body > *:not(canvas):not(script):not(style) {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }
  `;
  if (document.head) {
    document.head.appendChild(hideStyle);
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      if (document.head) document.head.appendChild(hideStyle);
    });
  }
})();

// Global beat trigger dispatcher for mock buttons
window._triggerMockButtons = function() {
  if (window._activeMockButtons && window._activeMockButtons.length > 0) {
    window._activeMockButtons.forEach(btn => {
      if (btn && btn._callbacks && btn._callbacks.length > 0) {
        btn._callbacks.forEach(cb => {
          try { cb.call(btn); } catch(e) {}
        });
      }
    });
  }
};
"""

BIND_MODULE_CALLBACKS_JS = """
// Auto-generated mapping to bind Module-scoped p5.js callbacks to window
(function() {
  const p5Callbacks = [
    'setup', 'draw', 'preload', 'windowResized',
    'keyPressed', 'keyReleased', 'keyTyped',
    'mousePressed', 'mouseReleased', 'mouseClicked',
    'mouseMoved', 'mouseDragged', 'mouseWheel', 'doubleClicked',
    'touchStarted', 'touchMoved', 'touchEnded'
  ];
  p5Callbacks.forEach(cb => {
    try {
      let fn = eval(cb);
      if (typeof fn === 'function') {
        window[cb] = fn;
      }
    } catch (e) {}
  });
})();
"""

class ParameterDialog(QDialog):
    """模組參數調整對話框 — 頻率 / 權重 / 特效"""
    def __init__(self, name, frequency, storyboard_weight, post_fx_intensity, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"⚙ 模組參數 — {name}")
        self.setFixedSize(380, 260)
        self.module_name = name
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 10px;
            }
            QLabel {
                color: #e4e4e7;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 標題
        title = QLabel(f"🎛️  {name}", self)
        title.setStyleSheet("color: #f4f4f5; font-size: 15px; font-weight: bold;")
        main_layout.addWidget(title)

        # 分隔線
        sep = QLabel(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3f3f46;")
        main_layout.addWidget(sep)

        SLIDER_STYLE = """
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #27272a;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f4f4f5;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #10b981;
            }
        """

        self.sliders = {}

        def add_param_row(icon, label_text, field_name, init_val):
            row = QHBoxLayout()
            row.setSpacing(10)

            lbl = QLabel(f"{icon} {label_text}", self)
            lbl.setStyleSheet("color: #a1a1aa; font-size: 13px; font-weight: bold;")
            lbl.setFixedWidth(130)
            row.addWidget(lbl)

            slider = QSlider(Qt.Orientation.Horizontal, self)
            slider.setRange(0, 100)
            slider.setValue(init_val)
            slider.setFixedHeight(20)
            slider.setStyleSheet(SLIDER_STYLE)
            row.addWidget(slider)

            val_lbl = QLabel(f"{init_val}%", self)
            val_lbl.setStyleSheet("color: #10b981; font-size: 13px; font-weight: bold;")
            val_lbl.setFixedWidth(40)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider.valueChanged.connect(lambda v: val_lbl.setText(f"{v}%"))
            row.addWidget(val_lbl)

            main_layout.addLayout(row)
            self.sliders[field_name] = slider

        add_param_row("🌀", "動態出現頻率", "frequency", frequency)
        add_param_row("📐", "分鏡切換權重", "storyboard_weight", storyboard_weight)
        add_param_row("✨", "後製特效強度", "post_fx_intensity", post_fx_intensity)

        main_layout.addStretch()

        # 按鈕列
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_cancel = QPushButton("取消", self)
        btn_cancel.setFixedSize(80, 32)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46;
                border-radius: 6px; font-size: 13px;
            }
            QPushButton:hover { background-color: #3f3f46; color: #f4f4f5; }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("✓ 套用", self)
        btn_save.setFixedSize(90, 32)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; border: none;
                border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        btn_save.clicked.connect(self.accept)
        btn_row.addWidget(btn_save)

        main_layout.addLayout(btn_row)

    def get_values(self):
        return {
            "frequency": self.sliders["frequency"].value(),
            "storyboard_weight": self.sliders["storyboard_weight"].value(),
            "post_fx_intensity": self.sliders["post_fx_intensity"].value()
        }


class VisualModuleCardWidget(QWidget):
    def __init__(self, name, tags, author, license_mode, date_added, thumbnail_path, frequency, storyboard_weight, post_fx_intensity, used_count, on_delete_callback, on_preview_callback, on_star_callback, parent=None, display_name=None, is_starred=False):
        super().__init__(parent)
        self.module_name = name
        self._frequency = frequency
        self._storyboard_weight = storyboard_weight
        self._post_fx_intensity = post_fx_intensity
        self.setFixedSize(175, 190)

        # 整體卡片外觀
        self.setStyleSheet("""
            VisualModuleCardWidget {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 6)
        layout.setSpacing(4)

        # 授權判定
        is_restricted = False
        restricted_keywords = ["不能二創", "不能引用", "禁止二創", "禁止引用", "nd", "non-derivative", "no derivative", "no-derivs", "cc-by-nc-nd", "僅限個人", "禁止商用且禁止修改", "不開放"]
        license_str = license_mode if license_mode else "未知"
        for kw in restricted_keywords:
            if kw in license_str.lower():
                is_restricted = True
                break
        is_by_sa = "by-sa" in license_str.lower() or "cc-by-sa" in license_str.lower()

        # ── 1. 預覽圖 (160×120) ──
        img_label = QLabel(self)
        img_label.setFixedSize(160, 120)
        img_label.setCursor(Qt.CursorShape.PointingHandCursor)
        img_label.mousePressEvent = lambda event: on_preview_callback(name)

        if is_restricted:
            border_style = "border: 2px solid #ef4444; border-radius: 8px; background-color: #1a1212;"
        elif is_by_sa:
            border_style = "border: 2px solid #10b981; border-radius: 8px; background-color: #061f14;"
        else:
            border_style = "border: 1px solid #3f3f46; border-radius: 8px; background-color: #09090b;"
        img_label.setStyleSheet(border_style)

        pixmap = QPixmap()
        if thumbnail_path and os.path.exists(thumbnail_path):
            pixmap.load(thumbnail_path)

        if pixmap.isNull():
            placeholder = QImage(160, 120, QImage.Format.Format_ARGB32)
            placeholder.fill(QColor(9, 9, 11))
            painter = QPainter(placeholder)
            painter.setPen(QPen(QColor(16, 185, 129) if is_by_sa else QColor(168, 85, 247)))
            painter.setFont(QFont("Outfit", 11, QFont.Weight.Bold))
            painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "p5.js Visual")
            painter.end()
            pixmap = QPixmap.fromImage(placeholder)

        scaled = pixmap.scaled(160, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        # 居中裁切
        if scaled.width() > 160 or scaled.height() > 120:
            x = (scaled.width() - 160) // 2
            y = (scaled.height() - 120) // 2
            scaled = scaled.copy(x, y, 160, 120)
        img_label.setPixmap(scaled)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Overlaid Star icon (我的最愛)
        star_icon = "★" if is_starred else "☆"
        star_color = "#eab308" if is_starred else "#71717a"
        badge_star = QLabel(star_icon, img_label)
        badge_star.setCursor(Qt.CursorShape.PointingHandCursor)
        badge_star.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(9, 9, 11, 0.85);
                color: {star_color};
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                padding: 1px 4px;
                border: 1px solid rgba(234, 179, 8, 0.4);
            }}
        """)
        badge_star.setGeometry(6, 6, 22, 22)
        badge_star.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Connect clicking star to callback
        def on_star_click(event):
            on_star_callback(name)
        badge_star.mousePressEvent = on_star_click

        # Overlaid used count badge
        badge_used = QLabel(f"🎬 {used_count}", img_label)
        badge_used.setStyleSheet("""
            QLabel {
                background-color: rgba(9, 9, 11, 0.85);
                color: #38bdf8;
                font-size: 9px;
                font-weight: bold;
                border-radius: 4px;
                padding: 1px 4px;
                border: 1px solid rgba(56, 189, 248, 0.4);
            }
        """)
        badge_width = badge_used.fontMetrics().horizontalAdvance(f"🎬 {used_count}") + 12
        badge_used.setGeometry(160 - badge_width - 6, 6, badge_width, 16)
        badge_used.mousePressEvent = lambda event: on_preview_callback(name)
        
        # Overlaid origin badge (🧬 原創 vs 📥 收編)
        is_original = (license_mode == "Original" or author == "AI Incubator")
        origin_text = "🧬 原創" if is_original else "📥 收編"
        origin_color = "#f3e8ff" if is_original else "#a1a1aa"
        origin_bg = "rgba(124, 58, 237, 0.85)" if is_original else "rgba(39, 39, 42, 0.85)"
        origin_border = "#8b5cf6" if is_original else "#3f3f46"
        
        badge_origin = QLabel(origin_text, img_label)
        badge_origin.setStyleSheet(f"""
            QLabel {{
                background-color: {origin_bg};
                color: {origin_color};
                font-size: 9px;
                font-weight: bold;
                border-radius: 3px;
                padding: 1px 3px;
                border: 1px solid {origin_border};
            }}
        """)
        origin_w = badge_origin.fontMetrics().horizontalAdvance(origin_text) + 8
        badge_origin.setGeometry(6, 98, origin_w, 16)
        badge_origin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_origin.mousePressEvent = lambda event: on_preview_callback(name)

        layout.addWidget(img_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # ── 2. 名稱 + 勾選框 ──
        # Constrain checkbox text width using QFontMetrics to prevent breaking grid layout columns
        full_text = display_name if display_name else name
        metrics = QFontMetrics(QFont("Outfit", 12, QFont.Weight.Bold))
        elided_text = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, 138)
        self.checkbox = QCheckBox(elided_text, self)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                color: #f4f4f5;
                font-weight: bold;
                font-size: 12px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 2px solid #52525b;
                border-radius: 4px;
                background-color: #27272a;
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
                border-color: #10b981;
            }
        """)
        self.checkbox.setToolTip(full_text)
        layout.addWidget(self.checkbox)

        # ── 3. 底部資訊列：指示器 + 作者/badge + ⚙ + 🗑️ ──
        bottom_box = QHBoxLayout()
        bottom_box.setContentsMargins(2, 0, 2, 0)
        bottom_box.setSpacing(3)

        # 微型三色指示器 (頻率/權重/特效)
        def _dot_color(val):
            if val <= 25: return "#ef4444"     # 低 → 紅
            elif val <= 50: return "#f59e0b"   # 中低 → 橙
            elif val <= 75: return "#10b981"   # 中高 → 綠
            else: return "#6366f1"             # 高 → 紫

        dots_widget = QWidget(self)
        dots_widget.setFixedSize(30, 12)
        dots_layout = QHBoxLayout(dots_widget)
        dots_layout.setContentsMargins(0, 0, 0, 0)
        dots_layout.setSpacing(3)

        for val, tip in [(frequency, "頻率"), (storyboard_weight, "權重"), (post_fx_intensity, "特效")]:
            dot = QLabel("●", self)
            dot.setStyleSheet(f"color: {_dot_color(val)}; font-size: 8px;")
            dot.setToolTip(f"{tip}: {val}%")
            dot.setFixedSize(8, 12)
            dots_layout.addWidget(dot)

        bottom_box.addWidget(dots_widget)

        # 作者 / CC BY-SA badge
        if is_by_sa:
            badge = QLabel("CC BY-SA", self)
            badge.setStyleSheet("""
                background-color: #064e3b;
                color: #34d399;
                font-size: 8px;
                font-weight: bold;
                border-radius: 3px;
                padding: 1px 4px;
            """)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bottom_box.addWidget(badge)
        else:
            author_lbl = QLabel(author[:8] if author else "未知", self)
            author_lbl.setStyleSheet("color: #52525b; font-size: 9px;")
            author_lbl.setToolTip(f"作者: {author}")
            bottom_box.addWidget(author_lbl)

        bottom_box.addStretch()

        # ⚙ 參數按鈕
        btn_param = QPushButton("參數", self)
        btn_param.setFixedSize(36, 20)
        btn_param.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_param.setToolTip("調整頻率 / 權重 / 特效參數")
        btn_param.setStyleSheet("""
            QPushButton {
                background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46;
                border-radius: 4px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #10b981; color: white; border-color: #10b981;
            }
        """)

        def open_param_dialog():
            dlg = ParameterDialog(name, self._frequency, self._storyboard_weight, self._post_fx_intensity, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                vals = dlg.get_values()
                self._frequency = vals["frequency"]
                self._storyboard_weight = vals["storyboard_weight"]
                self._post_fx_intensity = vals["post_fx_intensity"]
                # 寫回 JSON
                workspace = os.path.dirname(os.path.abspath(__file__))
                fp = os.path.join(workspace, "custom_visuals", f"{name}.json")
                if os.path.exists(fp):
                    try:
                        with open(fp, "r", encoding="utf-8") as f_in:
                            d = json.load(f_in)
                        d.update(vals)
                        with open(fp, "w", encoding="utf-8") as f_out:
                            json.dump(d, f_out, indent=4, ensure_ascii=False)
                    except Exception as e:
                        print(f"更新模組參數失敗: {e}")
                # 更新指示點顏色
                dot_vals = [self._frequency, self._storyboard_weight, self._post_fx_intensity]
                dot_tips = ["頻率", "權重", "特效"]
                for i in range(dots_layout.count()):
                    w = dots_layout.itemAt(i).widget()
                    if w:
                        w.setStyleSheet(f"color: {_dot_color(dot_vals[i])}; font-size: 8px;")
                        w.setToolTip(f"{dot_tips[i]}: {dot_vals[i]}%")

        btn_param.clicked.connect(open_param_dialog)
        bottom_box.addWidget(btn_param)

        # 🗑️ 刪除按鈕
        btn_delete = QPushButton("刪除", self)
        btn_delete.setFixedSize(36, 20)
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.setToolTip("刪除此模組")
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #27272a; color: #f87171; border: 1px solid #3f3f46;
                border-radius: 4px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f1d1d; color: white; border-color: #991b1b;
            }
        """)
        btn_delete.clicked.connect(lambda: on_delete_callback(name))
        bottom_box.addWidget(btn_delete)

        layout.addLayout(bottom_box)

        # Tooltip 詳細
        self.setToolTip(f"名稱: {name}\n作者: {author}\n授權: {license_str}\n日期: {date_added}\nTags: {', '.join(tags)}\n\n頻率: {frequency}%  |  權重: {storyboard_weight}%  |  特效: {post_fx_intensity}%\n\n💡 點擊卡片即可於右側啟動即時沙盒預覽")

        # 支援點擊卡片任意區域立即啟動預覽
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        def on_card_click(event):
            child = self.childAt(event.pos())
            if child not in (self.checkbox, badge_star, btn_param, btn_delete) and not isinstance(child, (QCheckBox, QPushButton)):
                on_preview_callback(name)
        self.mousePressEvent = on_card_click

    def enterEvent(self, event):
        self.setStyleSheet("""
            VisualModuleCardWidget {
                background-color: #1e1e23;
                border: 1px solid #10b981;
                border-radius: 10px;
            }
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("""
            VisualModuleCardWidget {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 10px;
            }
        """)
        super().leaveEvent(event)

class VisualModuleItemWidget(QWidget):
    def __init__(self, name, tags, author, license_mode, date_added, frequency, storyboard_weight, post_fx_intensity, on_delete_callback, on_star_callback, parent=None, display_name=None, is_starred=False, on_preview_callback=None):
        super().__init__(parent)
        self.module_name = name
        self._frequency = frequency
        self._storyboard_weight = storyboard_weight
        self._post_fx_intensity = post_fx_intensity
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)
        
        # 0.5 我的最愛星星按鈕
        self.btn_star = QPushButton("★" if is_starred else "☆", self)
        self.btn_star.setToolTip("加到最愛 / 取消最愛")
        star_color = "#eab308" if is_starred else "#71717a"
        self.btn_star.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {star_color};
                border: none;
                font-size: 16px;
                font-weight: bold;
                padding: 0px 4px;
            }}
            QPushButton:hover {{
                color: #eab308;
            }}
        """)
        self.btn_star.setFixedWidth(24)
        self.btn_star.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_star.clicked.connect(lambda: on_star_callback(name))
        layout.addWidget(self.btn_star)
        
        # 1. 模組名稱勾選框 (固定寬度 200px)
        self.checkbox = QCheckBox(display_name if display_name else name, self)
        self.checkbox.setStyleSheet("color: #f4f4f5; font-weight: bold; font-size: 13px;")
        self.checkbox.setFixedWidth(200)
        layout.addWidget(self.checkbox)
        
        tags_str = ", ".join(tags) if tags else "無"
        author_str = author if author else "未知"
        license_str = license_mode if license_mode else "未知"
        date_str = date_added[:10] if date_added else "未知"
        
        # 2. Tags 標籤 (固定寬度 130px)
        self.tags_label = QLabel(self)
        self.tags_label.setText(f'<span style="color: #c084fc;">[Tags: {tags_str}]</span>')
        self.tags_label.setStyleSheet("font-size: 12px;")
        self.tags_label.setFixedWidth(130)
        layout.addWidget(self.tags_label)
        
        # 3. 作者 (固定寬度 100px)
        self.author_label = QLabel(self)
        self.author_label.setText(f'<span style="color: #a1a1aa;">[作者: {author_str}]</span>')
        self.author_label.setStyleSheet("font-size: 12px;")
        self.author_label.setFixedWidth(100)
        layout.addWidget(self.author_label)
        
        # 4. 加入日期 (固定寬度 120px)
        self.date_label = QLabel(self)
        self.date_label.setText(f'<span style="color: #38bdf8;">[日期: {date_str}]</span>')
        self.date_label.setStyleSheet("font-size: 12px;")
        self.date_label.setFixedWidth(120)
        layout.addWidget(self.date_label)
        
        # 5. 授權模式 (固定寬度 180px)
        self.license_label = QLabel(self)
        is_restricted = False
        restricted_keywords = ["不能二創", "不能引用", "禁止二創", "禁止引用", "nd", "non-derivative", "no derivative", "no-derivs", "cc-by-nc-nd", "僅限個人", "禁止商用且禁止修改", "不開放"]
        for kw in restricted_keywords:
            if kw in license_str.lower():
                is_restricted = True
                break
        
        is_by_sa = "by-sa" in license_str.lower() or "cc-by-sa" in license_str.lower()
        if is_restricted:
            self.license_label.setText(f'<span style="color: #ef4444; font-weight: bold;">[🚫 {license_str[:15]}]</span>')
        elif is_by_sa:
            self.license_label.setText(f'<span style="color: #34d399; font-weight: bold;">[🟢 {license_str[:15]}]</span>')
        else:
            self.license_label.setText(f'<span style="color: #e4e4e7;">[{license_str[:15]}]</span>')
        self.license_label.setStyleSheet("font-size: 12px;")
        self.license_label.setFixedWidth(180)
        layout.addWidget(self.license_label)
        
        # 5.5. 參數調整區 (三個滑桿)
        params_layout = QHBoxLayout()
        params_layout.setSpacing(15)
        
        def create_list_slider(label_text, field_name, init_val):
            row = QHBoxLayout()
            row.setSpacing(5)
            
            lbl = QLabel(label_text, self)
            lbl.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: bold;")
            row.addWidget(lbl)
            
            slider = QSlider(Qt.Orientation.Horizontal, self)
            slider.setRange(0, 100)
            slider.setValue(init_val)
            slider.setFixedWidth(80)
            slider.setFixedHeight(12)
            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #3f3f46;
                    height: 4px;
                    background: #27272a;
                    border-radius: 2px;
                }
                QSlider::handle:horizontal {
                    background: #10b981;
                    width: 10px;
                    margin: -3px 0;
                    border-radius: 5px;
                }
            """)
            
            val_lbl = QLabel(f"{init_val}%", self)
            val_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
            val_lbl.setFixedWidth(30)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            def update_preset_field(val):
                val_lbl.setText(f"{val}%")
                if field_name == "frequency": self._frequency = val
                elif field_name == "storyboard_weight": self._storyboard_weight = val
                elif field_name == "post_fx_intensity": self._post_fx_intensity = val
                workspace = os.path.dirname(os.path.abspath(__file__))
                fp = os.path.join(workspace, "custom_visuals", f"{name}.json")
                if os.path.exists(fp):
                    try:
                        import json
                        with open(file_path, "r", encoding="utf-8") as f_in:
                            d = json.load(f_in)
                        d[field_name] = val
                        with open(file_path, "w", encoding="utf-8") as f_out:
                            json.dump(d, f_out, indent=4, ensure_ascii=False)
                    except Exception as e:
                        print(f"更新視覺模組欄位 {field_name} 失敗: {e}")
            
            def on_val_changed(val):
                val_lbl.setText(f"{val}%")
                update_preset_field(val)
                
            slider.valueChanged.connect(on_val_changed)
            
            row.addWidget(slider)
            row.addWidget(val_lbl)
            return row

        params_layout.addLayout(create_list_slider("🌀 頻率", "frequency", frequency))
        params_layout.addLayout(create_list_slider("⚖️ 權重", "storyboard_weight", storyboard_weight))
        params_layout.addLayout(create_list_slider("✨ 特效", "post_fx_intensity", post_fx_intensity))
        
        layout.addLayout(params_layout)
        layout.addStretch()
        
        # 6. 刪除按鈕 (🗑️)
        self.btn_delete = QPushButton("🗑️", self)
        self.btn_delete.setToolTip("刪除此預設檔")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #71717a;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #b91c1c;
                color: white;
                border-color: #ef4444;
            }
        """)
        self.btn_delete.clicked.connect(lambda: on_delete_callback(name))
        layout.addWidget(self.btn_delete)

class AspectRatioWidget(QWidget):
    def __init__(self, widget, ratio=16/9, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.ratio = ratio
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        
        target_h = int(w / self.ratio)
        if target_h <= h:
            margin = (h - target_h) // 2
            self.layout().setContentsMargins(0, margin, 0, margin)
        else:
            target_w = int(h * self.ratio)
            margin = (w - target_w) // 2
            self.layout().setContentsMargins(margin, 0, margin, 0)
        super().resizeEvent(event)

class StandaloneInjectorApp(QMainWindow):
    KNOWN_LIBRARIES = {
        "lil": "https://cdn.jsdelivr.net/npm/lil-gui@0.19/dist/lil-gui.umd.min.js",
        "matter": "https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js",
        "polygonclipping": "https://cdn.jsdelivr.net/npm/polygon-clipping@0.15.3/dist/polygon-clipping.umd.min.js",
        "p5.play": "https://cdn.jsdelivr.net/npm/p5.play@2/lib/p5.play.js",
        "epicolorspckg": "https://cdn.jsdelivr.net/gh/epibyte/p5-epi-colors@v0.0.9/dist/p5-epi-colors.js",
        "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
        "orbitcontrols": "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js",
        "chroma": "https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.4.2/chroma.min.js",
        "d3": "https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js",
        "dat": "https://cdnjs.cloudflare.com/ajax/libs/dat-gui/0.7.9/dat.gui.min.js",
        "decomp": "https://cdn.jsdelivr.net/npm/poly-decomp@0.3.0/build/decomp.min.js",
        "polydecomp": "https://cdn.jsdelivr.net/npm/poly-decomp@0.3.0/build/decomp.min.js"
    }

    def setup_web_sandbox(self, web_view):
        channel = QWebChannel()
        bridge = WebBridge(self)
        web_view._web_channel = channel
        web_view._web_bridge = bridge
        channel.registerObject("pyBridge", bridge)
        web_view.page().setWebChannel(channel)

    def handle_render_crash(self, error_msg):
        self.log_to_console(f"⚠️ 檢測到 JavaScript 執行警告 (繼續離線渲染)：{error_msg}", is_err=True)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("音畫互動 4K MV 視覺整合編輯器")
        self.resize(1400, 850)
        self.setMinimumSize(1000, 700)
        self.render_aborted = False
        self.thumbnail_generating = False
        self.failed_thumbnails = set()
        self.thumbnail_current_attempts = 0
        
        # Apply Neon Dark Theme
        self.setStyleSheet("""
            QMainWindow, QWidget, QDialog, QSplitter {
                background-color: #0b0b0e;
                color: #e4e4e7;
            }
            QScrollArea {
                background-color: #0b0b0e;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #0b0b0e;
            }
            QTabWidget, QTabWidget::pane {
                border: 1px solid #1f1f23;
                background-color: #0b0b0e;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #18181b;
                color: #a1a1aa;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #27272a;
                color: #ffffff;
                border-bottom: 2px solid #a855f7;
            }
            QLabel {
                font-family: 'Outfit', 'Inter', sans-serif;
                color: #f4f4f5;
                background-color: transparent;
            }
            QCheckBox {
                color: #f4f4f5;
                background-color: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #a855f7;
                border-color: #a855f7;
            }
            QLineEdit, QComboBox, QListWidget {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background-color: #18181b;
                color: #f4f4f5;
                selection-background-color: #a855f7;
                selection-color: #ffffff;
                border: 1px solid #27272a;
                outline: 0px;
            }
            QComboBox QAbstractItemView::item {
                background-color: #18181b;
                color: #f4f4f5;
                padding: 6px;
                min-height: 24px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #a855f7;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #a855f7;
                color: #ffffff;
            }
            QSlider::groove:horizontal {
                border: 1px solid #27272a;
                height: 6px;
                background: #18181b;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #a855f7;
                border: 1px solid #a855f7;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QPushButton {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27272a;
                border-color: #3f3f46;
            }
            QMessageBox {
                background-color: #18181b;
            }
            QMessageBox QLabel {
                color: #f4f4f5;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover {
                background-color: #3f3f46;
            }
        """)

        # Main splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(self.main_splitter)

        # ----------------------------------------------------
        # Left Panel (Tabbed: Code Editor & MV Renderer)
        # ----------------------------------------------------
        self.left_tabs = QTabWidget(self)
        self.main_splitter.addWidget(self.left_tabs)

        self.init_code_editor_tab()
        self.ai_incubator = AIIncubatorTab(self)
        self.left_tabs.insertTab(1, self.ai_incubator, "🚀 AI 視覺資產 AI 孵化器")
        self.init_renderer_tab()
        self.pixel_generator = PixelModuleGeneratorTab(self)
        self.left_tabs.addTab(self.pixel_generator, "👾 像素視覺模組生成器")
        self.shorts_exporter = ShortsExporterTab(self)
        self.left_tabs.addTab(self.shorts_exporter, "📱 YouTube Shorts 批量匯出")

        # ----------------------------------------------------
        # Right Panel (Sandbox & Console)
        # ----------------------------------------------------
        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        sandbox_title = QLabel("🌐 視覺特效即時沙盒 (16:9 Live Sandbox)", right_panel)
        sandbox_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        right_layout.addWidget(sandbox_title)

        # WebEngine sandbox
        self.web_view = QWebEngineView(right_panel)
        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_view)
        self.web_view.setPage(self.web_page)
        self.setup_web_sandbox(self.web_view)
        
        # Configure settings to allow local content to access remote URLs (CORS bypass)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        
        self.web_view.page().setBackgroundColor(QColor(11, 11, 14))
        self.web_view.setStyleSheet("border: 1px solid #27272a; border-radius: 8px; background-color: #0b0b0e;")
        
        self.placeholder_html = """
        <html>
        <body style="background-color: #0b0b0e; margin: 0; display: flex; align-items: center; justify-content: center; height: 100vh; overflow: hidden;">
            <div style="color: #a1a1aa; font-family: 'Outfit', 'Inter', sans-serif; font-size: 14px; text-align: center; border: 1px dashed #27272a; padding: 20px; border-radius: 8px; background-color: #121216; width: 80%;">
                📺 點擊下方【執行即時預覽測試】以啟動沙盒
            </div>
        </body>
        </html>
        """
        self.web_view.setHtml(self.placeholder_html, get_local_base_url())

        self.sandbox_container = AspectRatioWidget(self.web_view, 16/9, right_panel)
        right_layout.addWidget(self.sandbox_container, stretch=3)

        # 沙盒預覽即時控制按鈕
        sandbox_ctrl_layout = QHBoxLayout()
        sandbox_ctrl_layout.setContentsMargins(0, 5, 0, 5)
        
        self.btn_sandbox_stop = QPushButton("🛑 中斷預覽", right_panel)
        self.btn_sandbox_stop.setStyleSheet("""
            QPushButton {
                background-color: #7f1d1d;
                border: 1px solid #991b1b;
                color: #fecaca;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #991b1b;
                border-color: #b91c1c;
            }
        """)
        self.btn_sandbox_stop.clicked.connect(self.stop_sandbox_preview)
        
        self.btn_sandbox_clear = QPushButton("🧹 清空沙盒", right_panel)
        self.btn_sandbox_clear.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #e4e4e7;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border-color: #52525b;
            }
        """)
        self.btn_open_log = QPushButton("📜 開啟診斷日誌", right_panel)
        self.btn_open_log.setStyleSheet("""
            QPushButton {
                background-color: #1e1b4b;
                border: 1px solid #3730a3;
                color: #c7d2fe;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #312e81;
                border-color: #4338ca;
            }
        """)
        self.btn_open_log.clicked.connect(self.open_debug_log_file)
        
        sandbox_ctrl_layout.addWidget(self.btn_sandbox_stop)
        sandbox_ctrl_layout.addWidget(self.btn_sandbox_clear)
        sandbox_ctrl_layout.addWidget(self.btn_open_log)
        right_layout.addLayout(sandbox_ctrl_layout)

        console_title = QLabel("📝 輸出終端 (Console Logs & 錯誤監看):", right_panel)
        console_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #a1a1aa;")
        right_layout.addWidget(console_title)

        self.console_log = QTextEdit(right_panel)
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet("background-color: #09090b; color: #10b981; border: 1px solid #27272a; border-radius: 8px;")
        self.console_log.setFont(QFont("Courier New", 11))
        right_layout.addWidget(self.console_log, stretch=1)

        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setStretchFactor(0, 45)
        self.main_splitter.setStretchFactor(1, 55)

        # Sandbox beat timer
        self.beat_timer = QTimer(self)
        self.beat_timer.timeout.connect(self.trigger_simulated_beat)
        
        self.has_errors = False
        self.test_run_performed = False

        self.custom_html = ""
        self.custom_css = ""
        self.inline_assets = {}
        
        # 記憶體快取：儲存預先載入的模組元數據，避免每次搜尋重讀硬碟
        self.cached_presets = None

        # Pagination & Checked State Tracking for 1000+ visual modules
        self.checked_presets = set()
        self.presets_page_size = 60
        self.presets_current_page = 1
        self.presets_max_pages = 1

        # Load existing presets
        self.refresh_presets_list(clean_black=False)

        # Initialize local JS library caching to prevent CDN fetch failures
        self.js_local_paths = {}
        QTimer.singleShot(1000, self.preload_js_cache)

        # Setup 3-color AI Status Badge in Status Bar
        self.status_bar = self.statusBar()
        self.ai_status_label = QLabel("🤖 AI 引擎：檢測中...", self)
        self.ai_status_label.setStyleSheet("padding: 2px 10px; font-weight: bold; color: #a1a1aa; background-color: #18181b; border-radius: 4px; margin-right: 10px;")
        self.status_bar.addPermanentWidget(self.ai_status_label)

        # Non-blocking AI status check on startup and periodic polling
        QTimer.singleShot(1200, self.refresh_ai_status)
        self.ai_status_timer = QTimer(self)
        self.ai_status_timer.timeout.connect(self.refresh_ai_status)
        self.ai_status_timer.start(30000)

    def refresh_ai_status(self):
        """ 透過背景 QThread 發起非同步 Ollama 狀態探針 """
        self.ai_worker = AIStatusWorker()
        self.ai_worker.status_updated.connect(self.on_ai_status_updated)
        self.ai_worker.start()

    def on_ai_status_updated(self, status_info: dict):
        """ 依據 3 色狀態即時更新 UI 指示燈風格與提示字串 """
        status = status_info.get("status", "offline")
        msg = status_info.get("message", "離線")
        if status == "ready":
            # 🟢 綠燈
            self.ai_status_label.setText(f"🟢 {msg}")
            self.ai_status_label.setStyleSheet("padding: 2px 10px; font-weight: bold; color: #10b981; background-color: #064e3b; border: 1px solid #059669; border-radius: 4px; margin-right: 10px;")
        elif status == "model_missing":
            # 🟡 黃燈
            self.ai_status_label.setText(f"🟡 {msg}")
            self.ai_status_label.setStyleSheet("padding: 2px 10px; font-weight: bold; color: #f59e0b; background-color: #78350f; border: 1px solid #d97706; border-radius: 4px; margin-right: 10px;")
        else:
            # ⚪ 灰燈
            self.ai_status_label.setText(f"⚪ {msg}")
            self.ai_status_label.setStyleSheet("padding: 2px 10px; font-weight: bold; color: #a1a1aa; background-color: #18181b; border: 1px solid #27272a; border-radius: 4px; margin-right: 10px;")

    def init_code_editor_tab(self):
        tab = QWidget(self)
        tab.setStyleSheet("background-color: #0b0b0e;")
        main_tab_layout = QVBoxLayout(tab)
        main_tab_layout.setContentsMargins(4, 4, 4, 4)

        # Tab Scroll Area
        scroll_area = QScrollArea(tab)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #0b0b0e; }
            QWidget { background-color: #0b0b0e; }
            QScrollBar:vertical { width: 6px; background: #121215; }
            QScrollBar::handle:vertical { background: #3f3f46; border-radius: 3px; }
        """)
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #0b0b0e;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        scroll_area.setWidget(scroll_content)
        main_tab_layout.addWidget(scroll_area)

        editor_lbl = QLabel("💻 p5.js 開源代碼編輯區", scroll_content)
        editor_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #a855f7;")
        layout.addWidget(editor_lbl)

        # OpenProcessing fetch area (2-row stacked for responsive fit)
        op_box = QVBoxLayout()
        op_box.setSpacing(4)
        
        op_input_row = QHBoxLayout()
        op_lbl = QLabel("OpenProcessing 網址:", scroll_content)
        op_lbl.setFixedWidth(120)
        op_lbl.setStyleSheet("font-weight: bold; color: #a1a1aa; font-size: 11px;")
        self.op_input = QLineEdit(scroll_content)
        self.op_input.setPlaceholderText("貼上作品網址，例如: https://openprocessing.org/sketch/2219276")
        self.op_input.setStyleSheet("font-size: 11px;")
        op_input_row.addWidget(op_lbl)
        op_input_row.addWidget(self.op_input, 1)
        op_box.addLayout(op_input_row)

        op_btn_row = QHBoxLayout()
        op_btn_row.setSpacing(6)
        self.btn_op_fetch = QPushButton("⚡ 【自動抓取程式碼】", scroll_content)
        self.btn_op_fetch.setStyleSheet("background-color: #1e1b4b; border-color: #312e81; color: #e0e7ff; font-weight: bold; font-size: 11px; padding: 4px 8px;")
        self.btn_op_fetch.clicked.connect(self.fetch_and_load_openprocessing)
        
        self.btn_op_batch = QPushButton("📥 【批次收編作者作品】", scroll_content)
        self.btn_op_batch.setStyleSheet("background-color: #3b0764; border-color: #581c87; color: #f3e8ff; font-weight: bold; font-size: 11px; padding: 4px 8px;")
        self.btn_op_batch.clicked.connect(self.open_batch_import_dialog)
        
        op_btn_row.addWidget(self.btn_op_fetch)
        op_btn_row.addWidget(self.btn_op_batch)
        op_box.addLayout(op_btn_row)
        layout.addLayout(op_box)

        # Code editor
        self.editor = CodeEditor(scroll_content)
        self.editor.setMinimumHeight(240)
        self.editor.setPlainText(self.get_default_template())
        layout.addWidget(self.editor)

        # Name and parameters
        form = QVBoxLayout()
        form.setSpacing(6)
        
        name_row = QHBoxLayout()
        name_lbl = QLabel("視覺模組名稱:", scroll_content)
        name_lbl.setFixedWidth(110)
        name_lbl.setStyleSheet("font-size: 11px;")
        self.name_input = QLineEdit(scroll_content)
        self.name_input.setPlaceholderText("例如: audio_wave_4k")
        self.name_input.setStyleSheet("font-size: 11px;")
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_input, 1)
        form.addLayout(name_row)

        # Metadata rows (Author & License)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        author_lbl = QLabel("作者:", scroll_content)
        author_lbl.setFixedWidth(40)
        author_lbl.setStyleSheet("font-size: 11px;")
        self.author_input = QLineEdit(scroll_content)
        self.author_input.setPlaceholderText("作者名稱")
        self.author_input.setStyleSheet("font-size: 11px;")
        
        license_lbl = QLabel("授權:", scroll_content)
        license_lbl.setFixedWidth(40)
        license_lbl.setStyleSheet("font-size: 11px;")
        self.license_input = QLineEdit(scroll_content)
        self.license_input.setPlaceholderText("MIT / CC")
        self.license_input.setStyleSheet("font-size: 11px;")
        
        meta_row.addWidget(author_lbl)
        meta_row.addWidget(self.author_input, 1)
        meta_row.addWidget(license_lbl)
        meta_row.addWidget(self.license_input, 1)
        form.addLayout(meta_row)
        
        # Tags row
        tags_row = QHBoxLayout()
        tags_lbl = QLabel("分類標籤:", scroll_content)
        tags_lbl.setFixedWidth(110)
        tags_lbl.setStyleSheet("font-size: 11px;")
        self.tags_input = QLineEdit(scroll_content)
        self.tags_input.setPlaceholderText("例如: intro, drop, ambient, 3d, slow (逗號分隔)")
        self.tags_input.setStyleSheet("font-size: 11px;")
        tags_row.addWidget(tags_lbl)
        tags_row.addWidget(self.tags_input, 1)
        form.addLayout(tags_row)
        
        # Quick tag buttons (2-row grid for responsive fit)
        tag_grid = QGridLayout()
        tag_grid.setSpacing(3)
        tag_grid.addWidget(QLabel("推薦標籤:", scroll_content), 0, 0)
        
        tags_list = ["intro", "verse", "buildup", "drop", "outro", "ambient", "3d", "fast", "slow"]
        for idx, tag_name in enumerate(tags_list):
            btn = QPushButton(tag_name, scroll_content)
            btn.setStyleSheet("padding: 2px 6px; font-size: 10px; background-color: #18181b; color: #a1a1aa; border-radius: 3px; border: 1px solid #27272a;")
            btn.clicked.connect(lambda checked, t=tag_name: self.append_tag(t))
            row = (idx + 1) // 5
            col = (idx + 1) % 5
            tag_grid.addWidget(btn, row, col)
        form.addLayout(tag_grid)

        # Sliders
        self.freq_slider = self.create_slider_row(form, "動態出現頻率 (Frequency):", scroll_content)
        self.weight_slider = self.create_slider_row(form, "分鏡切換權重 (Weight):", scroll_content)
        self.fx_slider = self.create_slider_row(form, "後製特效強度 (Post-FX):", scroll_content)

        layout.addLayout(form)

        # Control Buttons
        self.btn_adapt = QPushButton("🪄 【自動 16:9 轉換與音畫優化】", scroll_content)
        self.btn_adapt.setStyleSheet("background-color: #7c2d12; border-color: #9a3412; color: #ffedd5; font-size: 13px;")
        self.btn_adapt.clicked.connect(self.adapt_and_repair_code)
        layout.addWidget(self.btn_adapt)

        # 預覽控制按鈕區 (執行與停止)
        sandbox_btn_layout = QHBoxLayout()
        sandbox_btn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_compile = QPushButton("【執行即時預覽測試】", scroll_content)
        self.btn_compile.clicked.connect(self.compile_and_run_sandbox)
        
        self.btn_stop_compile = QPushButton("【停止即時預覽】", scroll_content)
        self.btn_stop_compile.setEnabled(False)
        self.btn_stop_compile.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #71717a;
                border: 1px solid #3f3f46;
            }
            QPushButton:enabled {
                background-color: #b91c1c;
                color: white;
                border: 1px solid #ef4444;
            }
            QPushButton:enabled:hover {
                background-color: #ef4444;
                border-color: #f87171;
            }
        """)
        self.btn_stop_compile.clicked.connect(self.stop_sandbox_preview)
        
        sandbox_btn_layout.addWidget(self.btn_compile)
        sandbox_btn_layout.addWidget(self.btn_stop_compile)
        layout.addLayout(sandbox_btn_layout)

        self.cb_confirm = QCheckBox("【確認視覺模組運行正常】", scroll_content)
        self.cb_confirm.setEnabled(False)
        self.cb_confirm.stateChanged.connect(self.toggle_save_button)
        layout.addWidget(self.cb_confirm)

        self.btn_save = QPushButton("【儲存視覺預設檔】", scroll_content)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("QPushButton:enabled { background-color: #9333ea; color: white; }")
        self.btn_save.clicked.connect(self.save_preset)
        layout.addWidget(self.btn_save)

        self.left_tabs.addTab(tab, "視覺模組收編與編輯")

    def init_renderer_tab(self):
        tab = QWidget(self)
        tab.setStyleSheet("background-color: #0b0b0e;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("🎬 4K 音畫互動 MV 離線渲染器", tab)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        layout.addWidget(title)

        # Audio Select
        audio_box = QHBoxLayout()
        self.audio_input = QLineEdit(tab)
        self.audio_input.setPlaceholderText("選擇本地音訊檔 (.mp3, .wav) 或貼入 YouTube 網址")
        btn_browse = QPushButton("瀏覽...", tab)
        btn_browse.clicked.connect(self.browse_audio)
        audio_box.addWidget(self.audio_input)
        audio_box.addWidget(btn_browse)
        layout.addLayout(audio_box)

        # Batch Audio Folder Select
        batch_folder_box = QHBoxLayout()
        self.audio_dir_input = QLineEdit(tab)
        self.audio_dir_input.setPlaceholderText("選擇本地音訊資料夾（選填，用於批次智能剪輯與渲染）")
        btn_browse_dir = QPushButton("選擇資料夾...", tab)
        btn_browse_dir.clicked.connect(self.browse_audio_dir)
        batch_folder_box.addWidget(self.audio_dir_input)
        batch_folder_box.addWidget(btn_browse_dir)
        layout.addLayout(batch_folder_box)

        # Genre Selection
        genre_box = QHBoxLayout()
        genre_lbl = QLabel("音樂分析風格:", tab)
        self.genre_select = QComboBox(tab)
        self.genre_select.setView(QListView())
        self.genre_select.addItems(["Auto (自動偵測)", "Techno", "Dub Techno", "Lo-fi", "Ambient", "DnB", "EDM", "Jazz", "IDM", "Hard Techno", "Rock", "POP"])
        genre_box.addWidget(genre_lbl)
        genre_box.addWidget(self.genre_select)
        layout.addLayout(genre_box)

        # Visual selection header & sort/view-mode comboboxes
        header_box = QHBoxLayout()
        header_box.setContentsMargins(0, 0, 0, 0)
        
        lbl_list_title = QLabel("選擇本影片採用的視覺模組 (可多選，演算法自動分段調度):", tab)
        header_box.addWidget(lbl_list_title)
        
        self.lbl_visual_count = QLabel("(已收錄: 0)", tab)
        self.lbl_visual_count.setStyleSheet("color: #a855f7; font-weight: bold; margin-left: 8px;")
        header_box.addWidget(self.lbl_visual_count)
        
        header_box.addStretch()
        
        # 🔍 搜尋過濾輸入框 (可搜尋名稱、作者或標籤)
        lbl_search = QLabel("🔍 搜尋/標籤:", tab)
        self.search_input = QLineEdit(tab)
        self.search_input.setPlaceholderText("輸入關鍵字或 Tag...")
        self.search_input.setFixedWidth(180)
        self.search_input.textChanged.connect(self.refresh_presets_list)
        header_box.addWidget(lbl_search)
        header_box.addWidget(self.search_input)
        
        # 檢視模式下拉選單
        lbl_view_mode = QLabel("模式:", tab)
        self.view_mode_select = QComboBox(tab)
        self.view_mode_select.setView(QListView())
        self.view_mode_select.addItems(["🎨 網格卡片", "📝 表格列表"])
        self.view_mode_select.setFixedWidth(120)
        self.view_mode_select.currentIndexChanged.connect(self.refresh_presets_list)
        header_box.addWidget(lbl_view_mode)
        header_box.addWidget(self.view_mode_select)
        
        lbl_sort = QLabel("排序:", tab)
        self.sort_select = QComboBox(tab)
        self.sort_select.setView(QListView())
        self.sort_select.addItems([
            "⭐ 我的最愛優先",
            "名稱 (A-Z)", "名稱 (Z-A)", 
            "日期 (由新到舊)", "日期 (由舊到新)", 
            "使用次數 (由多到少)", "使用次數 (由少到多)",
            "📅 加入時間 (由新到舊)", "📅 加入時間 (由舊到新)"
        ])
        self.sort_select.setFixedWidth(150)
        self.sort_select.currentIndexChanged.connect(self.refresh_presets_list)
        
        header_box.addWidget(lbl_sort)
        header_box.addWidget(self.sort_select)
        layout.addLayout(header_box)
        
        self.visual_list = QListWidget(tab)
        self.visual_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.visual_list.itemClicked.connect(self.on_visual_list_item_clicked)
        self.visual_list.itemDoubleClicked.connect(self.on_visual_list_item_clicked)
        layout.addWidget(self.visual_list)

        # Pagination controls
        pagination_layout = QHBoxLayout()
        pagination_layout.setContentsMargins(0, 5, 0, 5)
        
        self.btn_prev_page = QPushButton("◀ 上一頁", tab)
        self.btn_prev_page.setFixedWidth(100)
        self.btn_prev_page.setStyleSheet("""
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; font-size: 11px; padding: 4px 10px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
        """)
        self.btn_prev_page.clicked.connect(self.prev_presets_page)
        
        self.lbl_page_info = QLabel("第 1 頁，共 1 頁", tab)
        self.lbl_page_info.setStyleSheet("color: #a1a1aa; font-weight: bold; font-size: 12px;")
        self.lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_next_page = QPushButton("下一頁 ▶", tab)
        self.btn_next_page.setFixedWidth(100)
        self.btn_next_page.setStyleSheet("""
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; font-size: 11px; padding: 4px 10px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
        """)
        self.btn_next_page.clicked.connect(self.next_presets_page)
        
        pagination_layout.addWidget(self.btn_prev_page)
        pagination_layout.addWidget(self.lbl_page_info, stretch=1)
        pagination_layout.addWidget(self.btn_next_page)
        layout.addLayout(pagination_layout)

        # Actions row (refresh and clean visual modules)
        action_row = QHBoxLayout()
        
        btn_refresh = QPushButton("🔄 整理並重新載入視覺清單", tab)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #18181b; color: #a1a1aa; border: 1px solid #27272a;
                border-radius: 6px; padding: 8px; font-size: 12px;
            }
            QPushButton:hover {
                background-color: #27272a; color: #f4f4f5; border-color: #3f3f46;
            }
        """)
        btn_refresh.clicked.connect(lambda: self.refresh_presets_list(clean_black=True))
        
        btn_cleanup = QPushButton("🧹 試運行並清理視覺模組庫", tab)
        btn_cleanup.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed; color: #ffffff; border: 1px solid #7c3aed;
                border-radius: 6px; padding: 8px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8b5cf6; border-color: #8b5cf6;
            }
        """)
        btn_cleanup.clicked.connect(self.open_module_cleanup_dialog)
        
        btn_download_deps = QPushButton("📥 下載所有模組本地依賴庫", tab)
        btn_download_deps.setStyleSheet("""
            QPushButton {
                background-color: #10b981; color: #ffffff; border: 1px solid #10b981;
                border-radius: 6px; padding: 8px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669; border-color: #059669;
            }
        """)
        btn_download_deps.clicked.connect(self.open_dependency_downloader_dialog)
        
        btn_clear_stars = QPushButton("☆ 一鍵清除所有最愛", tab)
        btn_clear_stars.setStyleSheet("""
            QPushButton {
                background-color: #3f3f46; color: #ffffff; border: 1px solid #3f3f46;
                border-radius: 6px; padding: 8px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #52525b; border-color: #52525b;
            }
        """)
        btn_clear_stars.clicked.connect(self.clear_all_stars)
        
        action_row.addWidget(btn_refresh)
        action_row.addWidget(btn_cleanup)
        action_row.addWidget(btn_download_deps)
        action_row.addWidget(btn_clear_stars)
        layout.addLayout(action_row)

        # Export config
        config_box = QHBoxLayout()
        
        res_lbl = QLabel("導出解析度:", tab)
        self.res_select = QComboBox(tab)
        self.res_select.setView(QListView())
        self.res_select.addItems(["4K (3840x2160)", "1080p (1920x1080)", "720p (1280x720)"])
        config_box.addWidget(res_lbl)
        config_box.addWidget(self.res_select)

        fps_lbl = QLabel("FPS:", tab)
        self.fps_select = QComboBox(tab)
        self.fps_select.setView(QListView())
        self.fps_select.addItems(["30", "60"])
        config_box.addWidget(fps_lbl)
        config_box.addWidget(self.fps_select)

        self.native_4k_cb = QCheckBox("原生 4K 畫質 (關閉 1080p 降採樣)", tab)
        self.native_4k_cb.setChecked(False)
        self.native_4k_cb.setToolTip("啟用後將關閉內部的 1080p 渲染與後製降採樣限制，使用原生 4K (3840x2160) 進行渲染與 VJ 特效處理，畫面將極度銳利與清晰，但對 GPU 和記憶體效能要求極高。")
        config_box.addWidget(self.native_4k_cb)

        layout.addLayout(config_box)

        # CPU Performance mode selector
        cpu_mode_box = QHBoxLayout()
        cpu_mode_lbl = QLabel("CPU 運作模式:", tab)
        self.cpu_mode_select = QComboBox(tab)
        self.cpu_mode_select.setView(QListView())
        self.cpu_mode_select.addItems(["🌡️ 控溫模式 (自動降頻防過熱)", "🔥 全力運作 (最大速度，忽略溫控)"])
        self.cpu_mode_select.setToolTip(
            "控溫模式：每 100 幀偵測 macOS 熱管理狀態，過熱時自動降速冷卻，適合長時間渲染或筆電使用。\n"
            "全力運作：跳過所有溫控檢測，以最大 CPU 速度持續渲染，適合桌機或短片快速輸出。"
        )
        cpu_mode_box.addWidget(cpu_mode_lbl)
        cpu_mode_box.addWidget(self.cpu_mode_select)
        cpu_mode_box.addStretch()
        layout.addLayout(cpu_mode_box)

        # Transition slider
        trans_box = QHBoxLayout()
        trans_lbl = QLabel("分鏡過渡融合時間 (秒):", tab)
        self.trans_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.trans_slider.setRange(0, 30)  # 0.0s to 3.0s
        self.trans_slider.setValue(5)      # 0.5s
        self.trans_val_lbl = QLabel("0.5s", tab)
        self.trans_slider.valueChanged.connect(lambda v: self.trans_val_lbl.setText(f"{v/10.0:.1f}s"))
        trans_box.addWidget(trans_lbl)
        trans_box.addWidget(self.trans_slider)
        trans_box.addWidget(self.trans_val_lbl)
        layout.addLayout(trans_box)

        # Global Post-FX Probability Slider
        fx_prob_box = QHBoxLayout()
        fx_prob_lbl = QLabel("全域後製特效出現機率:", tab)
        self.fx_prob_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.fx_prob_slider.setRange(0, 100)  # 0% to 100%
        self.fx_prob_slider.setValue(25)       # Default: 25%
        self.fx_prob_val_lbl = QLabel("25%", tab)
        self.fx_prob_slider.valueChanged.connect(lambda v: self.fx_prob_val_lbl.setText(f"{v}%"))
        fx_prob_box.addWidget(fx_prob_lbl)
        fx_prob_box.addWidget(self.fx_prob_slider)
        fx_prob_box.addWidget(self.fx_prob_val_lbl)
        layout.addLayout(fx_prob_box)

        # Global Post-FX Type Checkboxes
        fx_type_lbl = QLabel("全域後製特效種類與自適應調製:", tab)
        fx_type_lbl.setStyleSheet("color: #d4d4d8; font-weight: bold; margin-top: 4px;")
        layout.addWidget(fx_type_lbl)
        
        # Row 1: Basic Effects
        fx_type_box_1 = QHBoxLayout()
        fx_type_box_1.setSpacing(12)
        
        self.fx_cb_distortion = QCheckBox("幾何畸變", tab)
        self.fx_cb_distortion.setChecked(True)
        self.fx_cb_distortion.setToolTip("類別 1: 空間折疊與幾何畸變 — 魚眼、桶狀畸變與極座標轉換，讓畫面隨低音能量或強拍拉伸與扭轉")
        
        self.fx_cb_fluid_noise = QCheckBox("流體噪訊", tab)
        self.fx_cb_fluid_noise.setChecked(True)
        self.fx_cb_fluid_noise.setToolTip("類別 2: 流體與動態噪訊場 — fBm 分形噪訊領域扭曲 (Domain Warping) 與即時流體漩渦模擬")
        
        self.fx_cb_feedback_dynamics = QCheckBox("時空反饋", tab)
        self.fx_cb_feedback_dynamics.setChecked(True)
        self.fx_cb_feedback_dynamics.setToolTip("類別 3: 時空反饋與迭代動力學 — 環形緩衝時間置換狹縫掃描 (Slit-Scan) 與反應擴散 Gray-Scott 細胞增殖反饋")
        
        self.fx_cb_color_aberration = QCheckBox("光譜色彩", tab)
        self.fx_cb_color_aberration.setChecked(True)
        self.fx_cb_color_aberration.setToolTip("類別 4: 色彩光譜與光學異常 — 多採樣徑向邊緣色散與 Inigo Quilez 餘弦漸層全域色彩循環")
        
        self.fx_cb_glow_illumination = QCheckBox("高階光影", tab)
        self.fx_cb_glow_illumination.setChecked(True)
        self.fx_cb_glow_illumination.setToolTip("類別 5: 高階光影與動態發光 — Kawase 降採樣電影級發光 (Bloom) 與螢幕空間放射狀體積光 (God Rays)")

        self.fx_cb_retro_degradation = QCheckBox("訊號退化", tab)
        self.fx_cb_retro_degradation.setChecked(True)
        self.fx_cb_retro_degradation.setToolTip("類別 6: 訊號退化與復古降維 — 45 度旋轉印刷網點半色調與 CRT 掃描線、像素格柵與滾動干擾條")

        self.fx_cb_pixel_sort = QCheckBox("像素分選", tab)
        self.fx_cb_pixel_sort.setChecked(True)
        self.fx_cb_pixel_sort.setToolTip("類別 7: 矩陣重組與像素分選 — 亮度閥值水平連續像素排序拉絲與數位色塊 Glitch 故障藝術")

        self.fx_cb_kaleidoscope = QCheckBox("鏡像萬花筒", tab)
        self.fx_cb_kaleidoscope.setChecked(True)
        self.fx_cb_kaleidoscope.setToolTip("類別 8: 對稱鏡像萬花筒 — 極座標轉換放射狀對稱反射曼陀羅圖案，隨低音能量收縮")

        self.fx_cb_ambient_dsp = QCheckBox("空靈聲學", tab)
        self.fx_cb_ambient_dsp.setChecked(True)
        self.fx_cb_ambient_dsp.setToolTip("類別 10: 空靈聲學模擬 — 混響視覺尾音(Reverb Tail)、回音分身(Delay Echo)與悶音低通濾波(Low-pass)")

        self.fx_cb_adaptive = QCheckBox("情緒自適應調製", tab)
        self.fx_cb_adaptive.setChecked(True)
        self.fx_cb_adaptive.setToolTip("聽覺感知情緒調製 — 依據樂曲能量(Arousal)與情感(Valence)動態微調後製特效強度與機率")
        
        for cb in [self.fx_cb_distortion, self.fx_cb_fluid_noise, self.fx_cb_feedback_dynamics, self.fx_cb_color_aberration, self.fx_cb_glow_illumination, self.fx_cb_retro_degradation, self.fx_cb_pixel_sort, self.fx_cb_kaleidoscope, self.fx_cb_ambient_dsp, self.fx_cb_adaptive]:
            cb.setStyleSheet("QCheckBox { color: #a1a1aa; } QCheckBox::indicator { width: 16px; height: 16px; }")
            fx_type_box_1.addWidget(cb)
        fx_type_box_1.addStretch()
        layout.addLayout(fx_type_box_1)

        # Row 2: Advanced Global Channels & Derivative Effects
        fx_type_box_2 = QHBoxLayout()
        fx_type_box_2.setSpacing(12)

        self.fx_cb_data_mosh = QCheckBox("數位撕裂", tab)
        self.fx_cb_data_mosh.setChecked(True)
        self.fx_cb_data_mosh.setToolTip("全域通道 A: 數位撕裂 (Data-Mosh) — 運動向量邊緣像素拉絲錯位與 Glitch 故障撕裂感")

        self.fx_cb_sedimentation = QCheckBox("流沙沉澱", tab)
        self.fx_cb_sedimentation.setChecked(True)
        self.fx_cb_sedimentation.setToolTip("全域通道 B: 流沙沉澱 (Sedimentation) — 高光邊緣粒子緩慢下沉累積與 Sub-Bass 揚塵模擬")

        self.fx_cb_vector_scan = QCheckBox("雷射等高線", tab)
        self.fx_cb_vector_scan.setChecked(True)
        self.fx_cb_vector_scan.setToolTip("全域通道 C: 雷射等高線 (Vector Scan) — 頻譜自適應邊緣提取與雷射向量示波投影")

        self.fx_cb_temporal_fractal = QCheckBox("時空分形鏡", tab)
        self.fx_cb_temporal_fractal.setChecked(True)
        self.fx_cb_temporal_fractal.setToolTip("全域通道 D: 時空對稱分形鏡 (Temporal Fractal) — 當前影格與歷史延遲幀水平差值翻轉分形")

        self.fx_cb_phase_slit = QCheckBox("相位剪切", tab)
        self.fx_cb_phase_slit.setChecked(True)
        self.fx_cb_phase_slit.setToolTip("衍生通道 1: 相位剪切 (Phase Slit-Scan) — 左右聲道相位差引起之非對稱時間延遲與時空左右剪切")

        self.fx_cb_centroid_glitch = QCheckBox("高頻破碎", tab)
        self.fx_cb_centroid_glitch.setChecked(True)
        self.fx_cb_centroid_glitch.setToolTip("衍生通道 2: 高頻破碎 (Centroid Glitch) — 頻譜質心共振時橫向切片隨機橫移，共振電晶體質地")

        self.fx_cb_vignette_pulse = QCheckBox("呼吸暗房", tab)
        self.fx_cb_vignette_pulse.setChecked(False)
        self.fx_cb_vignette_pulse.setToolTip("衍生通道 3: 呼吸暗房 (Vignette Pulse) — 正拍預期心理學四周暗角飽和度抽離收縮與砸拍高光釋放")

        self.fx_cb_tension_overlay = QCheckBox("張力互斥", tab)
        self.fx_cb_tension_overlay.setChecked(False)
        self.fx_cb_tension_overlay.setToolTip("衍生通道 4: 張力互斥 (Tension Overlay) — 不協和和弦與畫面產生數學互斥 (Exclusion) 撞色翻轉")

        self.fx_cb_photosensitive_safe = QCheckBox("光敏健康防護", tab)
        self.fx_cb_photosensitive_safe.setChecked(True)
        self.fx_cb_photosensitive_safe.setToolTip("光敏健康保護與防癲癇機制 — 限制高頻閃爍、劇烈色彩翻轉與全螢幕高光刺激，提供兼顧畫面美學與醫療安全的視覺感受")

        for cb in [self.fx_cb_data_mosh, self.fx_cb_sedimentation, self.fx_cb_vector_scan, self.fx_cb_temporal_fractal, self.fx_cb_phase_slit, self.fx_cb_centroid_glitch, self.fx_cb_vignette_pulse, self.fx_cb_tension_overlay, self.fx_cb_photosensitive_safe]:
            cb.setStyleSheet("QCheckBox { color: #a1a1aa; } QCheckBox::indicator { width: 16px; height: 16px; }")
            fx_type_box_2.addWidget(cb)
        fx_type_box_2.addStretch()
        layout.addLayout(fx_type_box_2)
        self.fx_cb_photosensitive_safe.toggled.connect(self.update_photosensitive_safe_preview)

        # Row 3: New VJ Custom Effects (Thermal Vision, Scanline Glitch, Frame Drop, Dynamic Mosaic, Pixel Art, Handheld Camera, Stylized Fade, Zoom Pulse)
        fx_type_box_3 = QHBoxLayout()
        fx_type_box_3.setSpacing(12)
        
        self.fx_cb_thermal_vision = QCheckBox("熱成像", tab)
        self.fx_cb_thermal_vision.setChecked(True)
        self.fx_cb_thermal_vision.setToolTip("自訂擴充 1: 熱成像 (Thermal Vision) — 鐵血戰士霓虹邊緣、頻譜自適應冷熱分區與熱浪消融")
        
        self.fx_cb_scanline_glitch = QCheckBox("掃描故障", tab)
        self.fx_cb_scanline_glitch.setChecked(True)
        self.fx_cb_scanline_glitch.setToolTip("自訂擴充 2: 掃描故障 (Scanline Glitch) — VHS追軌同步漂移、R/G/B色差抖動與模擬訊號丟失滾動")
        
        self.fx_cb_frame_drop = QCheckBox("掉幀特效", tab)
        self.fx_cb_frame_drop.setChecked(True)
        self.fx_cb_frame_drop.setToolTip("自訂擴充 3: 掉幀特效 (Frame Drop) — 動態能量定格動畫、BPM量化節奏定格與混響殘影凍結")
        
        self.fx_cb_dynamic_mosaic = QCheckBox("動態馬賽克", tab)
        self.fx_cb_dynamic_mosaic.setChecked(True)
        self.fx_cb_dynamic_mosaic.setToolTip("自訂擴充 4: 動態馬賽克 (Dynamic Mosaic) — 低音爆裂格柵大小調製、旋轉斜切馬賽克與碎裂座標漂移")
        
        self.fx_cb_pixel_art = QCheckBox("像素畫", tab)
        self.fx_cb_pixel_art.setChecked(True)
        self.fx_cb_pixel_art.setToolTip("自訂擴充 5: 像素畫 (Pixel Art) — GameBoy復古液晶調色盤、漫畫像素黑線勾邊與賽博朋克霓虹色度限制")
        
        self.fx_cb_handheld_camera = QCheckBox("手持相機", tab)
        self.fx_cb_handheld_camera.setChecked(True)
        self.fx_cb_handheld_camera.setToolTip("自訂擴充 6: 手持相機 (Handheld Camera) — 有機呼吸鏡頭漂移、CCTV/DV錄影框資訊與魚眼廣角極限晃鏡")
        
        self.fx_cb_stylized_fade = QCheckBox("藝術淡入出", tab)
        self.fx_cb_stylized_fade.setChecked(True)
        self.fx_cb_stylized_fade.setToolTip("自訂擴充 7: 藝術淡入淡出 (Stylized Fade) — 噪訊腐蝕沙化溶解、光束快門收縮與垂直流淌融化")
        
        self.fx_cb_zoom_pulse = QCheckBox("縮放脈衝", tab)
        self.fx_cb_zoom_pulse.setChecked(True)
        self.fx_cb_zoom_pulse.setToolTip("自訂擴充 8: 縮放脈衝 (Zoom Pulse) — 低音砸拍縮放、旋轉縮放無限反饋隧道與R/G/B分通道立體縮放")

        for cb in [self.fx_cb_thermal_vision, self.fx_cb_scanline_glitch, self.fx_cb_frame_drop, self.fx_cb_dynamic_mosaic, self.fx_cb_pixel_art, self.fx_cb_handheld_camera, self.fx_cb_stylized_fade, self.fx_cb_zoom_pulse]:
            cb.setStyleSheet("QCheckBox { color: #a1a1aa; } QCheckBox::indicator { width: 16px; height: 16px; }")
            fx_type_box_3.addWidget(cb)
        fx_type_box_3.addStretch()
        layout.addLayout(fx_type_box_3)

        # Row 4: Top Tier Global Post-FX Matrix (Film Burn, Blueprint Edge, Turing Pattern, Point Cloud Depth, Vector Scope, Lowpass Muffle, Infinity Tunnel, Dolly Zoom)
        fx_type_box_4 = QHBoxLayout()
        fx_type_box_4.setSpacing(12)
        
        self.fx_cb_film_burn = QCheckBox("膠片腐蝕", tab)
        self.fx_cb_film_burn.setChecked(True)
        self.fx_cb_film_burn.setToolTip("全新維度 1: 膠片燒灼與化學腐蝕 (Film Burn) — 35mm硝酸底片高溫邊緣發黃發紅、硝酸銀顆粒與重拍底片跳齒漏光")

        self.fx_cb_blueprint = QCheckBox("建築藍圖", tab)
        self.fx_cb_blueprint.setChecked(True)
        self.fx_cb_blueprint.setToolTip("全新維度 2: 建築藍圖與 CAD 線稿 (Blueprint Edge) — 普魯士藍圖紙、細緻 Canny 邊緣與動態毫米標尺/CAD 坐標 overlay")

        self.fx_cb_turing = QCheckBox("圖靈細胞", tab)
        self.fx_cb_turing.setChecked(True)
        self.fx_cb_turing.setToolTip("全新維度 3: 圖靈擴散與生物斑紋 (Turing Pattern) — Gray-Scott 化學反應擴散、斑馬紋與珊瑚有機細胞增殖蔓延")

        self.fx_cb_point_cloud = QCheckBox("點雲深度", tab)
        self.fx_cb_point_cloud.setChecked(True)
        self.fx_cb_point_cloud.setToolTip("全新維度 4: 點雲立體深度重構 (Point Cloud Depth) — 依據 2D 亮度估算 3D Z-Depth、粒子點雲拉伸與虛擬鏡頭 Pitch/Yaw 旋轉")

        self.fx_cb_vector_scope = QCheckBox("聲相示波", tab)
        self.fx_cb_vector_scope.setChecked(True)
        self.fx_cb_vector_scope.setToolTip("全新維度 5: 聲相向量示波鏡 (Vector Scope) — Lissajous 示波器時域波形霓虹圖騰與背景光學折射屈光透鏡")

        self.fx_cb_lowpass_muffle = QCheckBox("悶音景深", tab)
        self.fx_cb_lowpass_muffle.setChecked(True)
        self.fx_cb_lowpass_muffle.setToolTip("全新維度 6: 低通悶音景深遮罩 (Low-Pass Muffle) — 隔牆水下沉浸感、多級高斯景深模糊與動態呼吸暗角影視語言")

        self.fx_cb_infinity_tunnel = QCheckBox("無限鏡廊", tab)
        self.fx_cb_infinity_tunnel.setChecked(True)
        self.fx_cb_infinity_tunnel.setToolTip("全新維度 7: 無限幾何鏡廊 (Infinity Tunnel) — 幾何對數極座標 Log-Polar 投影與飛速向前穿梭之鏡室隧道錯覺")

        self.fx_cb_dolly_zoom = QCheckBox("眩暈推拉", tab)
        self.fx_cb_dolly_zoom.setChecked(True)
        self.fx_cb_dolly_zoom.setToolTip("全新維度 8: 眩暈推拉變焦 (Dolly Zoom) — 希區考克 Vertigo 鏡頭語言、主體保持不變與背景飛速拉遠變大放射狀模糊")

        for cb in [self.fx_cb_film_burn, self.fx_cb_blueprint, self.fx_cb_turing, self.fx_cb_point_cloud, self.fx_cb_vector_scope, self.fx_cb_lowpass_muffle, self.fx_cb_infinity_tunnel, self.fx_cb_dolly_zoom]:
            cb.setStyleSheet("QCheckBox { color: #a1a1aa; } QCheckBox::indicator { width: 16px; height: 16px; }")
            fx_type_box_4.addWidget(cb)
        fx_type_box_4.addStretch()
        layout.addLayout(fx_type_box_4)

        # Row 5: Next-Gen 6 Advanced Global Post-FX
        fx_type_box_5 = QHBoxLayout()
        fx_type_box_5.setSpacing(12)
        
        self.fx_cb_hologram_glitch = QCheckBox("全息干擾", tab)
        self.fx_cb_hologram_glitch.setChecked(True)
        self.fx_cb_hologram_glitch.setToolTip("前沿全域 1: 全息掃描干擾 (Hologram Glitch) — 科幻全息掃描光條、RGB 撕裂與雷射干擾線")

        self.fx_cb_voronoi_shatter = QCheckBox("泰森碎裂", tab)
        self.fx_cb_voronoi_shatter.setChecked(True)
        self.fx_cb_voronoi_shatter.setToolTip("前沿全域 2: 泰森多邊形碎裂折射 (Voronoi Shatter) — 水晶幾何切片碎裂與低音動態折射")

        self.fx_cb_thermal_infrared = QCheckBox("紅外熱感", tab)
        self.fx_cb_thermal_infrared.setChecked(True)
        self.fx_cb_thermal_infrared.setToolTip("前沿全域 3: 軍規紅外熱感視界 (Thermal Infrared) — 賽博紅外熱感光譜與冷熱頻譜過渡")

        self.fx_cb_ascii_cyber_matrix = QCheckBox("矩陣字元", tab)
        self.fx_cb_ascii_cyber_matrix.setChecked(True)
        self.fx_cb_ascii_cyber_matrix.setToolTip("前沿全域 4: 高階動態 Cyber ASCII 碼雨 (ASCII Matrix Rain) — 數位字元矩陣與重拍脈衝高光")

        self.fx_cb_chromatic_radial_zoom = QCheckBox("色差爆發", tab)
        self.fx_cb_chromatic_radial_zoom.setChecked(True)
        self.fx_cb_chromatic_radial_zoom.setToolTip("前沿全域 5: 色差徑向爆發衝擊 (Chromatic Radial Zoom) — 重拍中心向外徑向色差與動態 Zoom 衝擊")

        self.fx_cb_synthwave_grid_scan = QCheckBox("賽博網格", tab)
        self.fx_cb_synthwave_grid_scan.setChecked(True)
        self.fx_cb_synthwave_grid_scan.setToolTip("前沿全域 6: 賽博波形網格掃描 (Synthwave 3D Grid) — 復古網格線條、地平線掃描與波型震蕩")

        for cb in [self.fx_cb_hologram_glitch, self.fx_cb_voronoi_shatter, self.fx_cb_thermal_infrared, self.fx_cb_ascii_cyber_matrix, self.fx_cb_chromatic_radial_zoom, self.fx_cb_synthwave_grid_scan]:
            cb.setStyleSheet("QCheckBox { color: #a1a1aa; } QCheckBox::indicator { width: 16px; height: 16px; }")
            fx_type_box_5.addWidget(cb)
        fx_type_box_5.addStretch()
        layout.addLayout(fx_type_box_5)

        # Progress bar
        self.progress_bar = QProgressBar(tab)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("準備就緒", tab)
        self.status_lbl.setStyleSheet("color: #a1a1aa;")
        layout.addWidget(self.status_lbl)

        # 🎬 AI 導演通告單可視化卡片 (Director Call Sheet Panel)
        self.call_sheet_widget = AIDirectorCallSheetWidget(tab)
        layout.addWidget(self.call_sheet_widget)

        # Render buttons layout
        btn_box = QHBoxLayout()
        self.btn_ai_director = QPushButton("🎬 【AI 導演智能排片 (LLM Script)】", tab)
        self.btn_ai_director.setStyleSheet("background-color: #9333ea; color: white; font-size: 13px; padding: 12px; font-weight: bold; border-radius: 6px;")
        self.btn_ai_director.clicked.connect(self.start_ai_director_orchestration)

        self.btn_smart_edit = QPushButton("🪄 智能剪輯配對並渲染", tab)
        self.btn_smart_edit.setStyleSheet("background-color: #7c3aed; color: white; font-size: 13px; padding: 12px; font-weight: bold; border-radius: 6px;")
        self.btn_smart_edit.clicked.connect(self.start_smart_edit_rendering)

        self.btn_batch_smart_edit = QPushButton("🪄 批次智能剪輯配對並渲染", tab)
        self.btn_batch_smart_edit.setStyleSheet("background-color: #4f46e5; color: white; font-size: 13px; padding: 12px; font-weight: bold; border-radius: 6px;")
        self.btn_batch_smart_edit.clicked.connect(self.start_batch_smart_edit_rendering)

        self.btn_render = QPushButton("🚀 一鍵開始渲染 4K MV", tab)
        self.btn_render.setStyleSheet("background-color: #059669; color: white; font-size: 13px; padding: 12px; font-weight: bold; border-radius: 6px;")
        self.btn_render.clicked.connect(self.start_mv_rendering)
        
        self.btn_cancel_render = QPushButton("⏹️ 中止", tab)
        self.btn_cancel_render.setStyleSheet("background-color: #b91c1c; color: white; font-size: 13px; padding: 12px; border-radius: 6px;")
        self.btn_cancel_render.clicked.connect(self.cancel_mv_rendering)
        self.btn_cancel_render.setEnabled(False)
        
        btn_box.addWidget(self.btn_ai_director, 3)
        btn_box.addWidget(self.btn_smart_edit, 2)
        btn_box.addWidget(self.btn_batch_smart_edit, 2)
        btn_box.addWidget(self.btn_render, 2)
        btn_box.addWidget(self.btn_cancel_render, 1)
        layout.addLayout(btn_box)

        self.left_tabs.addTab(tab, "4K 影片離線渲染器")

    def update_photosensitive_safe_preview(self):
        val = str(self.fx_cb_photosensitive_safe.isChecked()).lower()
        try:
            self.web_view.page().runJavaScript(f"window.photosensitiveSafe = {val};")
        except Exception:
            pass

    def create_slider_row(self, layout, title, parent):
        row = QHBoxLayout()
        lbl = QLabel(title, parent)
        lbl.setFixedWidth(180)
        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(0, 100)
        slider.setValue(50)
        val_lbl = QLabel("50%", parent)
        val_lbl.setFixedWidth(40)
        slider.valueChanged.connect(lambda v: val_lbl.setText(f"{v}%"))
        
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_lbl)
        layout.addLayout(row)
        return slider

    def browse_audio(self):
        file_path, _ = safe_get_open_file_name(self, "選擇音訊檔案", "", "Audio Files (*.mp3 *.wav *.m4a *.flac)")
        if file_path:
            self.audio_input.setText(file_path)

    def browse_audio_dir(self):
        dir_path = safe_get_existing_directory(self, "選擇音訊來源資料夾")
        if dir_path:
            self.audio_dir_input.setText(dir_path)

    def append_tag(self, tag):
        current = self.tags_input.text().strip()
        tags_list = [t.strip() for t in current.split(",") if t.strip()]
        if tag not in tags_list:
            tags_list.append(tag)
        self.tags_input.setText(", ".join(tags_list))

    def refresh_presets_list(self, *args, clean_black=False, keep_page=False):
        if not keep_page:
            self.presets_current_page = 1

        # Save vertical scroll position to prevent view resetting to top on rebuild
        scroll_bar = self.visual_list.verticalScrollBar()
        scroll_value = scroll_bar.value() if scroll_bar else 0

        self.visual_list.clear()
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)
        
        if clean_black:
            # Auto-detect and delete black thumbnails once
            for file in os.listdir(save_dir):
                if file.endswith(".json"):
                    name = file[:-5]
                    thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
                    if os.path.exists(thumb_path):
                        try:
                            from PIL import Image as PILImage
                            with PILImage.open(thumb_path) as img:
                                extrema = img.convert("L").getextrema()
                                if extrema and extrema[1] < 15:  # Max brightness is less than 15 out of 255
                                    os.remove(thumb_path)
                                    self.log_to_console(f"🗑️ 檢測到全黑預覽圖，已清除「{name}」以重新生成...")
                        except Exception as e:
                            pass
        
        # 決定 View Mode (0: 網格卡片, 1: 表格列表)
        view_mode = 0
        if hasattr(self, "view_mode_select"):
            view_mode = self.view_mode_select.currentIndex()
            
        if view_mode == 0:
            self.visual_list.setViewMode(QListWidget.ViewMode.IconMode)
            self.visual_list.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.visual_list.setMovement(QListWidget.Movement.Static)
            self.visual_list.setUniformItemSizes(True)
            self.visual_list.setSpacing(10)
            self.visual_list.setStyleSheet("""
                QListWidget {
                    background-color: #09090b;
                    border: 1px solid #27272a;
                    border-radius: 10px;
                    padding: 8px;
                }
                QListWidget::item:selected {
                    background: transparent;
                    border: none;
                }
                QListWidget::item:hover {
                    background: transparent;
                    border: none;
                }
            """)
        else:
            self.visual_list.setViewMode(QListWidget.ViewMode.ListMode)
            self.visual_list.setSpacing(2)
            self.visual_list.setStyleSheet("") # 回復全域設定
        
        # 記憶體快取加速：如果已快取且不需強行重新載入，則直接使用快取
        if getattr(self, "cached_presets", None) is not None and not clean_black:
            presets_data = list(self.cached_presets)
        else:
            presets_data = []
            for file in os.listdir(save_dir):
                if file.endswith(".json") and file not in ("modules_index.json", "module_usage_history.json"):
                    name = file[:-5]
                    p_path = os.path.join(save_dir, file)
                    tags = []
                    author = "未知"
                    license_mode = "未知"
                    date_added = ""
                    url = ""
                    frequency = 50
                    storyboard_weight = 50
                    post_fx_intensity = 50
                    
                    # 取得檔案修改時間作為 fallback
                    try:
                        mtime = os.path.getmtime(p_path)
                        ctime = os.path.getctime(p_path)
                        import datetime
                        fallback_date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                        created_time_str = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        fallback_date = "2026-06-25 00:00:00"
                        created_time_str = "2026-06-25 00:00:00"
                    
                    is_starred = False
                    display_name = name
                    try:
                        with open(p_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if not isinstance(data, dict) or 'code' not in data:
                                continue
                            tags = data.get("tags", [])
                            author = data.get("author", "未知")
                            license_mode = data.get("license", "未知")
                            url = data.get("url", "").strip()
                            date_added = data.get("date_added", "").strip()
                            frequency = data.get("frequency", 50)
                            storyboard_weight = data.get("storyboard_weight", 50)
                            post_fx_intensity = data.get("post_fx_intensity", 50)
                            display_name = data.get("name", name)
                            is_starred = data.get("is_starred", False)
                            used_in = data.get("used_in_videos", [])
                            used_count = max(int(data.get("used_count", 0)), len(used_in) if isinstance(used_in, list) else 0)
                            if not date_added:
                                date_added = fallback_date
                    except Exception as e:
                        print(f"讀取預設檔元數據失敗: {e}")
                        date_added = fallback_date
                        used_count = 0
                    
                    thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
                    
                    presets_data.append({
                        "name": name,
                        "display_name": display_name,
                        "tags": tags,
                        "author": author,
                        "license_mode": license_mode,
                        "date_added": date_added,
                        "join_time": created_time_str,
                        "url": url,
                        "thumbnail_path": thumb_path if os.path.exists(thumb_path) else "",
                        "frequency": frequency,
                        "storyboard_weight": storyboard_weight,
                        "post_fx_intensity": post_fx_intensity,
                        "used_count": used_count,
                        "is_starred": is_starred
                    })
            self.cached_presets = list(presets_data)
        
        # 🔍 搜尋過濾邏輯：如果 search_input 內有輸入內容，進行模糊過濾
        if hasattr(self, "search_input") and self.search_input.text().strip():
            query = self.search_input.text().strip().lower()
            filtered_presets = []
            for p in presets_data:
                # 匹配顯示名稱、檔案名稱、作者、或標籤陣列
                matches_name = query in p["display_name"].lower() or query in p["name"].lower()
                matches_author = query in p["author"].lower()
                matches_tag = any(query in t.lower() for t in p["tags"])
                
                if matches_name or matches_author or matches_tag:
                    filtered_presets.append(p)
            presets_data = filtered_presets
            
        # 根據 sort_select 的選取狀態進行排序
        # 0: 我的最愛優先, 1: 名稱 (A-Z), 2: 名稱 (Z-A), 3: 日期 (由新到舊), 4: 日期 (由舊到新)
        sort_idx = 0
        if hasattr(self, "sort_select"):
            sort_idx = self.sort_select.currentIndex()
            
        if sort_idx == 0:
            # ⭐ 我的最愛優先 (將 is_starred 為 True 的置頂，隨後按名稱 A-Z)
            presets_data.sort(key=lambda x: (not x["is_starred"], x["name"].lower()))
        elif sort_idx == 1:
            presets_data.sort(key=lambda x: x["name"].lower())
        elif sort_idx == 2:
            presets_data.sort(key=lambda x: x["name"].lower(), reverse=True)
        elif sort_idx == 3:
            presets_data.sort(key=lambda x: x["date_added"], reverse=True)
        elif sort_idx == 4:
            presets_data.sort(key=lambda x: x["date_added"])
        elif sort_idx == 5:
            presets_data.sort(key=lambda x: x["used_count"], reverse=True)
        elif sort_idx == 6:
            presets_data.sort(key=lambda x: x["used_count"])
        elif sort_idx == 7:
            # 📅 加入時間 (由新到舊)
            presets_data.sort(key=lambda x: x.get("join_time", ""), reverse=True)
        elif sort_idx == 8:
            # 📅 加入時間 (由舊到新)
            presets_data.sort(key=lambda x: x.get("join_time", ""))
            
        # 更新已收錄模組的數量顯示
        total_presets = len(presets_data)
        if hasattr(self, "lbl_visual_count"):
            self.lbl_visual_count.setText(f"(已收錄: {total_presets})")
            
        # Calculate pagination
        import math
        self.presets_max_pages = max(1, math.ceil(total_presets / self.presets_page_size))
        if self.presets_current_page > self.presets_max_pages:
            self.presets_current_page = self.presets_max_pages
            
        if hasattr(self, "lbl_page_info"):
            self.lbl_page_info.setText(f"第 {self.presets_current_page} 頁，共 {self.presets_max_pages} 頁 (每頁 {self.presets_page_size} 個 / 總計 {total_presets})")
            
        start_idx = (self.presets_current_page - 1) * self.presets_page_size
        end_idx = start_idx + self.presets_page_size
        presets_page_data = presets_data[start_idx:end_idx]
            
        for data in presets_page_data:
            item = QListWidgetItem(self.visual_list)
            self.visual_list.addItem(item)
            
            if view_mode == 0:
                # 網格卡片模式
                widget = VisualModuleCardWidget(
                    data["name"], data["tags"], data["author"], data["license_mode"], data["date_added"],
                    data["thumbnail_path"], data["frequency"], data["storyboard_weight"], data["post_fx_intensity"],
                    data["used_count"],
                    self.delete_preset, self.preview_preset, self.toggle_star_preset, self.visual_list,
                    display_name=data["display_name"], is_starred=data["is_starred"]
                )
            else:
                # 表格列表模式
                widget = VisualModuleItemWidget(
                    data["name"], data["tags"], data["author"], data["license_mode"], data["date_added"],
                    data["frequency"], data["storyboard_weight"], data["post_fx_intensity"],
                    self.delete_preset, self.toggle_star_preset, self.visual_list,
                    display_name=data["display_name"], is_starred=data["is_starred"],
                    on_preview_callback=self.preview_preset
                )
                
            item.setSizeHint(widget.sizeHint())
            self.visual_list.setItemWidget(item, widget)
            
            # Restore selection state from checked_presets and bind toggle slot
            widget.checkbox.setChecked(data["name"] in self.checked_presets)
            widget.checkbox.stateChanged.connect(lambda state, n=data["name"]: self.on_preset_checked_toggled(n, state))
            
        self.log_to_console("視覺預設清單已重新整理並完成排序。")
        # Restore scroll position on next tick after Qt completes layout
        if scroll_value > 0 and scroll_bar:
            QTimer.singleShot(50, lambda: scroll_bar.setValue(scroll_value))
        # 啟動非同步預覽縮圖生成佇列
        QTimer.singleShot(100, self.generate_next_missing_thumbnail)
        # 若右側沙盒尚無加載預覽，自動加載當前頁第一項以展示即時沙盒動態
        if len(presets_page_data) > 0 and not getattr(self, "current_preset_id", None):
            first_name = presets_page_data[0]["name"]
            QTimer.singleShot(400, lambda: self.preview_preset(first_name))

    def prev_presets_page(self):
        if self.presets_current_page > 1:
            self.presets_current_page -= 1
            self.refresh_presets_list(clean_black=False, keep_page=True)
            
    def next_presets_page(self):
        if self.presets_current_page < getattr(self, "presets_max_pages", 1):
            self.presets_current_page += 1
            self.refresh_presets_list(clean_black=False, keep_page=True)

    def on_preset_checked_toggled(self, name, state):
        # state can be int or Qt.CheckState enum value
        checked = (state == 2 or (hasattr(state, "value") and state.value == 2))
        if checked:
            self.checked_presets.add(name)
        else:
            self.checked_presets.discard(name)

    def on_visual_list_item_clicked(self, item):
        widget = self.visual_list.itemWidget(item)
        if widget and hasattr(widget, "module_name"):
            self.preview_preset(widget.module_name)


    def get_html_content(self, code, custom_css="", custom_html="", inline_assets=None, for_thumbnail=False, sketch_id=None, scaling_mode="auto", for_rendering=False):
        noloop_js = ""
        if for_thumbnail and not for_rendering:
            noloop_js = """
                (function() {
                  let proto = null;
                  if (typeof OriginalP5 !== 'undefined' && OriginalP5.prototype && OriginalP5.prototype._runLifecycleHook) {
                    proto = OriginalP5.prototype;
                  } else if (typeof p5 !== 'undefined' && p5.prototype && p5.prototype._runLifecycleHook) {
                    proto = p5.prototype;
                  }
                  
                  if (proto) {
                    if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] Hooking proto._runLifecycleHook");
                    const originalHook = proto._runLifecycleHook;
                    proto._runLifecycleHook = function(name) {
                      if (window.jsLogs) {
                        window.jsLogs.push("[DEBUG_NOLOOP] _runLifecycleHook called: " + name + 
                                            ", window.setup type: " + typeof window.setup + 
                                            ", this.setup type: " + typeof this.setup + 
                                            ", window.draw type: " + typeof window.draw + 
                                            ", this.draw type: " + typeof this.draw);
                      }
                      if (name === 'presetup') {
                        const setupFunc = this.setup || window.setup;
                        if (typeof setupFunc === 'function') {
                          const originalSetup = setupFunc;
                          const inst = this;
                          const wrappedSetup = function() {
                            if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] instance setup started via lifecycle hook.");
                            originalSetup.call(inst);
                            if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] instance setup originalSetup finished via lifecycle hook.");
                            if (typeof noLoop === 'function') {
                              noLoop();
                              if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] noLoop() called globally.");
                            } else if (typeof inst.noLoop === 'function') {
                              inst.noLoop();
                              if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] noLoop() called on instance.");
                            }
                          };
                          if (typeof this.setup === 'function') {
                            this.setup = wrappedSetup;
                          }
                          if (typeof window.setup === 'function') {
                            window.setup = wrappedSetup;
                          }
                        }
                      }
                      return originalHook.call(this, name);
                    };
                  } else {
                    if (window.jsLogs) window.jsLogs.push("[DEBUG_NOLOOP] Fallback: proto._runLifecycleHook not found, wrapping window.setup directly.");
                    // Fallback to global wrapping
                    const wrapGlobalSetup = () => {
                      if (typeof window.setup === 'function') {
                        const originalSetup = window.setup;
                        window.setup = function() {
                          originalSetup();
                          if (typeof noLoop === 'function') {
                            noLoop();
                          }
                        };
                      }
                    };
                    if (document.readyState === 'loading') {
                      document.addEventListener('DOMContentLoaded', wrapGlobalSetup);
                    } else {
                      wrapGlobalSetup();
                    }
                  }

                  // Restore readyState and trigger synthetic load event to initialize p5.js
                  const triggerLoad = () => {
                    try {
                      delete Document.prototype.readyState;
                    } catch(e) {}
                    try {
                      delete document.readyState;
                    } catch(e) {}
                    
                    if (window.jsLogs) {
                      window.jsLogs.push("[DEBUG_NOLOOP] Inside triggerLoad.");
                    }
                    window.dispatchEvent(new Event('load'));
                  };

                  if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', function() {
                      setTimeout(triggerLoad, 50);
                    });
                  } else {
                    setTimeout(triggerLoad, 50);
                  }
                })();
            """
        custom_html = self.cache_and_localize_scripts(custom_html or "")
        if not sketch_id:
            sketch_id = getattr(self, "current_preset_id", None)
            
        asset_override_js = ""
        if sketch_id:
            asset_override_js = f"""
            // Asset Loading Override for p5.js
            (function() {{
              const sketchId = "{sketch_id}";
              if (!sketchId || sketchId === "None") return;
              const assetSubdir = "custom_visuals/assets/" + sketchId + "/";
              const loadFuncs = ["loadImage", "loadSound", "loadFont", "loadModel", "loadStrings", "loadTable", "loadBytes", "loadXML"];
              loadFuncs.forEach(funcName => {{
                if (typeof window[funcName] === 'function') {{
                  const original = window[funcName];
                  window[funcName] = function(path, ...args) {{
                    if (typeof path === 'string' && !path.startsWith('http') && !path.startsWith('data:')) {{
                      let cleanPath = path;
                      if (cleanPath.startsWith('./')) {{
                        cleanPath = cleanPath.substring(2);
                      }} else if (cleanPath.startsWith('/')) {{
                        cleanPath = cleanPath.substring(1);
                      }}
                      path = assetSubdir + cleanPath;
                    }}
                    return original.call(this, path, ...args);
                  }};
                }}
                if (typeof p5 !== 'undefined' && p5.prototype && typeof p5.prototype[funcName] === 'function') {{
                  const original = p5.prototype[funcName];
                  p5.prototype[funcName] = function(path, ...args) {{
                    if (typeof path === 'string' && !path.startsWith('http') && !path.startsWith('data:')) {{
                      let cleanPath = path;
                      if (cleanPath.startsWith('./')) {{
                        cleanPath = cleanPath.substring(2);
                      }} else if (cleanPath.startsWith('/')) {{
                        cleanPath = cleanPath.substring(1);
                      }}
                      path = assetSubdir + cleanPath;
                    }}
                    return original.call(this, path, ...args);
                  }};
                }}
              }});
            }})();
            """
        # 🛡️ 即時 JS 代碼語法自癒修復矩陣 (Runtime JS Sanitization & Auto-Repair)
        if code:
            # 1. 自動修復未加引號的十六進位色碼 (防止 V8 引擎解析為 ES2022 Class Private Field #xxx 報錯)
            code = re.sub(r'(=|:|\(|,)\s*(#[0-9a-fA-F]{3,8})\b', r'\1 "\2"', code)
            
            # 2. 自動修復殘留的 Java 2D 陣列宣告語法 (double[][] / float[][])
            code = re.sub(
                r'\b(?:double|float|int|boolean|color|char|long|short)\s*\[\]\s*\[\]\s*(\w+)\s*=\s*new\s+\w*\[([^\]]+)\]\s*\[([^\]]+)\]\s*;',
                r'let \1 = Array.from({length: (\2)}, () => new Array(\3).fill(0));',
                code
            )
            code = re.sub(
                r'\b(?:double|float|int|boolean|color|char|long|short)\s*\[\]\s*\[\]\s*(\w+)\s*\(',
                r'function \1(',
                code
            )
            code = re.sub(
                r'\b(?:double|float|int|boolean|color|char|long|short)\s*\[\]\s*\[\]\s*(\w+)\b',
                r'\1',
                code
            )
            
            # 3. 自動修復殘留的 Java 泛型 (ArrayList<...>)
            code = re.sub(r'\bArrayList\s*<\s*\w+\s*>\s*(\w+)\s*;', r'let \1 = [];', code)
            code = re.sub(r'\bnew\s+ArrayList\s*<\s*\w+\s*>\s*\(\s*\)', r'[]', code)
            code = re.sub(r'\bArrayList\s*<\s*\w+\s*>', r'Array', code)
            
            # 4. 頂層 let / const 衝突修復 (防止多分頁或重新載入時發生 Identifier has already been declared)
            code = re.sub(r'^\s*let\s+([a-zA-Z0-9_$]+)', r'var \1', code, flags=re.MULTILINE)
            code = re.sub(r'^\s*const\s+([a-zA-Z0-9_$]+)', r'var \1', code, flags=re.MULTILINE)

        has_import_export = bool(re.search(r'\b(import\s+[\{\*a-zA-Z0-9_]|export\s+(default|const|let|var|function|class))\b', code))
        is_module = has_import_export

        script_tag = f'<script type="module">{code}\n{BIND_MODULE_CALLBACKS_JS}</script>' if is_module else f'<script>{code}</script>'

        ready_state_override_js = "Object.defineProperty(Document.prototype, 'readyState', { get: function() { return 'loading'; }, configurable: true });" if (for_thumbnail or for_rendering) else ""
        early_error_js = f"""
              <script>
                (function() {{
                  const _origWarn = console.warn;
                  console.warn = function(...args) {{
                    if (args[0] && typeof args[0] === 'string' && (args[0].includes('vectors of different sizes') || args[0].includes('linger vector'))) {{
                      return;
                    }}
                    if (typeof _origWarn === 'function') {{
                      _origWarn.apply(console, args);
                    }}
                  }};
                }})();
                window.wordsOfWisdom = window.wordsOfWisdom || ['Flow', 'Pulse', 'Vibration', 'Resonance', 'Structure', 'Echo', 'Wave', 'Core', 'Drift', 'Static', 'Horizon', 'Depth'];
                if (typeof window.getRotatedPt === 'undefined') {{
                  window.getRotatedPt = function(x, y, angle) {{
                    return {{ x: x * Math.cos(angle) - y * Math.sin(angle), y: x * Math.sin(angle) + y * Math.cos(angle) }};
                  }};
                }}
                window.createMockSoundFile = window.createMockSoundFile || function() {{
                  return {{
                    _isMockSound: true,
                    _isPlaying: false,
                    play: function() {{ this._isPlaying = true; return this; }},
                    loop: function() {{ this._isPlaying = true; return this; }},
                    stop: function() {{ this._isPlaying = false; return this; }},
                    pause: function() {{ this._isPlaying = false; return this; }},
                    isPlaying: function() {{ return this._isPlaying !== false && window.isAudioPlaying !== false; }},
                    setVolume: function() {{ return this; }},
                    pan: function() {{ return this; }},
                    rate: function() {{ return 1.0; }},
                    disconnect: function() {{ return this; }},
                    connect: function() {{ return this; }},
                    onended: function() {{}},
                    duration: function() {{ return window.totalAudioDuration || 180.0; }},
                    currentTime: function() {{ return (typeof window.custom_time_ms !== 'undefined' ? window.custom_time_ms / 1000 : (window.currentAudioTime || (window.frameCount ? window.frameCount / 60 : 0.0))); }},
                    getLevel: function() {{ return window.audioEnergy || window.beatEnergy || (typeof window.audioMid !== 'undefined' ? (window.audioLow + window.audioMid + window.audioHigh)/3 : 0.5); }},
                    getPeaks: function(n) {{ return new Float32Array(n || 5).fill(0); }},
                    buffer: {{ getChannelData: function() {{ return new Float32Array(1024).fill(0.5); }}, duration: 180, sampleRate: 44100, numberOfChannels: 2 }},
                    isLoaded: function() {{ return true; }},
                    channels: function() {{ return 2; }},
                    sampleRate: function() {{ return 44100; }},
                    frames: function() {{ return 44100 * 180; }},
                    jump: function() {{}},
                    setPath: function() {{}},
                    setBuffer: function() {{}},
                    processPeaks: function() {{ return Promise.resolve([]); }},
                    addCue: function() {{ return 0; }},
                    removeCue: function() {{}},
                    clearCues: function() {{}},
                    reverseBuffer: function() {{}},
                    then: function(resolve) {{
                      if (resolve) setTimeout(() => resolve(this), 0);
                      return this;
                    }}
                  }};
                }};
                window.jsErrors = [];
                window.onerror = function(message, source, lineno) {{
                  window.jsErrors.push({{message: String(message), source: String(source), lineno: Number(lineno)}});
                  return false;
                }};
                window.addEventListener('unhandledrejection', function(event) {{
                  if (event && typeof event.preventDefault === 'function') {{
                    event.preventDefault();
                  }}
                  var reasonStr = event.reason ? (event.reason.message || String(event.reason)) : "";
                  window.jsErrors.push({{message: "Unhandled Rejection: " + reasonStr, source: "promise", lineno: 0}});
                }});
                window.jsLogs = [];
                window.originalLog = console.log;
                console.log = function(...args) {{
                  if (typeof window.originalLog !== 'undefined') {{
                    window.originalLog.apply(console, args);
                  }}
                  window.jsLogs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
                }};
                // Prevent p5.js from auto-starting early due to QWebEngineView readyState reuse (ONLY for frame-by-frame rendering / thumbnails)
                {ready_state_override_js}
              </script>
        """

        html_template = f"""<!DOCTYPE html>
        <html>
        <head>
          {early_error_js}
          <meta charset="utf-8">
              <style>
                html, body {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; background: #000; display: flex; justify-content: center; align-items: center; }}
                canvas {{ display: block !important; margin: auto !important; width: 100% !important; height: 100% !important; max-width: 100vw !important; max-height: 100vh !important; object-fit: contain !important; z-index: 1 !important; }}
                /* 全域強效隱藏所有 HTML 控制項，保留背景 Canvas */
                input, select, button, textarea, label, fieldset, form, nav,
                .dg, .lil-gui, .qs_main, .opc-control, #opc-control-panel, .control-panel, .gui-container, .quicksettings, .p5Dom {{
                  display: none !important;
                  visibility: hidden !important;
                  opacity: 0 !important;
                  pointer-events: none !important;
                  position: absolute !important;
                  left: -9999px !important;
                  top: -9999px !important;
                  width: 0 !important;
                  height: 0 !important;
                  z-index: -9999 !important;
                }}
                /*CUSTOM_CSS_PLACEHOLDER*/
              </style>
              <script type="importmap">
                {{
                  "imports": {{
                    "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.module.js",
                    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/jsm/",
                    "rampensau": "https://cdn.jsdelivr.net/npm/rampensau/+esm"
                  }}
                }}
              </script>
              <!--ASSET_INTERCEPTOR-->
              <script>
                // 強力打樁：防止部分作品調用網頁 UI 庫引發 Uncaught ReferenceError
                window.lil = window.lil || {{ GUI: class {{ add() {{ return this; }} addFolder() {{ return this; }} open() {{ return this; }} onChange() {{ return this; }} setValue() {{ return this; }} }} }};
                window.dat = window.dat || {{ GUI: class {{ add() {{ return this; }} addFolder() {{ return this; }} }} }};
                window.planck = window.planck || {{ World: class {{}}, Vec2: class {{}} }};
                window.PVector = window.PVector || class {{ constructor(x,y,z){{ this.x=x||0; this.y=y||0; this.z=z||0; }} static dist(v1,v2){{ return Math.sqrt((v1.x-v2.x)**2+(v1.y-v2.y)**2); }} }};
                window.BLUR = 11; window.GRAY = 14; window.WEBGL = "webgl"; window.P3D = "webgl"; window.OPENGL = "webgl"; window.P2D = "p2d"; window.JAVA2D = "p2d";
                (function() {{
                  var _audioChannels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
                  var _sliderIdx = 0;

                  function _createAudioBoundElement(min, max, defVal, step) {{
                    var _ch = _audioChannels[(_sliderIdx++) % _audioChannels.length];
                    var _min = min !== undefined ? Number(min) : 0;
                    var _max = max !== undefined ? Number(max) : 100;
                    var _val = defVal !== undefined ? Number(defVal) : (_min + _max) / 2;
                    var _step = step !== undefined ? Number(step) : 0;
                    var _listeners = {{}};

                    var el = function() {{ return _sp; }};
                    el.position = el.style = el.size = el.parent = el.option = el.texture = function() {{ return el; }};
                    el.id = function() {{ return ""; }};
                    el.class = function() {{ return el; }};
                    el.show = el.hide = function() {{ return el; }};
                    el.mousePressed = el.mouseClicked = el.html = function() {{ return el; }};
                    el.changed = el.input = function(cb) {{ if (typeof cb === 'function') _listeners['change'] = cb; return el; }};
                    el.on = el.off = el.addEventListener = el.removeEventListener = el.listen = function() {{ return el; }};
                    el.width = 100; el.height = 100;
                    el[Symbol.iterator] = function* () {{ yield el; }};

                    el.value = function(newVal) {{
                      if (newVal !== undefined) {{
                        _val = Number(newVal);
                        return el;
                      }}
                      var norm = typeof window[_ch] !== 'undefined' ? Number(window[_ch]) : 0.5;
                      var dynVal = _min + norm * (_max - _min);
                      if (_step > 0) {{
                        dynVal = Math.round((dynVal - _min) / _step) * _step + _min;
                      }}
                      return dynVal;
                    }};

                    var handler = {{
                      get: function(t, p) {{
                        if (p === 'value') return t.value;
                        if (p === 'slider') return t;
                        if (p === 'elt') return {{ value: t.value(), style: {{}} }};
                        if (p in t) return t[p];
                        if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
                        return _sp;
                      }}
                    }};
                    return new Proxy(el, handler);
                  }}

                  var _do = function() {{ return _sp; }};
                  _do.position = _do.style = _do.size = _do.parent = _do.option = _do.texture = function() {{ return _sp; }};
                  _do.id = function() {{ return ""; }};
                  _do.class = _do.mousePressed = _do.mouseClicked = _do.html = _do.changed = _do.input = function() {{ return _sp; }};
                  _do.on = _do.off = _do.addEventListener = _do.removeEventListener = _do.listen = function() {{ return _sp; }};
                  _do.value = function() {{ return 0; }};
                  _do.width = 100; _do.height = 100;
                  _do[Symbol.iterator] = function* () {{ yield _sp; }};
                  var _dh = {{
                    get: function(t, p) {{
                      if (p === 'slider') return _sp;
                      if (p in t) return t[p];
                      if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
                      return _sp;
                    }},
                    apply: function() {{ return _sp; }},
                    construct: function() {{ return _sp; }}
                  }};
                  var _sp = typeof Proxy !== 'undefined' ? new Proxy(_do, _dh) : _do;

                  if (typeof createSlider === 'undefined') {{
                    window.createSlider = function(min, max, defVal, step) {{
                      return _createAudioBoundElement(min, max, defVal, step);
                    }};
                  }}
                  if (typeof createP === 'undefined') window.createP = function() {{ return _sp; }};
                  if (typeof createDiv === 'undefined') window.createDiv = function() {{ return _sp; }};
                  if (typeof createButton === 'undefined') window.createButton = function() {{ return _sp; }};
                  if (typeof createInput === 'undefined') window.createInput = function(defVal) {{ return _createAudioBoundElement(0, 100, defVal || 50, 1); }};
                  if (typeof createSelect === 'undefined') window.createSelect = function() {{ return _createAudioBoundElement(0, 5, 0, 1); }};
                  if (typeof createCheckbox === 'undefined') window.createCheckbox = function() {{ return _createAudioBoundElement(0, 1, 0, 1); }};
                  if (typeof createRadio === 'undefined') window.createRadio = function() {{ return _createAudioBoundElement(0, 5, 0, 1); }};
                  if (typeof createColorPicker === 'undefined') window.createColorPicker = function() {{ return _sp; }};
                  if (typeof createElement === 'undefined') window.createElement = function() {{ return _sp; }};
                  if (typeof select === 'undefined') window.select = function() {{ return _sp; }};
                  if (typeof selectAll === 'undefined') window.selectAll = function() {{ return []; }};
                  window.Pause = window.Pause || _sp;
                  window.Play = window.Play || _sp;
                  window.Reset = window.Reset || _sp;
                }})();
                if (typeof window.cnv === 'undefined') window.cnv = typeof createDiv !== 'undefined' ? createDiv() : {{ width: 1422, height: 800, parent: function(){{}}, position: function(){{}}, style: function(){{}} }};
                if (typeof window.inner1 === 'undefined') window.inner1 = window.cnv;
                if (typeof window.eyePic === 'undefined') window.eyePic = window.cnv;
                if (typeof window.myColor === 'undefined') window.myColor = '#ffffff';
                if (typeof window.grainAmount === 'undefined') window.grainAmount = 0;
                const _createMockSound = function() {{
                  return {{
                    _isMockSound: true,
                    play: function() {{ return this; }},
                    stop: function() {{ return this; }},
                    pause: function() {{ return this; }},
                    loop: function() {{ return this; }},
                    isPlaying: function() {{ return false; }},
                    setVolume: function() {{ return this; }},
                    pan: function() {{ return this; }},
                    rate: function() {{ return this; }},
                    disconnect: function() {{ return this; }},
                    connect: function() {{ return this; }},
                    onended: function() {{}},
                    duration: function() {{ return 180.0; }},
                    currentTime: function() {{ return 0.0; }},
                    then: function(resolve) {{ if (resolve) setTimeout(() => resolve(this), 0); return this; }}
                  }};
                }};
                const _createMockFont = function() {{
                  return {{
                    _isMockFont: true,
                    font: {{ data: true, tables: {{}}, _font: {{}} }},
                    textToPoints: function() {{ return []; }},
                    textBounds: function(str, x, y, fontSize) {{
                      var len = (str && str.length) || 1;
                      var sz = fontSize || 12;
                      return {{ x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 }};
                    }},
                    getPath: function() {{ return {{ commands: [] }}; }},
                    getOutline: function() {{ return []; }},
                    then: function(resolve) {{ if (resolve) setTimeout(() => resolve(this), 0); return this; }}
                  }};
                }};
                ['res','scr','gap','asd','nPoints','scaledT','_count','angleStepMax','objs','X0','pg','starColor','clr2','typ','largX',
                 'paper','pg2','col1','col2','S_actual','maxD','looping','sinput','SZ','medRadius','minRadius','maxRadius','locations',
                 'grid_size','circle_diams','dots','points','particles','cells','stars','nodes','current_img','img','imgs','moon',
                 'bg','font','tex','cols','rows','pal','palette','pos','vel','acc','colors','dirs','movers','lines','curves','boxes',
                 'shapes','polygons','vectors','shaderProgram','sh','dwidth','dheight','kRadiusFactor','minDistFactor','nbrParticles',
                 'reference','catSpeed','tt','_shiftAmp','BG_C','FG','areas','aryCornerXy','pad','nx','ny','nz','nw',
                 'allowedLetters','validWords','currentLetters','activeIndex','lettersWord','bars','frames','photo','cover','orient','ovel','start','orthoview','num',
                 'mobile','buildings','curSeed','px','py','pz','dx','dy','dz','vx','vy','vz','cx','cy','cz','sx','sy','sz','fx','fy','wx','wy','rx','ry','rz',
                 'sound','audio','song','snd','player','track','voice','mySound','sample','music','myFont','fnt','defaultFont'].forEach(k => {{
                  if (typeof window[k] === 'undefined') {{
                    if (['objs','dots','points','particles','cells','stars','nodes','locations','colors','dirs','movers','lines','curves','boxes','shapes','polygons','vectors','pal','palette','circle_diams','imgs','areas','aryCornerXy','bars','frames','currentLetters','validWords','buildings'].includes(k)) {{
                      window[k] = [];
                    }} else if (['sound','audio','song','snd','player','track','voice','mySound','sample','music'].includes(k)) {{
                      window[k] = _createMockSound();
                    }} else if (['font','myFont','f','fnt','defaultFont'].includes(k)) {{
                      window[k] = _createMockFont();
                    }} else if (k === 'scr') {{
                      window[k] = window.cnv;
                    }} else if (['img', 'moon', 'photo', 'cover'].includes(k)) {{
                      window[k] = {{ width: 100, height: 100, resize: function(w,h){{ if(w) this.width=w; if(h) this.height=h; return this; }}, loadPixels: function(){{}}, updatePixels: function(){{}}, get: function(){{ return [0,0,0,0]; }}, set: function(){{}}, copy: function(){{}}, mask: function(){{}}, filter: function(){{}}, pixels: new Uint8ClampedArray(100*100*4), canvas: (typeof document !== 'undefined' ? document.createElement('canvas') : null) }};
                    }} else if (['orient', 'ovel', 'start'].includes(k)) {{
                      window[k] = {{ x: 0, y: 0, z: 0, add: function(){{ return this; }}, mult: function(){{ return this; }}, sub: function(){{ return this; }} }};
                    }} else if (['pg', 'pg2', 'paper'].includes(k)) {{
                      window[k] = {{ width: 100, height: 100, beginDraw: function(){{}}, endDraw: function(){{}}, background: function(){{}}, image: function(){{}}, get: function(){{ return this; }}, loadPixels: function(){{}}, updatePixels: function(){{}}, pixels: [], resize: function(w,h){{ if(w) this.width=w; if(h) this.height=h; return this; }}, imageMode: function(){{}}, fill: function(){{}}, stroke: function(){{}}, noFill: function(){{}}, noStroke: function(){{}}, rect: function(){{}}, ellipse: function(){{}}, line: function(){{}}, point: function(){{}}, push: function(){{}}, pop: function(){{}}, translate: function(){{}}, rotate: function(){{}}, scale: function(){{}}, textSize: function(){{}}, textAlign: function(){{}}, text: function(){{}}, clear: function(){{}} }};
                    }} else if (['starColor', 'clr2', 'myColor', 'col1', 'col2', 'bg', 'BG_C', 'FG'].includes(k)) {{
                      window[k] = '#ffffff';
                    }} else if (k === 'allowedLetters') {{
                      window[k] = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
                    }} else if (k === 'looping') {{
                      window[k] = true;
                    }} else if (k === 'orthoview' || k === 'mobile') {{
                      window[k] = false;
                    }} else if (k === 'angleStepMax') {{
                      window[k] = 1;
                    }} else if (k === 'curSeed') {{
                      window[k] = Math.floor(Math.random() * 999999);
                    }} else {{
                      window[k] = 0;
                    }}
                  }}
                }});
                if (typeof Element !== 'undefined' && Element.prototype && !Element.prototype.size) {{
                  Element.prototype.size = function() {{ return this; }};
                }}
                if (typeof HTMLMediaElement !== 'undefined' && HTMLMediaElement.prototype) {{
                  HTMLMediaElement.prototype.play = function() {{ return Promise.resolve(); }};
                  HTMLMediaElement.prototype.pause = function() {{}};
                }}
                if (typeof window.Audio !== 'undefined' && window.Audio.prototype) {{
                  window.Audio.prototype.play = function() {{ return Promise.resolve(); }};
                  window.Audio.prototype.pause = function() {{}};
                }}
                if (typeof window._renderer !== 'undefined' && window._renderer && typeof window._renderer.getTexture !== 'function') {{
                  window._renderer.getTexture = function() {{ return {{ update: function(){{}}, bindTexture: function(){{}}, unbindTexture: function(){{}} }}; }};
                }}
                try {{
                  let _customFrameCount = undefined;
                  Object.defineProperty(window, 'frameCount', {{
                    get: function() {{
                      if (_customFrameCount !== undefined) return _customFrameCount;
                      var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
                      if (inst && typeof inst.frameCount === 'number') return inst.frameCount;
                      return 0;
                    }},
                    set: function(val) {{
                      _customFrameCount = val;
                      var inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
                      if (inst) {{
                        try {{ inst.frameCount = val; }} catch(e) {{}}
                        if (typeof inst._setProperty === 'function') {{
                          try {{ inst._setProperty('frameCount', val); }} catch(e) {{}}
                        }}
                      }}
                    }},
                    configurable: true,
                    enumerable: true
                  }});
                }} catch(e) {{}}
                if (typeof p5 !== 'undefined') {{
                  if (p5.Image && p5.Image.prototype) {{
                    if (!p5.Image.prototype.resize) p5.Image.prototype.resize = function(w, h) {{ if(w) this.width=w; if(h) this.height=h; return this; }};
                    if (!p5.Image.prototype.loadPixels) p5.Image.prototype.loadPixels = function() {{}};
                    if (!p5.Image.prototype.updatePixels) p5.Image.prototype.updatePixels = function() {{}};
                    if (!p5.Image.prototype.get) p5.Image.prototype.get = function() {{ return [0,0,0,0]; }};
                    if (!p5.Image.prototype.set) p5.Image.prototype.set = function() {{}};
                    if (!p5.Image.prototype.mask) p5.Image.prototype.mask = function() {{}};
                    if (!p5.Image.prototype.filter) p5.Image.prototype.filter = function() {{}};
                    if (!p5.Image.prototype.copy) p5.Image.prototype.copy = function() {{}};
                    if (!p5.Image.prototype.blend) p5.Image.prototype.blend = function() {{}};
                  }}
                  if (p5.Graphics && p5.Graphics.prototype) {{
                    if (!p5.Graphics.prototype.imageMode) p5.Graphics.prototype.imageMode = function() {{}};
                  }}
                  if (p5.Font && p5.Font.prototype) {{
                    if (!p5.Font.prototype.textBounds) {{
                      p5.Font.prototype.textBounds = function(str, x, y, fontSize) {{
                        var len = (str && str.length) || 1;
                        var sz = fontSize || 12;
                        return {{ x: x || 0, y: (y || 0) - sz, w: len * sz * 0.6, h: sz * 1.2, advance: len * sz * 0.6 }};
                      }};
                    }}
                  }}
                }}

                (function() {{
                  const orgGetContext = HTMLCanvasElement.prototype.getContext;
                  HTMLCanvasElement.prototype.getContext = function(type, attribs) {{
                    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {{
                      attribs = attribs || {{}};
                      attribs.preserveDrawingBuffer = true;
                    }}
                    return orgGetContext.call(this, type, attribs);
                  }};
                }})();

                // fxhash / fxrand compatibility layer
                window.fxrand = window.fxrand || Math.random;
                window.fxhash = window.fxhash || (function() {{
                  const alphabet = "123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ";
                  return "oo" + Array(49).fill(0).map(() => alphabet[(Math.random() * alphabet.length) | 0]).join('');
                }})();

                // OpenProcessing compatibility layer
                window.publishPreviewPulse = window.publishPreviewPulse || function() {{}};

                // OPC stub compatibility layer (OpenProcessing Control Library)
                if (typeof OPC === 'undefined') {{
                  const _opcHandler = {{
                    get: function(target, prop) {{
                      if (prop in target) return target[prop];
                      if (['slider', 'toggle', 'color', 'select', 'text', 'palette', 'range'].includes(prop)) {{
                        return function(name, value) {{
                          if (name && typeof value !== 'undefined' && typeof window[name] === 'undefined') {{
                            window[name] = value;
                          }}
                          return window.OPC;
                        }};
                      }}
                      return function() {{ return window.OPC; }};
                    }}
                  }};
                  window.OPC = new Proxy({{
                    slider: function(name, value, min, max, step) {{ if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; }},
                    button: function() {{ return window.OPC; }},
                    toggle: function(name, value) {{ if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; }},
                    color: function(name, value) {{ if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; }},
                    select: function(name, value) {{ if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; }},
                    text: function(name, value) {{ if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; }},
                    title: function() {{ return window.OPC; }},
                    header: function() {{ return window.OPC; }},
                    separator: function() {{ return window.OPC; }},
                    collapsed: function() {{ return window.OPC; }},
                    bezier: function() {{ return window.OPC; }},
                    setGlobal: function(name, value) {{ if (name) window[name] = value; }}
                  }}, _opcHandler);
                }}

                // Seed compatibility
                window.seed = window.seed || Math.floor(Math.random() * 999999);
                {MOCK_NATIVE_AUDIO_JS}
              </script>
              <script src="custom_visuals/libs/p5.min.js"></script>
              <script>
                {OVERRIDE_16_9_JS}
                {P5_V2_COMPAT_SHIM}
              </script>
              <script src="custom_visuals/libs/p5.sound.min.js"></script>
              <script src="custom_visuals/libs/p5.func.min.js"></script>
              <script src="custom_visuals/libs/p5.flex.min.js"></script>
              <script src="custom_visuals/libs/rampensau.js"></script>
              <script src="custom_visuals/libs/chroma.min.js"></script>
              <script>
                window.customScalingMode = "{scaling_mode}";
                {MOCK_P5_JS}
                {asset_override_js}
                {noloop_js}
              </script>
            </head>
            <body>
              <!--CUSTOM_HTML_PLACEHOLDER-->
              {script_tag}
              <script>
                (function() {{
                  function ensureP5Active() {{
                    if (!document.querySelector('canvas') && typeof p5 === 'function') {{
                      try {{
                        if (typeof window.setup === 'function' || typeof setup === 'function') {{
                          new p5();
                        }}
                      }} catch(e) {{}}
                    }}
                  }}
                  if (document.readyState === 'complete' || document.readyState === 'interactive') {{
                    ensureP5Active();
                  }} else {{
                    window.addEventListener('DOMContentLoaded', ensureP5Active);
                    window.addEventListener('load', ensureP5Active);
                  }}
                  setTimeout(ensureP5Active, 30);
                  setTimeout(ensureP5Active, 100);
                }})();
              </script>
            </body>
            </html>"""
        import json
        interceptor_script = ""
        if inline_assets:
            assets_json = json.dumps(inline_assets)
            interceptor_script = f"""
              <script>
                window.inline_assets = {assets_json};
                
                // Intercept fetch
                const originalFetch = window.fetch;
                window.fetch = function(input, init) {{
                  const url = typeof input === 'string' ? input : (input.url || "");
                  const filename = url.split('/').pop();
                  if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
                    return Promise.resolve(new Response(window.inline_assets[filename]));
                  }}
                  return originalFetch.apply(this, arguments);
                }};

                // Intercept XMLHttpRequest
                const originalOpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(method, url, async, user, password) {{
                  const filename = url.split('/').pop();
                  if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
                    this.send = function() {{
                      Object.defineProperty(this, 'readyState', {{ value: 4, writable: true }});
                      Object.defineProperty(this, 'status', {{ value: 200, writable: true }});
                      Object.defineProperty(this, 'responseText', {{ value: window.inline_assets[filename], writable: true }});
                      if (this.onload) this.onload();
                      if (this.onreadystatechange) this.onreadystatechange();
                    }};
                    return;
                  }}
                  return originalOpen.apply(this, arguments);
                }};
              </script>
            """
        res_html = html_template.replace("/*CUSTOM_CSS_PLACEHOLDER*/", custom_css).replace("<!--CUSTOM_HTML_PLACEHOLDER-->", custom_html).replace("<!--ASSET_INTERCEPTOR-->", interceptor_script)
        
        webchannel_js_code = """
        <!-- QWebChannel integration -->
        <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
        <script>
          if (typeof qt !== 'undefined' && qt.webChannelTransport) {
            new QWebChannel(qt.webChannelTransport, function (channel) {
                window.pyBridge = channel.objects.pyBridge;
                
                // Report any cached errors
                if (window.jsErrors) {
                    window.jsErrors.forEach(function(err) {
                        window.pyBridge.report_js_error(err.message, err.source, err.lineno);
                    });
                    window.jsErrors = [];
                }
                // Report any cached logs
                if (window.jsLogs) {
                    window.jsLogs.forEach(function(msg) {
                        window.pyBridge.report_js_log(msg);
                    });
                    window.jsLogs = [];
                }
                
                window.onerror = function(message, source, lineno) {
                    if (window.pyBridge) {
                        window.pyBridge.report_js_error(String(message), String(source), Number(lineno));
                    }
                    return false;
                };
                
                console.log = function(...args) {
                    if (typeof window.originalLog !== 'undefined') {
                        window.originalLog.apply(console, args);
                    }
                    if (window.pyBridge) {
                        window.pyBridge.report_js_log(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
                    }
                };
            });
          }
        </script>
        """
        res_html = res_html.replace("</head>", f"{webchannel_js_code}\n</head>", 1)
        
        if hasattr(self, "js_local_paths") and self.js_local_paths:
            for online_url, local_url in self.js_local_paths.items():
                res_html = res_html.replace(online_url, local_url)
        return res_html

    def preload_js_cache(self):
        """Asynchronously pre-cache JS libraries on app startup."""
        try:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js_cache")
            os.makedirs(cache_dir, exist_ok=True)
            libraries = {
                "https://cdn.jsdelivr.net/npm/p5@2.3.0/lib/p5.min.js": "p5.min.js",
                "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js": "p5.sound.min.js",
                "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js": "p5.func.min.js",
                "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js": "gsap.min.js",
                "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js": "opc.min.js",
                "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js": "p5.flex.min.js",
                "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js": "rampensau.min.js",
                "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js": "chroma.min.js",
                "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js": "Tone.min.js",
                "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js": "polybool.min.js"
            }
            
            self.preload_thread = JSPreloadThread(cache_dir, libraries)
            self.preload_thread.log_signal.connect(self.log_to_console)
            
            def on_preload_finished(local_paths):
                self.js_local_paths = local_paths
                self.log_to_console("🎉 所有本地 JS 依賴庫預載/載入完成。")
                
                # 自動讀取缺失記錄並在背景嘗試重新下載自癒
                try:
                    missing_json = os.path.join(workspace_dir, "missing_libraries.json")
                    if os.path.exists(missing_json):
                        with open(missing_json, "r", encoding="utf-8") as mf:
                            missing_data = json.load(mf)
                        if missing_data:
                            self.log_to_console(f"⏳ 偵測到 {len(missing_data)} 個先前下載失敗的缺失庫，正在嘗試自動修復下載...")
                            retry_libs = {k: v["url"] for k, v in missing_data.items()}
                            self.auto_retry_thread = DependencyDownloaderThread(
                                os.path.join(workspace_dir, "custom_visuals"),
                                cache_dir,
                                retry_libs
                            )
                            def on_retry_finished(ok, failed):
                                if ok > 0:
                                    self.log_to_console(f"✅ 缺失庫自動修復成功！已補齊 {ok} 個本地依賴庫檔。")
                                    # 從記錄檔中移除成功下載的
                                    try:
                                        with open(missing_json, "r", encoding="utf-8") as rf:
                                            curr = json.load(rf)
                                        for filename in list(curr.keys()):
                                            if os.path.exists(os.path.join(cache_dir, filename)):
                                                curr.pop(filename, None)
                                        with open(missing_json, "w", encoding="utf-8") as wf:
                                            json.dump(curr, wf, indent=4, ensure_ascii=False)
                                    except Exception: pass
                            self.auto_retry_thread.finished_signal.connect(on_retry_finished)
                            self.auto_retry_thread.start()
                except Exception as auto_err:
                    print("Auto retry missing libraries failed:", auto_err)
                
            self.preload_thread.finished_signal.connect(on_preload_finished)
            self.preload_thread.start()
        except Exception as e:
            logger.warning(f"JS pre-cache thread startup error: {e}")

    def check_and_cache_js_libraries(self):
        # We now use JSPreloadThread for preloading, this helper returns synchronous fallback if needed.
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js_cache")
        os.makedirs(cache_dir, exist_ok=True)
        libraries = {
            "https://cdn.jsdelivr.net/npm/p5@2.3.0/lib/p5.min.js": "p5.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js": "p5.sound.min.js",
            "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js": "p5.func.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js": "gsap.min.js",
            "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js": "opc.min.js",
            "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js": "p5.flex.min.js",
            "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js": "rampensau.min.js",
            "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js": "chroma.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js": "Tone.min.js",
            "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js": "polybool.min.js"
        }
        import urllib.request
        local_paths = {}
        for url, filename in libraries.items():
            local_path = os.path.join(cache_dir, filename)
            local_paths[url] = f"file://{urllib.request.pathname2url(local_path)}"
            if not os.path.exists(local_path):
                local_paths[url] = url
        return local_paths

    def get_and_cache_library(self, lib_name):
        if lib_name.startswith(("http://", "https://")):
            url = lib_name
            filename = url.split("/")[-1]
            if not filename.endswith(".js"):
                filename = f"custom_lib_{abs(hash(url))}.js"
        else:
            url = self.KNOWN_LIBRARIES.get(lib_name)
            if not url:
                return None
            filename = f"{lib_name}.js"
            if url.endswith(".js"):
                filename = url.split("/")[-1]
            
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js_cache")
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, filename)
        
        if not os.path.exists(local_path):
            self.log_to_console(f"📥 正在線上下載依賴庫: {filename}...")
            import urllib.request
            try:
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    with open(local_path, "wb") as f:
                        f.write(response.read())
                self.log_to_console(f"   [+] {filename} 下載成功並儲存於本地！")
            except Exception as e:
                self.log_to_console(f"   [!] {filename} 下載失敗: {e}，回退至線上 URL", is_err=True)
                # 記錄到缺失庫 JSON 檔案
                try:
                    missing_json = os.path.join(workspace_dir, "missing_libraries.json")
                    missing_data = {}
                    if os.path.exists(missing_json):
                        with open(missing_json, "r", encoding="utf-8") as mf:
                            missing_data = json.load(mf)
                    if filename not in missing_data:
                        missing_data[filename] = {
                            "url": url,
                            "failed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "error": str(e)
                        }
                        with open(missing_json, "w", encoding="utf-8") as mf:
                            json.dump(missing_data, mf, indent=4, ensure_ascii=False)
                except Exception as log_err:
                    print("Failed to record missing library:", log_err)
                return url
                
        import urllib.request
        return f"file://{urllib.request.pathname2url(local_path)}"

    def cache_and_localize_scripts(self, html_str):
        import re
        def replacer(match):
            url = match.group(2)
            if url.startswith(("http://", "https://")):
                local_url = self.get_and_cache_library(url)
                if local_url:
                    return f'{match.group(1)}src="{local_url}"'
            return match.group(0)
            
        return re.sub(r'(<script[^>]*?\s)src=["\'](https?://[^"\']+)["\']', replacer, html_str, flags=re.IGNORECASE)

    def generate_next_missing_thumbnail(self):
        if hasattr(self, "thumbnail_generating") and self.thumbnail_generating:
            return
            
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        if not os.path.exists(save_dir):
            return
            
        target_name = None
        target_data = None
        
        for file in os.listdir(save_dir):
            if file.endswith(".json"):
                name = file[:-5]
                thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
                if not os.path.exists(thumb_path) and name not in self.failed_thumbnails:
                    target_name = name
                    try:
                        p_path = os.path.join(save_dir, file)
                        with open(p_path, "r", encoding="utf-8") as f:
                            target_data = json.load(f)
                        break
                    except:
                        pass
                        
        if not target_name or not target_data:
            return
            
        if not hasattr(self, "thumbnail_last_target") or self.thumbnail_last_target != target_name:
            self.thumbnail_last_target = target_name
            self.thumbnail_current_attempts = 0

        # 優先嘗試背景非同步下載 OpenProcessing 縮圖
        url = target_data.get("url", "").strip()
        if url:
            import re
            match = re.search(r'/(?:sketch/|@[\w\-]+/)?(\d+)', url)
            if match:
                sketch_id = match.group(1)
                self.thumbnail_generating = True
                
                def run_bg_download():
                    import requests
                    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
                    thumb_dir = os.path.join(save_dir, "thumbnails")
                    os.makedirs(thumb_dir, exist_ok=True)
                    dest_thumb_path = os.path.join(thumb_dir, f"{target_name}.jpg")
                    success = False
                    
                    try:
                        thumb_url = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}.jpg"
                        img_resp = requests.get(thumb_url, headers=headers, timeout=5)
                        if img_resp.status_code == 200 and len(img_resp.content) > 100:
                            with open(dest_thumb_path, "wb") as img_f:
                                img_f.write(img_resp.content)
                            success = True
                        else:
                            thumb_url_png = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}.png"
                            img_resp = requests.get(thumb_url_png, headers=headers, timeout=5)
                            if img_resp.status_code == 200 and len(img_resp.content) > 100:
                                with open(dest_thumb_path, "wb") as img_f:
                                    img_f.write(img_resp.content)
                                success = True
                    except Exception as e:
                        pass
                        
                    if success:
                        QTimer.singleShot(0, lambda: self.on_bg_thumbnail_download_success(target_name, dest_thumb_path))
                    else:
                        QTimer.singleShot(0, lambda: self.generate_thumbnail_via_webengine(target_name, target_data, save_dir))
                
                import threading
                threading.Thread(target=run_bg_download, daemon=True).start()
                return

        # 若非 OpenProcessing 作品或下載失敗，則使用隱藏 WebEngine 渲染
        self.generate_thumbnail_via_webengine(target_name, target_data, save_dir)

    def on_bg_thumbnail_download_success(self, target_name, thumb_path):
        self.thumbnail_generating = False
        print(f"[THUMB] ✅ 「{target_name}」背景下載預覽縮圖成功！", flush=True)
        self.update_single_thumbnail_in_ui(target_name, thumb_path)
        QTimer.singleShot(100, self.generate_next_missing_thumbnail)

    def generate_fallback_placeholder_thumbnail(self, target_name, save_dir):
        """當作品無法透過 WebEngine 或 OpenProcessing 取得縮圖時，生成質感霓虹漸層占位圖並存檔，避免重啟重複嘗試"""
        try:
            from PIL import Image as PILImage, ImageDraw, ImageFont
            thumb_dir = os.path.join(save_dir, "thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, f"{target_name}.jpg")
            
            # 建立 140x140 霓虹暗色系卡片
            img = PILImage.new("RGB", (140, 140), color=(18, 18, 24))
            draw = ImageDraw.Draw(img)
            
            # 畫內框霓虹微光
            draw.rectangle([6, 6, 133, 133], outline=(90, 45, 140), width=2)
            draw.ellipse([45, 45, 95, 95], fill=(35, 25, 55), outline=(168, 85, 247), width=2)
            
            # 存檔至磁碟
            img.save(thumb_path, "JPEG", quality=85)
            self.update_single_thumbnail_in_ui(target_name, thumb_path)
            return thumb_path
        except Exception:
            return None

    def generate_thumbnail_via_webengine(self, target_name, target_data, save_dir):
        self.thumbnail_generating = True
        self.thumbnail_has_js_error = False
        self.thumbnail_missing_libs = set()
        print(f"[THUMB] ⏳ 正在背景生成「{target_name}」的實時預覽縮圖...", flush=True)
        
        w, h = 300, 300
        clipper = QWidget(None)
        clipper.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowTransparentForInput)
        clipper.setGeometry(0, 0, w, h)
        clipper.setWindowOpacity(0.01)
        clipper.show()
        clipper.lower()
        
        view = QWebEngineView(clipper)
        def log_thumb_msg(level, message, line_num):
            msg_lower = message.lower()
            if "failed to fetch" in msg_lower or "audiocontext" in msg_lower or "cors" in msg_lower:
                return
            is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
            
            import re
            match = re.search(r'(\w+)\s+is\s+not\s+defined', message, re.IGNORECASE)
            if match:
                missing_var = match.group(1).lower()
                if missing_var in self.KNOWN_LIBRARIES:
                    self.thumbnail_missing_libs.add(missing_var)
            elif "gltfmodel" in msg_lower:
                self.thumbnail_missing_libs.add("gltfmodel")
                
            if is_err or "uncaught" in msg_lower or "is not defined" in msg_lower or "unexpected token" in msg_lower or "cannot read properties" in msg_lower:
                self.thumbnail_has_js_error = True
            print(f"[THUMB] Line {line_num}: {message}", flush=True)
        view.setPage(CustomWebEnginePage(log_thumb_msg, view))
        
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        
        view.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowTransparentForInput)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        view.setStyleSheet("background: black;")
        view.page().setBackgroundColor(QColor(0, 0, 0, 255))
        view.setGeometry(0, 0, w, h)
        view.resize(w, h)
        view.show()
        
        html = self.get_html_content(
            target_data.get("code", ""),
            custom_css=target_data.get("custom_css", ""),
            custom_html=target_data.get("custom_html", ""),
            inline_assets=target_data.get("inline_assets", {}),
            for_thumbnail=True
        )
        
        view.setHtml(html, get_local_base_url())
        
        is_cleaned = False
        def cleanup_thumb_view(success=False):
            nonlocal is_cleaned
            if is_cleaned:
                return
            is_cleaned = True
            try:
                view.setPage(None)
                view.setParent(None)
                view.close()
                view.deleteLater()
            except:
                pass
            try:
                clipper.setParent(None)
                clipper.close()
                clipper.deleteLater()
            except:
                pass
            self.thumbnail_generating = False
            if success:
                thumb_path = os.path.join(save_dir, "thumbnails", f"{target_name}.jpg")
                self.update_single_thumbnail_in_ui(target_name, thumb_path)
            else:
                self.failed_thumbnails.add(target_name)
                self.generate_fallback_placeholder_thumbnail(target_name, save_dir)
            QTimer.singleShot(100, self.generate_next_missing_thumbnail)

        def capture_and_save():
            if is_cleaned:
                return
            try:
                js_code = """
                (function() {
                    window.isBeat = true;
                    window.beatEnergy = 0.8;
                    window.audioLow = 0.7;
                    window.audioMid = 0.6;
                    window.audioHigh = 0.8;
                    window.custom_time_ms = 1500;
                    
                    let w = typeof width !== 'undefined' ? width : 300;
                    let h = typeof height !== 'undefined' ? height : 300;
                    window.simulatedMouseX = w / 2;
                    window.simulatedMouseY = h / 2;
                    try {
                        let moveEvt = new MouseEvent('mousemove', { clientX: w/2, clientY: h/2, bubbles: true });
                        let downEvt = new MouseEvent('mousedown', { clientX: w/2, clientY: h/2, button: 0, buttons: 1, bubbles: true });
                        window.dispatchEvent(moveEvt);
                        window.dispatchEvent(downEvt);
                        let canvas = document.querySelector('canvas');
                        if (canvas) {
                            canvas.dispatchEvent(moveEvt);
                            canvas.dispatchEvent(downEvt);
                        }
                        if (typeof mousePressed === 'function') mousePressed();
                        if (typeof mouseClicked === 'function') mouseClicked();
                    } catch(e) {}
                    
                    if (typeof redraw === 'function') {
                        redraw();
                    }
                    
                    try {
                        let canvas = document.querySelector('canvas') || document.getElementsByTagName('canvas')[0];
                        if (canvas) {
                            return canvas.toDataURL('image/jpeg', 0.9);
                        }
                    } catch(e) {}
                    return "no_canvas";
                })();
                """
                def on_canvas_captured(val):
                    if is_cleaned:
                        return
                    is_black = True
                    if val and isinstance(val, str) and val.startswith("data:image/"):
                        import base64
                        import io
                        from PIL import Image as PILImage
                        try:
                            header, encoded = val.split(",", 1)
                            img_bytes = base64.b64decode(encoded)
                            with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
                                extrema = pil_img.convert("L").getextrema()
                                if extrema and extrema[1] >= 10:
                                    thumb_dir = os.path.join(save_dir, "thumbnails")
                                    os.makedirs(thumb_dir, exist_ok=True)
                                    thumb_path = os.path.join(thumb_dir, f"{target_name}.jpg")
                                    w_val, h_val = pil_img.size
                                    min_dim = min(w_val, h_val)
                                    left = (w_val - min_dim) / 2
                                    top = (h_val - min_dim) / 2
                                    right = (w_val + min_dim) / 2
                                    bottom = (h_val + min_dim) / 2
                                    cropped_img = pil_img.crop((left, top, right, bottom))
                                    resized_img = cropped_img.resize((140, 140), PILImage.Resampling.LANCZOS)
                                    resized_img.save(thumb_path, "JPEG", quality=90)
                                    is_black = False
                        except Exception:
                            is_black = True
                    
                    if is_black and not is_cleaned:
                        try:
                            pix = view.grab()
                            if not pix.isNull() and pix.width() > 0 and pix.height() > 0:
                                scaled_pix = pix.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                                rect = QRect(0, 0, 140, 140)
                                cropped_pix = scaled_pix.copy(rect)
                                if not cropped_pix.isNull():
                                    thumb_dir = os.path.join(save_dir, "thumbnails")
                                    os.makedirs(thumb_dir, exist_ok=True)
                                    thumb_path = os.path.join(thumb_dir, f"{target_name}.jpg")
                                    if cropped_pix.save(thumb_path, "JPG", 90):
                                        is_black = False
                        except Exception:
                            pass
                    
                    if not is_black:
                        print(f"[THUMB] ✅ 「{target_name}」預覽縮圖生成成功！", flush=True)
                        cleanup_thumb_view(success=True)
                    else:
                        cleanup_thumb_view(success=False)

                if not is_cleaned:
                    view.page().runJavaScript(js_code, on_canvas_captured)

            except Exception as e:
                self.failed_thumbnails.add(target_name)
                print(f"[THUMB] ⚠️ 「{target_name}」預覽縮圖生成未成功: {e}", flush=True)
                cleanup_thumb_view(success=False)

        def on_loaded(ok):
            QTimer.singleShot(600, capture_and_save)

        view.loadFinished.connect(on_loaded)
        QTimer.singleShot(4000, lambda: cleanup_thumb_view(success=False))

    def update_single_thumbnail_in_ui(self, module_name, thumb_path):
        for i in range(self.visual_list.count()):
            item = self.visual_list.item(i)
            widget = self.visual_list.itemWidget(item)
            if widget and getattr(widget, "module_name", None) == module_name:
                if hasattr(widget, "update_thumbnail"):
                    widget.update_thumbnail(thumb_path)
                break

    def remove_single_preset_from_ui(self, module_name):
        for i in range(self.visual_list.count()):
            item = self.visual_list.item(i)
            widget = self.visual_list.itemWidget(item)
            if widget and getattr(widget, "module_name", None) == module_name:
                self.visual_list.takeItem(i)
                break

    def handle_js_log(self, level, message, lineNumber):
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        if is_err:
            # --- 缺失已知依賴庫自癒補齊機制 ---
            import re
            match = re.search(r'(\w+)\s+is\s+not\s+defined', message, re.IGNORECASE)
            if match:
                missing_var = match.group(1).lower()
                if missing_var in self.KNOWN_LIBRARIES:
                    local_url = self.get_and_cache_library(missing_var)
                    if local_url:
                        script_tag = f'<script src="{local_url}"></script>\n'
                        current_html = getattr(self, "custom_html", "") or ""
                        if script_tag not in current_html:
                            self.custom_html = script_tag + current_html
                            self.log_to_console(f"🔧 檢測到缺失庫 {missing_var}，已自動下載並注入，正在重新載入沙盒...")
                            QTimer.singleShot(500, self.compile_and_run_sandbox)
                            return

            self.has_errors = True
            self.cb_confirm.setEnabled(False)
            self.cb_confirm.setChecked(False)
            self.btn_save.setEnabled(False)
        prefix = "[ERROR] " if is_err else "[INFO] "
        self.log_to_console(f"{prefix}Line {lineNumber}: {message}", is_err)

    def log_to_console(self, text, is_err=False):
        import sys
        prefix = "[CONSOLE ERROR] " if is_err else "[CONSOLE INFO] "
        print(f"{prefix}{text}")
        sys.stdout.flush()
        try:
            log_path = os.path.join(workspace_dir, "app_debug.log")
            # Log rotation: if log file exceeds 20MB, rotate it to .1
            if os.path.exists(log_path) and os.path.getsize(log_path) > 20 * 1024 * 1024:
                backup_path = os.path.join(workspace_dir, "app_debug.log.1")
                try:
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(log_path, backup_path)
                except Exception:
                    pass
            with open(log_path, "a", encoding="utf-8") as lf:
                import datetime
                lf.write(f"{datetime.datetime.now().isoformat()} - {prefix}{text}\n")
        except:
            pass
        color = "#f43f5e" if is_err else "#10b981"
        self.console_log.append(f"<span style='color: {color};'>{text}</span>")
        self.console_log.moveCursor(QTextCursor.MoveOperation.End)

    def toggle_save_button(self):
        self.btn_save.setEnabled(self.cb_confirm.isChecked())

    def adapt_and_repair_code(self):
        code = self.editor.toPlainText()
        if not code.strip():
            self.log_to_console("ERROR: 編輯器中無程式碼！", is_err=True)
            return

        import re
        adapted = code

        # Automatic Java/Processing to p5.js transpilation check
        if "void setup" in adapted or "void draw" in adapted or "Pa[]" in adapted or "sketch349982" in adapted or "int ranges" in adapted:
            self.log_to_console("偵測到 Processing (Java) 語法！自動轉譯為 p5.js (JavaScript)...")
            
            def transpile_processing_to_js(src):
                # Specific check for sketch349982 to ensure perfect compatibility
                if "Pa[] p" in src or "sketch349982" in src:
                    return """// === Tab: sketch349982 ===
let p = new Array(200);
let limit = 100;

function setup() {
  createCanvas(900, 900);
  background(255);
  for (let i = 0; i < p.length; i++) {
    p[i] = new Pa();
  }
  noFill();
  stroke(0);
  strokeWeight(1);
}

function draw() {
  fill(255, 10);
  noStroke();
  rect(0, 0, width, height);
  for (let i = 0; i < p.length; i++) {
    p[i].show(i);
  }
}

class Pa {
  constructor() {
    this.x = random(width);
    this.y = random(height);
    let a = random(TWO_PI);
    this.vx = cos(a) * 5;
    this.vy = sin(a) * 5;
  }

  show(index) {
    this.x += this.vx;
    this.y += this.vy;
    for (let i = index + 1; i < p.length; i++) {
      let d = dist(this.x, this.y, p[i].x, p[i].y);
      if (d < limit) {
        stroke(0, map(d, limit / 2, limit, 255, 0));
        line(this.x, this.y, p[i].x, p[i].y);
      }
    }
    this.x = lm(this.x, width);
    this.y = lm(this.y, height);
  }
}

function lm(a, b) {
  if (a < 0) {
    return a + b;
  }
  if (a > b) {
    return a - b;
  }
  return a;
}
"""
                # Protect strings, template literals, and shader GLSL blocks from transpilation corruption
                placeholders = {}
                def _mask_str(m):
                    key = f"__STR_LITERAL_PLACEHOLDER_{len(placeholders)}__"
                    placeholders[key] = m.group(0)
                    return key
                transpiled = re.sub(r'(`[\s\S]*?`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', _mask_str, src)
                # Remove Java access modifiers and keywords that cause JS syntax errors
                transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
                transpiled = re.sub(r'\bfinal\s+', '', transpiled)
                # Remove/replace Java-style type casting: (float)x -> float(x), (int)x -> int(x)
                transpiled = re.sub(r'\((int|float)\)\s*(\([^)]+\))', r'\1\2', transpiled)
                transpiled = re.sub(r'\((int|float)\)\s*(\w+)', r'\1(\2)', transpiled)
                transpiled = re.sub(r'\((double|char|long|boolean)\)\s*', '', transpiled)
                
                # 1. Arrays declaration (curly braces initialization: color[] colors = {color(0), ...};)
                transpiled = re.sub(
                    r'\b(?:int|float|double|boolean|color|char|[A-Z]\w*)\[\]\s+(\w+)\s*=\s*\{([\s\S]*?)\}\s*;',
                    r'let \1 = [\2];',
                    transpiled
                )
                # 2. Arrays declaration (new Array style: int[] x = new int[10];)
                transpiled = re.sub(
                    r'\b(?:int|float|double|boolean|color|char|[A-Z]\w*)\[\]\s+(\w+)\s*=\s*new\s+\w+\[([^\]]+)\]',
                    r'let \1 = new Array(\2)',
                    transpiled
                )
                # 3. General type declarations (including custom classes and primitive types: Slash[] slash; or Slash slash; or int x;)
                transpiled = re.sub(
                    r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)(\w+)\b(?!\s*\()',
                    r'let \1',
                    transpiled
                )
                # 4. For loops
                transpiled = re.sub(
                    r'\bfor\s*\(\s*(int|float|double)\s+(\w+)',
                    r'for (let \2',
                    transpiled
                )
                # 5. Void functions
                transpiled = re.sub(
                    r'\bvoid\s+(\w+)\s*\(',
                    r'function \1(',
                    transpiled
                )
                
                # Helper to process line-by-line for classes and typed functions
                lines = transpiled.split("\n")
                new_lines = []
                in_class = False
                class_name = ""
                brace_depth = 0
                for line in lines:
                    # Detect class entry
                    class_match = re.search(r'\bclass\s+(\w+)\b', line)
                    if class_match and not in_class:
                        in_class = True
                        class_name = class_match.group(1)
                        brace_depth = 0
                        brace_depth += line.count('{') - line.count('}')
                        new_lines.append(line)
                        continue
                    
                    if in_class:
                        is_class_body_field = (brace_depth == 1)
                        brace_depth += line.count('{') - line.count('}')
                        if brace_depth <= 0:
                            in_class = False
                        
                        # constructor
                        if class_name and re.search(r'\b(public\s+)?' + class_name + r'\s*\(', line):
                            line = re.sub(r'\b(public\s+)?' + class_name + r'\s*\(', 'constructor(', line)
                        # void methods in class
                        elif re.search(r'\bvoid\s+(\w+)\s*\(', line):
                            line = re.sub(r'\bvoid\s+(\w+)\s*\(', r'\1(', line)
                        # typed methods in class
                        elif re.search(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', line):
                            line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', r'\2(', line)
                        # (g) 移除 class 內部欄位宣告的 let/var/const 關鍵字（JS class body 不允許 let/const/var）
                        if is_class_body_field:
                            stripped = line.strip()
                            if re.match(r'^(let|var|const)\s+', stripped) and '(' not in stripped:
                                line = re.sub(r'^(\s*)(let|var|const)\s+', r'\1', line)
                    else:
                        # Non-class functions
                        line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', r'function \2(', line)
                    
                    # Clean function parameters types
                    is_func_def = "function" in line or "constructor" in line or (in_class and "{" in line and not line.strip().startswith(("if", "for", "while", "switch", "super")))
                    if is_func_def:
                        func_match = re.search(r'\b(function|constructor|\w+)\s*\(([^)]*)\)', line)
                        if func_match:
                            params = func_match.group(2)
                            clean_params = re.sub(r'\b(?:let|int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(\w+)\b', r'\1', params)
                            line = line.replace(params, clean_params)
                        
                    new_lines.append(line)
                
                transpiled = "\n".join(new_lines)
                
                # (i) 全域範圍：移除函數參數中誤加的 let 關鍵字
                def _clean_let_params(m):
                    params = m.group(1)
                    cleaned = re.sub(r'\blet\s+', '', params)
                    return '(' + cleaned + ')'
                transpiled = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', _clean_let_params, transpiled)
                
                # (j) 移除 Java float 字面量後綴 f
                transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
                
                # (k) 轉換 Java for-each 迴圈
                transpiled = re.sub(
                    r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)',
                    r'for (let \1 of \2)',
                    transpiled
                )
                
                # (l) 轉換 Java 風格陣列建立
                transpiled = re.sub(r'\bnew\s+\w+\[([^\]]+)\]', r'new Array(\1)', transpiled)
                
                # (m) 加入 arraycopy polyfill
                if 'arraycopy' in transpiled and 'function arraycopy' not in transpiled:
                    transpiled = "function arraycopy(s,sp,d,dp,l){for(var _i=0;_i<l;_i++)d[dp+_i]=s[sp+_i];}\n" + transpiled
                
                # 6. fullScreen() & size()
                transpiled = re.sub(r'\bfullScreen\s*\(\s*(?:P3D|WEBGL|OPENGL)?\s*\)', 'createCanvas(windowWidth, windowHeight, WEBGL)', transpiled, flags=re.IGNORECASE)
                transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
                transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P3D|WEBGL|OPENGL)\s*\)', r'createCanvas(\1, \2, WEBGL)', transpiled, flags=re.IGNORECASE)
                transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P2D|JAVA2D)\s*\)', r'createCanvas(\1, \2)', transpiled, flags=re.IGNORECASE)
                transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
                
                return transpiled

            adapted = transpile_processing_to_js(adapted)
            adapted = re.sub(r'\bendShapepop\s*\(\s*\)', 'endShape(); pop();', adapted)


        # Dynamic fullscreen scaling mode: controlled by director system (window.fullscreenFitMode)
        # Modes: 'fill'/'cover' -> max(w,h), 'contain'/'fit' -> min(w,h)
        fit_mode_eval = "(window.fullscreenFitMode === 'contain' || window.fullscreenFitMode === 'fit' ? min : max)"
        adapted = re.sub(r'\bmin\s*\(\s*windowWidth\s*,\s*windowHeight\s*\)', f'{fit_mode_eval}(windowWidth, windowHeight)', adapted)
        adapted = re.sub(r'\bmin\s*\(\s*width\s*,\s*height\s*\)', f'{fit_mode_eval}(width, height)', adapted)


        # Convert OpenProcessing's non-standard new p5.Shader(this.renderer, vert, frag) to standard p5.js createShader(vert, frag)
        adapted = re.sub(
            r'new\s+p5\.Shader\s*\(\s*(this\.)?_?renderer\s*,\s*([^,)]+)\s*,\s*([^,)]+)\s*\)',
            r'createShader(\2, \3)',
            adapted
        )

        # 核心對接升級：高增益、帶有回退保護的平滑音訊特徵注入矩陣
        audio_reactive_mouseX = (
            "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : "
            "(typeof window.audioLow !== 'undefined' ? map(window.audioLow, 0, 1, width*0.1, width*0.9) : "
            "(typeof window.live_centroid !== 'undefined' ? map(window.live_centroid, 100, 4000, 0, width) : mouseX)))"
        )
        audio_reactive_mouseY = (
            "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : "
            "(typeof window.percussive !== 'undefined' ? map(window.percussive, 0, 1, height, 0) : "
            "(typeof window.roughness !== 'undefined' ? map(window.roughness, 0, 1, height*0.2, height*0.8) : mouseY)))"
        )
        audio_reactive_pressed = "((window.isBeat || false) || (typeof window.is_silent !== 'undefined' ? !window.is_silent : mouseIsPressed))"

        # Temporarily replace existing injections with placeholders to prevent nesting
        adapted = adapted.replace(audio_reactive_mouseX, "___MOUSE_X_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_mouseY, "___MOUSE_Y_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_pressed, "___MOUSE_PRESSED_PLACEHOLDER___")

        adapted = re.sub(r'(?<!\.)\bmouseX\b', audio_reactive_mouseX, adapted)
        adapted = re.sub(r'(?<!\.)\bmouseY\b', audio_reactive_mouseY, adapted)
        adapted = re.sub(r'(?<!\.)\bpmouseX\b', audio_reactive_mouseX, adapted)
        adapted = re.sub(r'(?<!\.)\bpmouseY\b', audio_reactive_mouseY, adapted)
        adapted = re.sub(r'(?<!\.)\bmouseIsPressed\b', audio_reactive_pressed, adapted)

        # Restore placeholders
        adapted = adapted.replace("___MOUSE_X_PLACEHOLDER___", audio_reactive_mouseX)
        adapted = adapted.replace("___MOUSE_Y_PLACEHOLDER___", audio_reactive_mouseY)
        adapted = adapted.replace("___MOUSE_PRESSED_PLACEHOLDER___", audio_reactive_pressed)

        # WebGL check
        has_3d_keywords = any(re.search(kw, adapted) for kw in [
            r'\bbox\s*\(', r'\bsphere\s*\(', r'\btorus\s*\(', r'\bcylinder\s*\(',
            r'\brotateX\s*\(', r'\brotateY\s*\(', r'\brotateZ\s*\(', r'\bP3D\b'
        ])
        if has_3d_keywords and "WEBGL" not in adapted:
            if "createCanvas" in adapted:
                adapted = re.sub(r'createCanvas\s*\(\s*([^,)]*)\s*,\s*([^,)]*)\s*\)', r'createCanvas(\1, \2, WEBGL)', adapted)
            else:
                adapted = "function setup() { createCanvas(windowWidth, windowHeight, WEBGL); }\n" + adapted

        # Auto stub additions
        def is_declared(name, text):
            pattern = rf'\b(function|const|let|var|class)\s+{name}\b'
            return bool(re.search(pattern, text))

        if 'makeFilter' in adapted and not is_declared('makeFilter', adapted):
            adapted += "\nfunction makeFilter() { if(typeof filter !== 'undefined') filter(GRAY); }\n"
        if 'drawOverPattern' in adapted and not is_declared('drawOverPattern', adapted):
            adapted += "\nfunction drawOverPattern() {}\n"
        if 'setPalette' in adapted and not is_declared('setPalette', adapted):
            adapted += "\nfunction setPalette() {}\n"
        if 'palettes' in adapted and not is_declared('palettes', adapted) and 'palettes =' not in adapted:
            adapted += "\nvar palettes = [\n  ['#fdfffc', '#235789', '#c1292e', '#f1d302', '#020100'],\n  ['#0D1E40', '#224573', '#5679A6', '#F2A25C', '#D96B43'],\n  ['#7E56A6', '#F28B50', '#A63B14', '#591202', '#260101'],\n  ['#4ED98A', '#3B8C57', '#F2AD85', '#404040', '#0D0D0D'],\n  ['#725373', '#7866F2', '#8979F2', '#025373', '#BF7D56']\n];\n"
        if 'overAllTexture' in adapted and not is_declared('overAllTexture', adapted):
            adapted = "var overAllTexture;\n" + adapted

        # Fix drawingContext radial/linear gradient mismatch (e.g. originalGraphics vs main drawingContext)
        if "originalGraphics" in adapted:
            adapted = re.sub(
                r'(?<![\w.])drawingContext\.(createRadialGradient|createLinearGradient)\s*\(',
                r'originalGraphics.drawingContext.\1(',
                adapted
            )
            # Fix potential historical double-replacement pollution
            if "originalGraphics.originalGraphics" in adapted:
                adapted = adapted.replace("originalGraphics.originalGraphics", "originalGraphics")

        # 5. 防衛性轉譯器常駐外掛 Stub 注入
        if "window._origLoadImage =" not in adapted and "const _origLoadImage =" not in adapted:
            adapted += """

// 1. 免疫 DOM 元素建立並於背景以音視頻段驅動
(function() {
    var _audioChannels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
    var _sliderIdx = 0;

    function _createAudioBoundElement(min, max, defVal, step) {
        var _ch = _audioChannels[(_sliderIdx++) % _audioChannels.length];
        var _min = min !== undefined ? Number(min) : 0;
        var _max = max !== undefined ? Number(max) : 100;
        var _val = defVal !== undefined ? Number(defVal) : (_min + _max) / 2;
        var _step = step !== undefined ? Number(step) : 0;
        var _listeners = {};

        var el = function() { return _sp; };
        el.position = el.style = el.size = el.parent = el.option = el.texture = function() { return el; };
        el.id = function() { return ""; };
        el.class = function() { return el; };
        el.show = el.hide = function() { return el; };
        el.mousePressed = el.mouseClicked = el.html = function() { return el; };
        el.changed = el.input = function(cb) { if (typeof cb === 'function') _listeners['change'] = cb; return el; };
        el.on = el.off = el.addEventListener = el.removeEventListener = el.listen = function() { return el; };
        el.width = 100; el.height = 100;
        el[Symbol.iterator] = function* () { yield el; };

        el.value = function(newVal) {
            if (newVal !== undefined) {
                _val = Number(newVal);
                return el;
            }
            var norm = typeof window[_ch] !== 'undefined' ? Number(window[_ch]) : 0.5;
            var dynVal = _min + norm * (_max - _min);
            if (_step > 0) {
                dynVal = Math.round((dynVal - _min) / _step) * _step + _min;
            }
            return dynVal;
        };

        var handler = {
            get: function(t, p) {
                if (p === 'value') return t.value;
                if (p === 'slider') return t;
                if (p === 'elt') return { value: t.value(), style: {} };
                if (p in t) return t[p];
                if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
                return _sp;
            }
        };
        return new Proxy(el, handler);
    }

    var _do = function() { return _sp; };
    _do.position = _do.style = _do.size = _do.parent = _do.option = _do.texture = function() { return _sp; };
    _do.id = function() { return ""; };
    _do.class = _do.mousePressed = _do.mouseClicked = _do.html = _do.changed = _do.input = function() { return _sp; };
    _do.on = _do.off = _do.addEventListener = _do.removeEventListener = _do.listen = function() { return _sp; };
    _do.value = function() { return 0; };
    _do.width = 100; _do.height = 100;
    _do[Symbol.iterator] = function* () { yield _sp; };
    var _dh = {
        get: function(t, p) {
            if (p === 'slider') return _sp;
            if (p in t) return t[p];
            if (typeof p === 'symbol' || p === 'then' || p === 'toJSON') return undefined;
            return _sp;
        },
        apply: function() { return _sp; },
        construct: function() { return _sp; }
    };
    var _sp = typeof Proxy !== 'undefined' ? new Proxy(_do, _dh) : _do;

    if (typeof createSlider === 'undefined') {
        window.createSlider = function(min, max, defVal, step) {
            return _createAudioBoundElement(min, max, defVal, step);
        };
    }
    if (typeof createP === 'undefined') window.createP = function() { return _sp; };
    if (typeof createDiv === 'undefined') window.createDiv = function() { return _sp; };
    if (typeof createButton === 'undefined') window.createButton = function() { return _sp; };
    if (typeof createInput === 'undefined') window.createInput = function(defVal) { return _createAudioBoundElement(0, 100, defVal || 50, 1); };
    if (typeof createSelect === 'undefined') window.createSelect = function() { return _createAudioBoundElement(0, 5, 0, 1); };
    if (typeof createCheckbox === 'undefined') window.createCheckbox = function() { return _createAudioBoundElement(0, 1, 0, 1); };
    if (typeof createRadio === 'undefined') window.createRadio = function() { return _createAudioBoundElement(0, 5, 0, 1); };
    if (typeof createColorPicker === 'undefined') window.createColorPicker = function() { return _sp; };
    if (typeof createElement === 'undefined') window.createElement = function() { return _sp; };
    if (typeof select === 'undefined') window.select = function() { return _sp; };
    if (typeof selectAll === 'undefined') window.selectAll = function() { return []; };
    window.Pause = window.Pause || _sp;
    window.Play = window.Play || _sp;
    window.Reset = window.Reset || _sp;
})();

// 2. 圖片與非同步資產載入後備自癒護欄
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origLoadImage === 'undefined') { window._origLoadImage = p5.prototype.loadImage; }
    p5.prototype.loadImage = function(path, successCallback, failureCallback) {
        if (typeof path !== 'string' || (path.startsWith('http') === false && path.startsWith('data:') === false)) {
            // 當發現是相對路徑或丟失的外部圖片資產時，使用 1x1 灰色 GIF 的 Base64 代替，防止渲染死鎖
            const dummyPath = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
            return window._origLoadImage.call(this, dummyPath, successCallback, failureCallback);
        }
        return window._origLoadImage.call(this, path, successCallback, failureCallback);
    };
}

// 3. 修正 3D 渲染圖層 WebGL 與 Canvas 2D 上下文屬性缺失
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origGet === 'undefined') { window._origGet = p5.prototype.get; }
    p5.prototype.get = function(...args) {
        if (this.width === 0 || this.height === 0) {
            try {
                if (typeof this.createGraphics === 'function') {
                    return this.createGraphics(10, 10);
                } else if (typeof createGraphics === 'function') {
                    return createGraphics(10, 10);
                }
            } catch(e) {}
            try {
                if (typeof this.createImage === 'function') {
                    return this.createImage(1, 1);
                }
            } catch(e) {}
            return {
                width: 1,
                height: 1,
                pixels: [0, 0, 0, 0],
                loadPixels: function() {},
                updatePixels: function() {},
                get: function() { return [0, 0, 0, 255]; },
                vertices: []
            };
        }
        try {
            return window._origGet.apply(this, args);
        } catch(e) {
            return {
                width: 1,
                height: 1,
                pixels: [0, 0, 0, 0],
                loadPixels: function() {},
                updatePixels: function() {},
                get: function() { return [0, 0, 0, 255]; },
                vertices: []
            };
        }
    };
}
"""

        self.editor.setPlainText(adapted)
        self.log_to_console("SUCCESS: 程式碼轉換已完成，注入 16:9 比例適配與音畫控制映射！")

    def compile_and_run_sandbox(self):
        self.console_log.clear()
        self.has_errors = False
        self.test_run_performed = True
        
        self.adapt_and_repair_code()
        
        name = self.name_input.text().strip()
        if not name:
            self.log_to_console("ERROR: 模組名稱不得為空！", is_err=True)
            return

        code = self.editor.toPlainText()
        try:
            debug_dir = os.path.join(workspace_dir, "scratch")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "debug_sketch.js"), "w", encoding="utf-8") as df:
                df.write(code)
        except Exception as e:
            self.log_to_console(f"[DEBUG] 寫入偵錯檔案失敗: {e}")
        self.log_to_console("正在編譯 p5.js 畫布並啟動測試沙盒...")

        custom_css = getattr(self, "custom_css", "")
        custom_html = self.cache_and_localize_scripts(getattr(self, "custom_html", "") or "")
        inline_assets = getattr(self, "inline_assets", {})
        sketch_id = getattr(self, "current_preset_id", None)
        scaling_mode = getattr(self, "current_scaling_mode", "auto")

        # 使用統一且經過嚴格驗證的 get_html_content 生成 HTML 結構
        html = self.get_html_content(
            code,
            custom_css=custom_css,
            custom_html=custom_html,
            inline_assets=inline_assets,
            sketch_id=sketch_id,
            scaling_mode=scaling_mode,
            for_thumbnail=False,
            for_rendering=False
        )

        # 注入沙盒即時音訊動態模擬與滑桿控制
        sandbox_controls = f"""
        <script>
          window.frequency = {self.freq_slider.value()};
          window.storyboardWeight = {self.weight_slider.value()};
          window.postFxIntensity = {self.fx_slider.value()};
          window.isBeat = false;
          window.beatEnergy = 0;
          window.audioLow = 0.5;
          window.audioMid = 0.5;
          window.audioHigh = 0.5;
          window.simulatedMouseX = 640;
          window.simulatedMouseY = 360;
          window.simulatedPMouseX = 640;
          window.simulatedPMouseY = 360;

          window.triggerBeat = function() {{
            window.isBeat = true;
            window.beatEnergy = 1.0;
            
            let w = typeof width !== 'undefined' ? width : (window.innerWidth || 1280);
            let h = typeof height !== 'undefined' ? height : (window.innerHeight || 720);
            
            window.simulatedPMouseX = window.simulatedMouseX;
            window.simulatedPMouseY = window.simulatedMouseY;
            window.simulatedMouseX = Math.random() * w;
            window.simulatedMouseY = Math.random() * h;
            
            if (typeof window._triggerMockButtons === 'function') {{
              try {{ window._triggerMockButtons(); }} catch(e) {{}}
            }}
            
            let duration = 30 + (window.audioLow || 0.5) * 400;
            setTimeout(() => {{ 
              window.isBeat = false; 
            }}, duration);
          }};

          function tick() {{
            let w = typeof width !== 'undefined' ? width : (window.innerWidth || 1280);
            let h = typeof height !== 'undefined' ? height : (window.innerHeight || 720);
            
            window.simulatedPMouseX = window.simulatedMouseX || (w / 2);
            window.simulatedPMouseY = window.simulatedMouseY || (h / 2);
            let prevX = window.simulatedMouseX;
            let prevY = window.simulatedMouseY;

            if (window.beatEnergy > 0) window.beatEnergy *= 0.92;
            var _now = Date.now();
            window.audioLow = 0.2 + 0.3 * Math.sin(_now * 0.005) + (window.beatEnergy * 0.5);
            window.audioMid = 0.15 + 0.25 * Math.sin(_now * 0.007);
            window.audioHigh = 0.1 + 0.2 * Math.sin(_now * 0.01) + (window.beatEnergy * 0.3);
            
            var hue = (_now * 0.01) % 360;
            let hFactor = hue / 60;
            let c = 0.3;
            let x = c * (1 - Math.abs(hFactor % 2 - 1));
            let r1=0, g1=0, b1=0;
            if (hFactor >= 0 && hFactor < 1) {{ r1=c; g1=x; }}
            else if (hFactor >= 1 && hFactor < 2) {{ r1=x; g1=c; }}
            else if (hFactor >= 2 && hFactor < 3) {{ g1=c; b1=x; }}
            else if (hFactor >= 3 && hFactor < 4) {{ g1=x; b1=c; }}
            else if (hFactor >= 4 && hFactor < 5) {{ r1=x; b1=c; }}
            else {{ r1=c; b1=x; }}
            let rVal = Math.round((r1 + 0.05) * 255).toString(16).padStart(2, '0');
            let gVal = Math.round((g1 + 0.05) * 255).toString(16).padStart(2, '0');
            let bVal = Math.round((b1 + 0.05) * 255).toString(16).padStart(2, '0');
            window.currentChordColor = '#' + rVal + gVal + bVal;
            
            if (!window.isBeat) {{
              window.simulatedMouseX = w / 2 + (window.audioLow - 0.5) * w * 0.6;
              window.simulatedMouseY = h / 2 + (window.audioMid - 0.5) * h * 0.6;
            }}
            window.simulatedPMouseX = prevX;
            window.simulatedPMouseY = prevY;
            
            try {{
              let moveEvt = new MouseEvent('mousemove', {{ clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, bubbles: true }});
              window.dispatchEvent(moveEvt);
              let canvas = document.querySelector('canvas');
              if (canvas) {{
                canvas.dispatchEvent(moveEvt);
              }}
            }} catch(e) {{}}
            
            requestAnimationFrame(tick);
          }}
          requestAnimationFrame(tick);
        </script>
        """

        if "</head>" in html:
            html = html.replace("</head>", f"{sandbox_controls}\n</head>", 1)
        else:
            html = sandbox_controls + html

        self.web_view.setHtml(html, get_local_base_url())
        if not self.beat_timer.isActive():
            self.beat_timer.start(500)
        self.btn_stop_compile.setEnabled(True)
            
        QTimer.singleShot(1000, self.check_sandbox_success)

    def stop_sandbox_preview(self):
        self.beat_timer.stop()
        self.web_view.setHtml(self.placeholder_html, get_local_base_url())
        self.btn_stop_compile.setEnabled(False)
        self.log_to_console("沙盒預覽已手動停止，節奏定時器已關閉。")

    def open_debug_log_file(self):
        log_path = os.path.join(workspace_dir, "app_debug.log")
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=== 4K MV Visual Integration Editor 診斷日誌 ===\n")
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", log_path])
            elif sys.platform == "win32":
                os.startfile(log_path)
            else:
                subprocess.Popen(["xdg-open", log_path])
            self.log_to_console(f"已開啟診斷日誌檔案: {log_path}")
        except Exception as e:
            self.log_to_console(f"開啟日誌失敗: {e}", is_err=True)

    def check_sandbox_success(self):
        if not self.has_errors:
            self.log_to_console("沙盒編譯成功！節奏與頻率動態運行中。")
            self.cb_confirm.setEnabled(True)

        def _on_inspect(res):
            if res:
                self.log_to_console(f"🔍 [沙盒狀態檢測] {res}")

        js_inspect = """
        (function() {
            var cnv = document.querySelector('canvas');
            var cnvInfo = cnv ? (cnv.width + 'x' + cnv.height + ' (style: ' + cnv.style.width + 'x' + cnv.style.height + ', display: ' + window.getComputedStyle(cnv).display + ')') : 'None';
            var p5Inst = window._p5Instance || (typeof p5 !== 'undefined' && (p5.instance || (p5.activeInstances && p5.activeInstances[0])));
            var p5State = p5Inst ? ('isLooping: ' + p5Inst._loop + ', frameCount: ' + p5Inst.frameCount) : 'NoInstance';
            var errs = window.jsErrors && window.jsErrors.length ? (' | Errors: ' + JSON.stringify(window.jsErrors)) : '';
            return 'Canvas: ' + cnvInfo + ' | p5: ' + p5State + ' | setup: ' + (typeof window.setup) + ' | draw: ' + (typeof window.draw) + errs;
        })();
        """
        self.web_view.page().runJavaScript(js_inspect, _on_inspect)

    def trigger_simulated_beat(self):
        if self.test_run_performed and not self.has_errors:
            self.web_view.page().runJavaScript("if(window.triggerBeat) window.triggerBeat();")

    def save_preset(self):
        name = self.name_input.text().strip()
        import re
        if not name or not re.match(r'^[a-zA-Z0-9_-]+$', name):
            QMessageBox.critical(self, "錯誤", "模組名稱必須為英數字、底線(_)或連字號(-)！")
            return
            
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)
        
        author = self.author_input.text().strip()

        # --- 重複收錄檢測 (Duplicate Module Detection) ---
        current_code = self.editor.toPlainText().strip()
        current_url = self.op_input.text().strip() if hasattr(self, 'op_input') else ""

        # Look for an existing file with the same name AND same author to decide overwrite
        existing_file_path = None
        for fname in os.listdir(save_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(save_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as ef:
                        existing = json.load(ef)
                    if existing.get("name", "").strip() == name and existing.get("author", "").strip() == author:
                        existing_file_path = fpath
                        break
                except Exception:
                    continue

        if existing_file_path:
            display_author = f" (作者: {author})" if author else ""
            reply = QMessageBox.question(
                self, "名稱衝突",
                f"模組「{name}」{display_author}已經存在。\n是否要覆蓋現有模組？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            save_path = existing_file_path
            unique_name = os.path.basename(save_path)[:-5]
        else:
            # Determine a new unique filename
            sanitized_author = "".join([c for c in author if c.isalnum() or c in ('-', '_')]).strip() if author else ""
            if sanitized_author:
                base_filename = f"{name}_{sanitized_author}"
            else:
                base_filename = name
                
            candidate = f"{base_filename}.json"
            counter = 1
            while os.path.exists(os.path.join(save_dir, candidate)):
                candidate = f"{base_filename}_{counter}.json"
                counter += 1
            save_path = os.path.join(save_dir, candidate)
            unique_name = candidate[:-5]

        # 2. 掃描所有已收錄模組，比對 URL 和程式碼
        def _normalize_code(code_str):
            """移除空白與換行差異，用於程式碼相似度比對"""
            return re.sub(r'\s+', '', code_str)

        normalized_current = _normalize_code(current_code) if current_code else ""
        duplicate_by_url = None
        duplicate_by_code = None

        for fname in os.listdir(save_dir):
            if not fname.endswith(".json") or fname == f"{unique_name}.json":
                continue
            try:
                fpath = os.path.join(save_dir, fname)
                with open(fpath, "r", encoding="utf-8") as ef:
                    existing = json.load(ef)
                existing_name = fname[:-5]  # 去除 .json 副檔名

                # URL 比對
                if current_url and existing.get("url", ""):
                    if current_url.rstrip("/") == existing.get("url", "").rstrip("/"):
                        duplicate_by_url = existing_name
                        break

                # 程式碼比對 (正規化後完全一致)
                existing_code = existing.get("code", "").strip()
                if normalized_current and existing_code:
                    if _normalize_code(existing_code) == normalized_current:
                        duplicate_by_code = existing_name
                        break
            except Exception:
                continue

        if duplicate_by_url:
            reply = QMessageBox.warning(
                self, "⚠️ 重複收錄偵測",
                f"此 OpenProcessing 網址已收錄於模組「{duplicate_by_url}」。\n\n"
                f"確定仍要另存為「{name}」嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if duplicate_by_code:
            reply = QMessageBox.warning(
                self, "⚠️ 重複收錄偵測",
                f"此程式碼與已收錄模組「{duplicate_by_code}」的內容完全一致。\n\n"
                f"確定仍要另存為「{name}」嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        # --- 重複檢測結束 ---
        
        import datetime
        data = {
            "name": name,
            "code": self.editor.toPlainText(),
            "frequency": self.freq_slider.value(),
            "storyboard_weight": self.weight_slider.value(),
            "post_fx_intensity": self.fx_slider.value(),
            "custom_html": getattr(self, "custom_html", ""),
            "custom_css": getattr(self, "custom_css", ""),
            "inline_assets": getattr(self, "inline_assets", {}),
            "author": self.author_input.text().strip(),
            "license": self.license_input.text().strip(),
            "tags": [t.strip() for t in self.tags_input.text().split(",") if t.strip()],
            "url": self.op_input.text().strip(),
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # 刪除舊縮圖以強制重新生成最新畫面 (因為程式碼可能被修改了)
        thumb_dir = os.path.join(workspace_dir, "custom_visuals", "thumbnails")
        dest_thumb_path = os.path.join(thumb_dir, f"{unique_name}.jpg")
        if os.path.exists(dest_thumb_path):
            try:
                os.remove(dest_thumb_path)
            except Exception as e:
                print(f"刪除舊縮圖失敗: {e}")

        # 下載並快取縮圖
        sketch_id = getattr(self, "last_fetched_sketch_id", None)
        if sketch_id:
            thumb_dir = os.path.join(workspace_dir, "custom_visuals", "thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            dest_thumb_path = os.path.join(thumb_dir, f"{unique_name}.jpg")
            try:
                import requests
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                thumb_url = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}.jpg"
                img_resp = requests.get(thumb_url, headers=headers, timeout=5)
                if img_resp.status_code == 200:
                    with open(dest_thumb_path, "wb") as img_f:
                        img_f.write(img_resp.content)
                else:
                    thumb_url_png = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}.png"
                    img_resp = requests.get(thumb_url_png, headers=headers, timeout=5)
                    if img_resp.status_code == 200:
                        with open(dest_thumb_path, "wb") as img_f:
                            img_f.write(img_resp.content)
            except Exception as e:
                print(f"下載縮圖失敗: {e}")
            
        self.log_to_console(f"預設檔已成功儲存至: {save_path}")
        self.cached_presets = None  # 儲存新預設後使記憶體快取失效
        self.refresh_presets_list()
        QMessageBox.information(self, "儲存成功", f"視覺預設檔 {name} 儲存成功！")

    def check_mac_thermal_state(self):
        """Query macOS thermal warning state and CPU speed limit using pmset."""
        try:
            import subprocess
            import platform
            if platform.system() != 'Darwin':
                return 100, False
            
            res = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=1.0)
            output = res.stdout
            
            speed_limit = 100
            for line in output.split('\n'):
                if "CPU_Speed_Limit" in line:
                    parts = line.split('=')
                    if len(parts) == 2:
                        try:
                            speed_limit = int(parts[1].strip())
                        except ValueError:
                            pass
            
            has_warning = False
            for line in output.split('\n'):
                if "warning" in line.lower():
                    # Serious or critical warning level
                    if "no thermal warning" not in line.lower() and "no performance warning" not in line.lower():
                        has_warning = True
            
            return speed_limit, has_warning
        except Exception as e:
            logger.warning(f"Error checking thermal state: {e}")
            return 100, False

    def delete_preset(self, name):
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        save_path = os.path.join(save_dir, f"{name}.json")
        if os.path.exists(save_path):
            reply = QMessageBox.question(
                self, "確認刪除", f"確定要刪除視覺預設檔「{name}」嗎？\n此動作將無法復原。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.remove(save_path)
                    # Clean up thumbnail as well
                    thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                    self.log_to_console(f"預設檔與縮圖已刪除: {name}")
                    self.checked_presets.discard(name)
                    self.cached_presets = None  # 刪除檔案後使快取失效
                    self.refresh_presets_list(keep_page=True)
                except Exception as e:
                    QMessageBox.critical(self, "錯誤", f"刪除檔案失敗: {e}")

    def toggle_star_preset(self, name):
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        save_path = os.path.join(save_dir, f"{name}.json")
        if os.path.exists(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f_in:
                    data = json.load(f_in)
                current_starred = data.get("is_starred", False)
                data["is_starred"] = not current_starred
                with open(save_path, "w", encoding="utf-8") as f_out:
                    json.dump(data, f_out, indent=4, ensure_ascii=False)
                status = "已加到我的最愛 ⭐" if not current_starred else "已取消最愛 ☆"
                self.log_to_console(f"「{name}」{status}")
                self.cached_presets = None  # 更新最愛狀態後使快取失效
                self.refresh_presets_list()
            except Exception as e:
                self.log_to_console(f"最愛狀態更新失敗: {e}", is_err=True)

    def clear_all_stars(self):
        reply = QMessageBox.question(
            self, "確認動作", "確定要取消所有視覺預設的「我的最愛 (★)」標記嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        if not os.path.exists(save_dir):
            return
            
        cleared_count = 0
        for file in os.listdir(save_dir):
            if file.endswith(".json"):
                p_path = os.path.join(save_dir, file)
                try:
                    with open(p_path, "r", encoding="utf-8") as f_in:
                        data = json.load(f_in)
                    if data.get("is_starred", False):
                        data["is_starred"] = False
                        with open(p_path, "w", encoding="utf-8") as f_out:
                            json.dump(data, f_out, indent=4, ensure_ascii=False)
                        cleared_count += 1
                except Exception as e:
                    pass
        self.log_to_console(f"🧹 已成功一鍵取消共 {cleared_count} 個模組的我的最愛勾選。")
        self.cached_presets = None  # 批次取消最愛後使快取失效
        self.refresh_presets_list()

    def preview_preset(self, name):
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        save_path = os.path.join(save_dir, f"{name}.json")
        if not os.path.exists(save_path):
            self.log_to_console(f"ERROR: 找不到視覺預設檔 {name}", is_err=True)
            return
            
        try:
            self.current_preset_id = name
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.name_input.setText(data.get("name", name))
            self.editor.setPlainText(data.get("code", ""))
            self.freq_slider.setValue(data.get("frequency", 50))
            self.weight_slider.setValue(data.get("storyboard_weight", 50))
            self.fx_slider.setValue(data.get("post_fx_intensity", 50))
            self.author_input.setText(data.get("author", "未知"))
            self.license_input.setText(data.get("license", "未知"))
            self.tags_input.setText(", ".join(data.get("tags", [])))
            self.op_input.setText(data.get("url", ""))
            self.custom_css = data.get("custom_css", "")
            self.custom_html = data.get("custom_html", "")
            self.inline_assets = data.get("inline_assets", {})
            self.current_scaling_mode = data.get("scaling_mode", "auto")
            
            self.cb_confirm.setEnabled(True)
            self.cb_confirm.setChecked(True)
            self.btn_save.setEnabled(True)
            
            self.log_to_console(f"已加載視覺預設檔「{name}」，正在右方啟動即時沙盒預覽...")
            self.compile_and_run_sandbox()
            
        except Exception as e:
            self.log_to_console(f"ERROR: 讀取預設檔 {name} 失敗: {e}", is_err=True)

    def clear_sandbox(self):
        self.stop_sandbox_preview()
        self.console_log.clear()
        self.log_to_console("即時沙盒畫面與終端日誌已清空。")

    def get_default_template(self):
        return """// p5.js 音畫互動自訂模組範本
let rot = 0;
function setup() {
  createCanvas(windowWidth, windowHeight);
}
function draw() {
  background(0, 20);
  
  let size = 150 + window.beatEnergy * 100;
  translate(width / 2, height / 2);
  rotate(rot);
  
  stroke(255);
  strokeWeight(2 + window.audioHigh * 5);
  noFill();
  
  ellipse(0, 0, size, size * 0.6);
  rot += 0.02 + window.audioLow * 0.05;
}"""

    def set_render_buttons_enabled(self, enabled):
        self.btn_render.setEnabled(enabled)
        if hasattr(self, "btn_smart_edit"):
            self.btn_smart_edit.setEnabled(enabled)
        if hasattr(self, "btn_batch_smart_edit"):
            self.btn_batch_smart_edit.setEnabled(enabled)

    def perform_smart_clip_matching(self, audio_path, show_popups=True, batch_used_keys=None):
        # Perform audio analysis to get the storyboard sections
        try:
            detector = AudioBeatDetector()
            analysis = detector.analyze(audio_path, self.genre_select.currentText())
        except Exception as e:
            if show_popups:
                QMessageBox.critical(self, "分析失敗", f"音軌分析失敗: {e}")
            self.log_to_console(f"音軌分析失敗: {e}", is_err=True)
            return None
        
        storyboard = analysis.get('storyboard', [])
        if not storyboard:
            if show_popups:
                QMessageBox.warning(self, "錯誤", "無法從音訊中產生分鏡腳本！")
            self.log_to_console("無法從音訊中產生分鏡腳本！", is_err=True)
            return None
        
        # Load module usage history from disk to ensure cross-session diversity
        history_file = os.path.join(workspace_dir, "custom_visuals", "module_usage_history.json")
        usage_history = {}
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    usage_history = json.load(f)
            except Exception:
                usage_history = {}

        # Load all presets in the library
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        all_modules = []
        for file in os.listdir(save_dir):
            if file.endswith(".json") and file != "module_usage_history.json":
                p_path = os.path.join(save_dir, file)
                try:
                    with open(p_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        code = data.get("code", "")
                        if not code or len(code) < 30 or "setup" not in code or "draw" not in code:
                            continue
                        key = file[:-5]
                        data["_filename_key"] = key
                        used_in = data.get("used_in_videos", [])
                        file_used = max(int(data.get("used_count", 0)), len(used_in) if isinstance(used_in, list) else 0)
                        hist_used = int(usage_history.get(key, 0)) if isinstance(usage_history.get(key), (int, float)) else 0
                        effective_used = max(file_used, hist_used)
                        data["used_count"] = effective_used
                        data["_history_used"] = effective_used
                        all_modules.append(data)
                except Exception as e:
                    print(f"無法讀取模組 {file}: {e}")
                    
        if not all_modules:
            if show_popups:
                QMessageBox.warning(self, "錯誤", "模組庫中沒有可用的視覺模組！")
            self.log_to_console("模組庫中沒有可用的視覺模組！", is_err=True)
            return None
            
        # ── 1. 強制按「我的最愛」優先與真實使用次數嚴格升序排序 ──
        import random
        all_modules.sort(key=lambda x: (
            not x.get("is_starred", False),
            int(x.get("used_count", 0)),
            batch_used_keys.get(x["_filename_key"], 0),
            random.random()
        ))

        recent_keys = [k for k, v in usage_history.items() if isinstance(v, (int, float)) and v > 1]
        self.log_to_console("🧠 正在呼叫本地 AI 導演大腦 (Llama3/DeepSeek) 構思全曲世界觀與分鏡表...")
        
        from llm_director import LLMDirectorAgent
        llm_agent = LLMDirectorAgent()
        director_script = llm_agent.generate_director_script(analysis, all_modules, recent_keys)
        self.current_director_script = director_script

        if hasattr(self, "call_sheet_widget"):
            self.call_sheet_widget.update_call_sheet(director_script, storyboard)

        selected_keys = set()
        for shot in director_script.get("shot_list", []):
            mod_id = shot.get("assigned_module_id")
            if mod_id:
                selected_keys.add(mod_id)

        # 若 LLM 選擇之模組數量偏少，以階梯式最低使用次數補充至 4~6 個
        if len(selected_keys) < 4 and len(all_modules) >= 4:
            for vis in all_modules:
                v_key = vis["_filename_key"]
                if v_key not in selected_keys:
                    selected_keys.add(v_key)
                    if len(selected_keys) >= 4:
                        break
                    
        # 更新全域歷史使用計數，確保下次挑選輪替
        for k in selected_keys:
            usage_history[k] = (int(usage_history.get(k, 0)) if isinstance(usage_history.get(k), (int, float)) else 0) + 1

        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(usage_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"無法寫入歷史紀錄 {history_file}: {e}")

        # Select in tracking set and refresh UI
        self.checked_presets = set(selected_keys)
        self.cached_presets = None
        self.refresh_presets_list(clean_black=True, keep_page=True)
                
        theme = director_script.get("theme_title", "Custom Procedural")
        self.log_to_console(f"🎬 AI 導演排片就緒！世界觀「{theme}」，精選 {len(selected_keys)} 個獨特視覺模組。")
        return selected_keys

    def start_ai_director_orchestration(self):
        audio_path = self.audio_input.text().strip()
        if not audio_path:
            QMessageBox.warning(self, "提示", "請先選擇音訊檔案！")
            return
        
        self.set_render_buttons_enabled(False)
        if hasattr(self, "btn_ai_director"):
            self.btn_ai_director.setEnabled(False)
            self.btn_ai_director.setText("⏳ AI 導演排片中...")

        # Load modules from disk
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        history_file = os.path.join(save_dir, "module_usage_history.json")
        usage_history = {}
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    usage_history = json.load(f)
            except Exception:
                pass

        all_modules = []
        for file in os.listdir(save_dir):
            if file.endswith(".json") and file != "module_usage_history.json":
                p_path = os.path.join(save_dir, file)
                try:
                    with open(p_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        code = data.get("code", "")
                        if not code or len(code) < 30 or "setup" not in code or "draw" not in code:
                            continue
                        key = file[:-5]
                        data["_filename_key"] = key
                        used_in = data.get("used_in_videos", [])
                        file_used = max(int(data.get("used_count", 0)), len(used_in) if isinstance(used_in, list) else 0)
                        hist_used = int(usage_history.get(key, 0)) if isinstance(usage_history.get(key), (int, float)) else 0
                        effective_used = max(file_used, hist_used)
                        data["used_count"] = effective_used
                        data["_history_used"] = effective_used
                        all_modules.append(data)
                except Exception:
                    pass

        import random
        all_modules.sort(key=lambda x: (not x.get("is_starred", False), int(x.get("used_count", 0)), random.random()))

        recent_keys = [k for k, v in usage_history.items() if isinstance(v, (int, float)) and v > 1]
        genre = self.genre_select.currentText()

        self.director_thread = AIDirectorOrchestrationThread(audio_path, genre, all_modules, recent_keys)
        self.director_thread.log_signal.connect(lambda msg, is_err: self.log_to_console(msg, is_err))
        self.director_thread.script_ready.connect(self._on_director_script_ready)
        self.director_thread.finished.connect(lambda: (
            self.set_render_buttons_enabled(True),
            self.btn_ai_director.setEnabled(True),
            self.btn_ai_director.setText("🎬 【AI 導演智能排片 (LLM Script)】")
        ))
        self.director_thread.start()

    def _on_director_script_ready(self, script_data: dict, analysis_data: dict):
        self.current_director_script = script_data
        storyboard = analysis_data.get("storyboard", [])
        if hasattr(self, "call_sheet_widget"):
            self.call_sheet_widget.update_call_sheet(script_data, storyboard)

        # Select the chosen modules in checked_presets and refresh UI
        chosen_keys = set()
        for shot in script_data.get("shot_list", []):
            mod_id = shot.get("assigned_module_id")
            if mod_id:
                chosen_keys.add(mod_id)
        
        if chosen_keys:
            self.checked_presets = chosen_keys
            self.refresh_presets_list(keep_page=True)

        theme = script_data.get("theme_title", "")
        self.log_to_console(f"🎬 AI 導演排片完成！已生成主題「{theme}」，精選 {len(chosen_keys)} 組視覺模組！")
        QMessageBox.information(self, "AI 導演劇本已就緒", f"🎉 AI 導演排片完成！\n\n美學世界觀：{theme}\n色彩氛圍：{script_data.get('color_palette_mood', '')}\n\n已將分鏡表同步至上方「AI 導演通告單」並勾選對應視覺模組。點擊「開始渲染」即可直接產出 4K MV！")

    def start_smart_edit_rendering(self):
        audio_path = self.audio_input.text().strip()
        if not audio_path:
            QMessageBox.warning(self, "錯誤", "請先選擇音樂檔案！")
            return
        
        # Disable buttons immediately to prevent double clicks
        self.set_render_buttons_enabled(False)
        self.status_lbl.setText("正在分析音軌特徵與進行智能分鏡剪輯...")
        QApplication.processEvents()

        selected_keys = self.perform_smart_clip_matching(audio_path, show_popups=True)
        if not selected_keys:
            self.set_render_buttons_enabled(True)
            self.status_lbl.setText("分析失敗")
            return
            
        self.set_render_buttons_enabled(True)
        # Trigger regular rendering pipeline
        self.start_mv_rendering()

    def start_batch_smart_edit_rendering(self):
        audio_dir = self.audio_dir_input.text().strip()
        if not audio_dir or not os.path.isdir(audio_dir):
            QMessageBox.warning(self, "錯誤", "請先選擇有效的音訊來源資料夾！")
            return
            
        audio_files = []
        for file in os.listdir(audio_dir):
            if file.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')):
                audio_files.append(os.path.join(audio_dir, file))
        audio_files.sort()
        
        if not audio_files:
            QMessageBox.warning(self, "錯誤", "資料夾中沒有找到支援的音訊檔案 (.mp3, .wav, .m4a, .flac)！")
            return
            
        out_dir = safe_get_existing_directory(self, "選擇批次渲染影片的儲存位置/資料夾")
        if not out_dir:
            return
            
        self.set_render_buttons_enabled(False)
        self.btn_cancel_render.setEnabled(True)
        self.render_aborted = False
        
        success_count = 0
        failed_files = []
        
        total_songs = len(audio_files)
        import time
        self.is_batch_rendering = True
        self.batch_total_songs = total_songs
        self.batch_start_time = time.time()
        self.batch_completed_frames = 0
        self._batch_used_themes = []  # 追蹤已使用的視覺主題以確保跨曲目多樣性
        self._batch_used_module_counts = {}  # 追蹤已使用的視覺模組以確保跨曲目視覺豐富度
        
        for index, audio_path in enumerate(audio_files):
            self.batch_current_idx = index
            if self.render_aborted:
                self.log_to_console("批次渲染被使用者中止。", is_err=True)
                break
                
            filename = os.path.basename(audio_path)
            self.log_to_console(f"\n--- 開始批次處理 ({index + 1}/{total_songs}): {filename} ---")
            self.status_lbl.setText(f"批次處理 ({index + 1}/{total_songs}): {filename}")
            QApplication.processEvents()
            
            # Step 0: 優先進行檔案比對，判斷是否已渲染並跳過（防止未比對前先執行視覺庫準備與音軌分析）
            name, _ = os.path.splitext(filename)
            output_file = os.path.join(out_dir, f"{name}.mp4")
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1024 * 1024:
                import subprocess
                def get_duration(file_path):
                    try:
                        cmd = [
                            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
                        ]
                        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                        dur = float(res.stdout.strip())
                        if dur > 0:
                            return dur
                    except Exception:
                        pass
                    try:
                        import soundfile as sf
                        info = sf.info(file_path)
                        return float(info.duration)
                    except Exception:
                        pass
                    try:
                        import librosa
                        return float(librosa.get_duration(path=file_path))
                    except Exception:
                        pass
                    return 0.0
                
                video_dur = get_duration(output_file)
                audio_dur = get_duration(audio_path)
                
                if video_dur > 0 and audio_dur > 0 and abs(video_dur - audio_dur) <= 1.0:
                    self.log_to_console(f"【跳過】偵測到已完成的影片檔案（長度一致：{video_dur:.1f}秒 / {audio_dur:.1f}秒），自動跳過: {filename}")
                    success_count += 1
                    continue
                else:
                    self.log_to_console(f"⚠️ 偵測到影片檔案，但長度不一致（影片 {video_dur:.1f}秒 vs 音訊 {audio_dur:.1f}秒），將重新渲染: {filename}", is_err=True)
            
            # Step 1: Perform smart clip matching for this audio file with cross-track module diversity penalty
            selected_keys = self.perform_smart_clip_matching(audio_path, show_popups=False, batch_used_keys=self._batch_used_module_counts)
            if not selected_keys:
                self.log_to_console(f"跳過 {filename}: 智能剪輯匹配失敗", is_err=True)
                failed_files.append((filename, "智能剪輯匹配分析失敗"))
                continue
                
            # 直接使用專為本首曲目匹配的視覺模組清單 selected_keys
            selected_presets = list(selected_keys)
            # 累計本批次使用次數
            for key in selected_presets:
                self._batch_used_module_counts[key] = self._batch_used_module_counts.get(key, 0) + 1
                        
            if not selected_presets:
                self.log_to_console(f"跳過 {filename}: 未選取任何視覺模組", is_err=True)
                failed_files.append((filename, "未選取任何視覺模組"))
                continue
                
            # Load preset details
            visuals_data = []
            save_dir = os.path.join(workspace_dir, "custom_visuals")
            for vp in selected_presets:
                if vp == "modules_index":
                    continue
                p_path = os.path.join(save_dir, f"{vp}.json")
                if os.path.exists(p_path):
                    with open(p_path, "r", encoding="utf-8") as f:
                        preset_dict = json.load(f)
                        if not isinstance(preset_dict, dict) or 'code' not in preset_dict:
                            continue
                        if 'name' not in preset_dict:
                            preset_dict['name'] = preset_dict.get('title', vp)
                        visuals_data.append(preset_dict)
                        
            # Resolution config
            res_str = self.res_select.currentText()
            if "4K" in res_str:
                w, h = 3840, 2160
            elif "1080p" in res_str:
                w, h = 1920, 1080
            else:
                w, h = 1280, 720
                
            fps = int(self.fps_select.currentText())
            trans_sec = self.trans_slider.value() / 10.0
            fx_prob = self.fx_prob_slider.value() / 100.0
            genre = self.genre_select.currentText()
            
            # Increment used count
            video_id = f"{name}.mp4"
            for vp in selected_presets:
                p_path = os.path.join(save_dir, f"{vp}.json")
                if os.path.exists(p_path):
                    try:
                        with open(p_path, "r", encoding="utf-8") as f_in:
                            data = json.load(f_in)
                        used_in = data.get("used_in_videos", [])
                        if video_id not in used_in:
                            used_in.append(video_id)
                            data["used_in_videos"] = used_in
                            data["used_count"] = data.get("used_count", 0) + 1
                            with open(p_path, "w", encoding="utf-8") as f_out:
                                json.dump(data, f_out, indent=4, ensure_ascii=False)
                    except Exception as e:
                        print(f"無法增加使用次數: {e}")
            self.cached_presets = None
            self.refresh_presets_list(clean_black=True, keep_page=True)
            
            # Collect post-FX flags
            fx_flags = {
                'spatial_warping': self.fx_cb_distortion.isChecked(),
                'fluid_noise': self.fx_cb_fluid_noise.isChecked(),
                'temporal_feedback': self.fx_cb_feedback_dynamics.isChecked(),
                'color_spectral': self.fx_cb_color_aberration.isChecked(),
                'glow_illumination': self.fx_cb_glow_illumination.isChecked(),
                'retro_degradation': self.fx_cb_retro_degradation.isChecked(),
                'pixel_sort': self.fx_cb_pixel_sort.isChecked(),
                'kaleidoscope': self.fx_cb_kaleidoscope.isChecked(),
                'ambient_dsp': self.fx_cb_ambient_dsp.isChecked(),
                'adaptive_modulation': self.fx_cb_adaptive.isChecked(),
                # 新增全域與衍生特效
                'data_mosh': self.fx_cb_data_mosh.isChecked(),
                'sedimentation': self.fx_cb_sedimentation.isChecked(),
                'vector_scan': self.fx_cb_vector_scan.isChecked(),
                'temporal_fractal': self.fx_cb_temporal_fractal.isChecked(),
                'phase_slit': self.fx_cb_phase_slit.isChecked(),
                'centroid_glitch': self.fx_cb_centroid_glitch.isChecked(),
                'vignette_pulse': self.fx_cb_vignette_pulse.isChecked(),
                'tension_overlay': self.fx_cb_tension_overlay.isChecked(),
                'photosensitive_safe': self.fx_cb_photosensitive_safe.isChecked(),
                # 自訂擴充特效
                'thermal_vision': self.fx_cb_thermal_vision.isChecked(),
                'scanline_glitch': self.fx_cb_scanline_glitch.isChecked(),
                'frame_drop': self.fx_cb_frame_drop.isChecked(),
                'dynamic_mosaic': self.fx_cb_dynamic_mosaic.isChecked(),
                'pixel_art': self.fx_cb_pixel_art.isChecked(),
                'handheld_camera': self.fx_cb_handheld_camera.isChecked(),
                'stylized_fade': self.fx_cb_stylized_fade.isChecked(),
                'zoom_pulse': self.fx_cb_zoom_pulse.isChecked(),
                # 頂級全域後製特效矩陣擴充
                'film_burn': self.fx_cb_film_burn.isChecked(),
                'blueprint_edge': self.fx_cb_blueprint.isChecked(),
                'turing_pattern': self.fx_cb_turing.isChecked(),
                'point_cloud_depth': self.fx_cb_point_cloud.isChecked(),
                'vector_scope': self.fx_cb_vector_scope.isChecked(),
                'lowpass_muffle': self.fx_cb_lowpass_muffle.isChecked(),
                'infinity_tunnel': self.fx_cb_infinity_tunnel.isChecked(),
                'dolly_zoom': self.fx_cb_dolly_zoom.isChecked(),
                'bypass_downscale': self.native_4k_cb.isChecked()
            }
            
            # Step 2: Trigger frame-by-frame rendering with show_popups=False and is_batch=True
            success = self.render_mv_frame_by_frame(
                audio_path, genre, visuals_data, output_file, w, h, fps, trans_sec, fx_prob, fx_flags,
                show_popups=False, is_batch=True,
                used_themes=getattr(self, '_batch_used_themes', None)
            )
            
            if success:
                success_count += 1
                # 追蹤已使用的視覺主題以確保跨曲目多樣性
                if hasattr(self, '_last_post_processor') and self._last_post_processor:
                    used_t = self._last_post_processor.selected_theme
                    self._batch_used_themes.append(used_t)
                    self.log_to_console(f"◆ 視覺主題: {used_t} | 累計已用: {self._batch_used_themes}")
                self.log_to_console(f"批次處理成功: {filename} -> {output_file}")
            else:
                self.log_to_console(f"批次處理失敗或被中止: {filename}", is_err=True)
                failed_files.append((filename, "渲染失敗或被使用者中止"))
                
        # Batch Completed
        self.is_batch_rendering = False
        self.set_render_buttons_enabled(True)
        self.btn_cancel_render.setEnabled(False)
        self.status_lbl.setText("批次渲染結束")
        
        summary = f"批次智能剪輯配對並渲染結束！\n成功: {success_count} / {total_songs} 首歌曲。"
        if failed_files:
            summary += "\n\n未成功清單:\n" + "\n".join([f"- {name}: {reason}" for name, reason in failed_files])
            
        QMessageBox.information(self, "批次渲染結果", summary)

    # ----------------------------------------------------
    # MV Rendering Pipeline (Offline 4K Render Engine)
    # ----------------------------------------------------
    def start_mv_rendering(self):
        audio_path = self.audio_input.text().strip()
        if not audio_path:
            QMessageBox.warning(self, "錯誤", "請先選擇音樂檔案！")
            return
            
        # 若未手動勾選特定模組，自動調用智能剪輯進行輪替配對
        if not self.checked_presets:
            self.perform_smart_clip_matching(audio_path, show_popups=False)

        selected_presets = list(self.checked_presets)
        if not selected_presets:
            QMessageBox.warning(self, "錯誤", "請至少選取一個視覺模組！")
            return
            
        # Load preset details
        visuals_data = []
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        for vp in selected_presets:
            if vp == "modules_index":
                continue
            p_path = os.path.join(save_dir, f"{vp}.json")
            if os.path.exists(p_path):
                with open(p_path, "r", encoding="utf-8") as f:
                    preset_dict = json.load(f)
                    if not isinstance(preset_dict, dict) or 'code' not in preset_dict:
                        continue
                    if 'name' not in preset_dict:
                        preset_dict['name'] = preset_dict.get('title', vp)
                    visuals_data.append(preset_dict)

        # Resolution config
        res_str = self.res_select.currentText()
        if "4K" in res_str:
            w, h = 3840, 2160
        elif "1080p" in res_str:
            w, h = 1920, 1080
        else:
            w, h = 1280, 720
            
        fps = int(self.fps_select.currentText())
        trans_sec = self.trans_slider.value() / 10.0
        fx_prob = self.fx_prob_slider.value() / 100.0
        genre = self.genre_select.currentText()

        # Output video file path
        default_dir = ""
        if audio_path and not (audio_path.startswith("http://") or audio_path.startswith("https://")):
            audio_dir = os.path.dirname(audio_path)
            base = os.path.basename(audio_path)
            name, _ = os.path.splitext(base)
            if name:
                default_dir = os.path.join(audio_dir, f"{name}.mp4")
        else:
            default_dir = "YouTube_MV_Output.mp4"

        output_file, _ = safe_get_save_file_name(self, "儲存 4K MV 影片", default_dir, "MP4 Video (*.mp4)")
        if not output_file:
            return

        self.set_render_buttons_enabled(False)
        self.btn_cancel_render.setEnabled(True)
        self.render_aborted = False
        self.progress_bar.setValue(0)
        self.status_lbl.setText("正在分析音軌特徵與進行分鏡排程...")
        
        import time
        self.is_batch_rendering = False
        self.single_start_time = time.time()
        
        # Increment used_count for selected presets
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        video_id = os.path.basename(output_file) if output_file else "unknown_single.mp4"
        for vp in selected_presets:
            p_path = os.path.join(save_dir, f"{vp}.json")
            if os.path.exists(p_path):
                try:
                    with open(p_path, "r", encoding="utf-8") as f_in:
                        data = json.load(f_in)
                    used_in = data.get("used_in_videos", [])
                    if video_id not in used_in:
                        used_in.append(video_id)
                        data["used_in_videos"] = used_in
                        data["used_count"] = data.get("used_count", 0) + 1
                        with open(p_path, "w", encoding="utf-8") as f_out:
                            json.dump(data, f_out, indent=4, ensure_ascii=False)
                except Exception as e:
                    print(f"無法增加使用次數: {e}")
        # Refresh visual list to reflect new counts immediately
        self.cached_presets = None
        self.refresh_presets_list(clean_black=True, keep_page=True)
        
        # Collect post-FX type flags from checkboxes
        fx_flags = {
                'spatial_warping': self.fx_cb_distortion.isChecked(),
                'fluid_noise': self.fx_cb_fluid_noise.isChecked(),
                'temporal_feedback': self.fx_cb_feedback_dynamics.isChecked(),
                'color_spectral': self.fx_cb_color_aberration.isChecked(),
                'glow_illumination': self.fx_cb_glow_illumination.isChecked(),
                'retro_degradation': self.fx_cb_retro_degradation.isChecked(),
                'pixel_sort': self.fx_cb_pixel_sort.isChecked(),
                'kaleidoscope': self.fx_cb_kaleidoscope.isChecked(),
                'ambient_dsp': self.fx_cb_ambient_dsp.isChecked(),
                'adaptive_modulation': self.fx_cb_adaptive.isChecked(),
                # 新增全域與衍生特效
                'data_mosh': self.fx_cb_data_mosh.isChecked(),
                'sedimentation': self.fx_cb_sedimentation.isChecked(),
                'vector_scan': self.fx_cb_vector_scan.isChecked(),
                'temporal_fractal': self.fx_cb_temporal_fractal.isChecked(),
                'phase_slit': self.fx_cb_phase_slit.isChecked(),
                'centroid_glitch': self.fx_cb_centroid_glitch.isChecked(),
                'vignette_pulse': self.fx_cb_vignette_pulse.isChecked(),
                'tension_overlay': self.fx_cb_tension_overlay.isChecked(),
                'photosensitive_safe': self.fx_cb_photosensitive_safe.isChecked(),
                # 自訂擴充特效
                'thermal_vision': self.fx_cb_thermal_vision.isChecked(),
                'scanline_glitch': self.fx_cb_scanline_glitch.isChecked(),
                'frame_drop': self.fx_cb_frame_drop.isChecked(),
                'dynamic_mosaic': self.fx_cb_dynamic_mosaic.isChecked(),
                'pixel_art': self.fx_cb_pixel_art.isChecked(),
                'handheld_camera': self.fx_cb_handheld_camera.isChecked(),
                'stylized_fade': self.fx_cb_stylized_fade.isChecked(),
                'zoom_pulse': self.fx_cb_zoom_pulse.isChecked(),
                # 頂級全域後製特效矩陣擴充
                'film_burn': self.fx_cb_film_burn.isChecked(),
                'blueprint_edge': self.fx_cb_blueprint.isChecked(),
                'turing_pattern': self.fx_cb_turing.isChecked(),
                'point_cloud_depth': self.fx_cb_point_cloud.isChecked(),
                'vector_scope': self.fx_cb_vector_scope.isChecked(),
                'lowpass_muffle': self.fx_cb_lowpass_muffle.isChecked(),
                'infinity_tunnel': self.fx_cb_infinity_tunnel.isChecked(),
                'dolly_zoom': self.fx_cb_dolly_zoom.isChecked(),
                'hologram_glitch': self.fx_cb_hologram_glitch.isChecked(),
                'voronoi_shatter': self.fx_cb_voronoi_shatter.isChecked(),
                'thermal_infrared': self.fx_cb_thermal_infrared.isChecked(),
                'ascii_cyber_matrix': self.fx_cb_ascii_cyber_matrix.isChecked(),
                'chromatic_radial_zoom': self.fx_cb_chromatic_radial_zoom.isChecked(),
                'synthwave_grid_scan': self.fx_cb_synthwave_grid_scan.isChecked(),
                'bypass_downscale': self.native_4k_cb.isChecked()
            }
        
        # We will do audio analysis on worker thread, then perform frame captures on main loop
        self.render_mv_frame_by_frame(audio_path, genre, visuals_data, output_file, w, h, fps, trans_sec, fx_prob, fx_flags)

    def cancel_mv_rendering(self):
        self.render_aborted = True

    def render_mv_frame_by_frame(self, audio_path, genre, visuals_data, output_file, w, h, fps, trans_sec, fx_prob=1.0, fx_flags=None, show_popups=True, is_batch=False, used_themes=None):
        visuals_data = [v for v in (visuals_data or []) if isinstance(v, dict) and bool(v.get('code'))]
        if not visuals_data:
            self.log_to_console("❌ 無有效的視覺模組可供渲染 (選取的模組缺失代碼)", is_err=True)
            return False

        if fx_flags is None:
            fx_flags = {
                'spatial_warping': True,
                'fluid_noise': True,
                'temporal_feedback': True,
                'color_spectral': True,
                'glow_illumination': True,
                'retro_degradation': True,
                'pixel_sort': True,
                'kaleidoscope': True,
                'ambient_dsp': True,
                'adaptive_modulation': True,
                'data_mosh': True,
                'sedimentation': True,
                'vector_scan': True,
                'temporal_fractal': True,
                'phase_slit': True,
                'centroid_glitch': True,
                'vignette_pulse': False,
                'tension_overlay': False,
                'photosensitive_safe': True,
                # 自訂擴充特效
                'thermal_vision': True,
                'scanline_glitch': True,
                'frame_drop': True,
                'dynamic_mosaic': True,
                'pixel_art': True,
                'handheld_camera': True,
                'stylized_fade': True,
                'zoom_pulse': True,
                'film_burn': True,
                'blueprint_edge': True,
                'turing_pattern': True,
                'point_cloud_depth': True,
                'vector_scope': True,
                'lowpass_muffle': True,
                'infinity_tunnel': True,
                'dolly_zoom': True,
                'hologram_glitch': True,
                'voronoi_shatter': True,
                'thermal_infrared': True,
                'ascii_cyber_matrix': True,
                'chromatic_radial_zoom': True,
                'synthwave_grid_scan': True,
                'bypass_downscale': getattr(self, 'native_4k_cb', None).isChecked() if getattr(self, 'native_4k_cb', None) is not None else False
            }
        # Step 1: Analyze audio
        try:
            detector = AudioBeatDetector()
            analysis = detector.analyze(audio_path, genre)
            resolved_genre = analysis.get('genre', 'Generic').lower().strip()
        except Exception as e:
            if show_popups:
                QMessageBox.critical(self, "分析失敗", f"音軌分析失敗: {e}")
            self.log_to_console(f"音軌分析失敗: {e}", is_err=True)
            if not is_batch:
                self.set_render_buttons_enabled(True)
            return False

        bpm = analysis['bpm']
        beat_timestamps = analysis['beat_timestamps']
        duration = analysis['duration']
        storyboard = analysis['storyboard']
        filter_dynamics = analysis['filter_dynamics']
        total_frames = int(duration * fps)

        # Cap internal rendering resolution to 1080p to prevent GPU driver/VRAM crashes
        # and hardware thermal reboots on high-res output (e.g. 4K).
        render_w, render_h = w, h
        if (w > 1920 or h > 1080) and not self.native_4k_cb.isChecked():
            aspect_ratio = w / h
            if aspect_ratio >= 1.0:
                render_w = 1920
                render_h = int(1920 / aspect_ratio)
            else:
                render_h = 1080
                render_w = int(1080 * aspect_ratio)
            # Ensure even dimensions for FFmpeg
            render_w = (render_w // 2) * 2
            render_h = (render_h // 2) * 2
            self.log_to_console(f"⚠️ 偵測到超高輸出解析度 ({w}x{h})，內部渲染將降低至 1080p 級別 ({render_w}x{render_h})，並由 FFmpeg 二次升頻以防止 GPU/系統崩潰！")

        self.log_to_console(f"音訊分析完畢: {duration:.2f}s, {total_frames} 幀。")

        # Smart Dispatcher based on Visual Tags and Storyboard Weights
        def get_candidate_visuals_for_section(section_name, available_visuals, fallback_list):
            section_tags = {
                'Intro': ['intro', 'start', 'ambient', 'slow', 'calm'],
                'Verse': ['verse', 'main', 'theme'],
                'Build-up': ['buildup', 'build-up', 'transition', 'energy'],
                'Drop': ['drop', 'climax', 'fast', 'energetic', 'hard', 'heavy', '3d'],
                'Chorus': ['chorus', 'climax', 'fast', 'energetic', 'vocal', 'pop', 'main'],
                'Bridge': ['bridge', 'transition', 'slow', 'calm', 'contrast', 'melodic'],
                'Outro': ['outro', 'end', 'ambient', 'slow', 'fade']
            }
            target_weights = {
                'Intro': 30,
                'Verse': 50,
                'Build-up': 70,
                'Drop': 90,
                'Chorus': 80,
                'Bridge': 40,
                'Outro': 20
            }
            target_w = target_weights.get(section_name, 50)
            target_keywords = section_tags.get(section_name, [])
            candidates = []
            for vis in available_visuals:
                vis_tags = [t.lower().strip() for t in vis.get("tags", [])]
                matches = sum(1 for tk in target_keywords if tk in vis_tags)
                vis_w = vis.get("storyboard_weight", 50)
                energy_diff = abs(vis_w - target_w)
                score = matches * 10.0 - (energy_diff / 1.5)
                if vis.get("is_starred", False):
                    score += 100.0
                
                # Keep if it matches keywords OR is close in weight (energy_diff <= 30) OR is starred
                if matches > 0 or energy_diff <= 30 or vis.get("is_starred", False):
                    candidates.append((score, vis))
            
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return [c[1] for c in candidates]
            return fallback_list

        sorted_visuals = sorted(visuals_data, key=lambda x: x.get('storyboard_weight', 50))
        
        # 建立每個 section name 的候選列表
        candidates_by_sec = {}
        for sec in ['Intro', 'Verse', 'Build-up', 'Drop', 'Chorus', 'Bridge', 'Outro']:
            # fallback_list 直接使用 sorted_visuals，確保即使沒有 tags 符合，也能從所有勾選模組中輪巡
            candidates_by_sec[sec] = get_candidate_visuals_for_section(sec, visuals_data, sorted_visuals)
            self.log_to_console(f"分鏡「{sec}」候選視覺模組列表: {[v['name'] for v in candidates_by_sec[sec]]}")

        # 子分鏡輪流指派（基於曲目哈希設定初始偏移，防止每首歌總是從第0個候選模組開始指派）
        import hashlib
        audio_seed = int(hashlib.md5(audio_path.encode('utf-8')).hexdigest(), 16)
        sec_counters = {
            sec: (audio_seed + idx * 7)
            for idx, sec in enumerate(['Intro', 'Verse', 'Build-up', 'Drop', 'Chorus', 'Bridge', 'Outro'])
        }
        
        # 🎬 檢查是否已具備 AI 導演劇本 (LLM Director Script)
        llm_shot_list = getattr(self, "current_director_script", {}).get("shot_list", [])
        modules_by_key = {m.get("_filename_key") or m.get("name"): m for m in visuals_data}
        modules_by_name = {m.get("name"): m for m in visuals_data}

        last_assigned_name = None
        for sec_idx, sec_data in enumerate(storyboard):
            sec_name = sec_data['section']
            assigned_vis = None
            fit_mode = 'fill'
            fx_intensity = 0.6

            # 優先採用 LLM 導演指定的模組與構圖
            if sec_idx < len(llm_shot_list):
                shot_info = llm_shot_list[sec_idx]
                mod_id = shot_info.get("assigned_module_id")
                assigned_vis = modules_by_key.get(mod_id) or modules_by_name.get(mod_id)
                fit_mode = shot_info.get("framing_mode", "fill")
                fx_intensity = shot_info.get("target_fx_intensity", 0.6)

            if not assigned_vis:
                candidates = candidates_by_sec.get(sec_name, sorted_visuals) or sorted_visuals
                idx = sec_counters[sec_name] % len(candidates)
                assigned_vis = candidates[idx]
                if len(candidates) > 1 and assigned_vis.get('name') == last_assigned_name:
                    idx = (idx + 1) % len(candidates)
                    assigned_vis = candidates[idx]
                sec_counters[sec_name] += 1
                
                import random
                if sec_name in ['Intro', 'Bridge'] and random.random() < 0.25:
                    fit_mode = 'contain'
                else:
                    fit_mode = 'fill'

            sec_data['fullscreen_fit_mode'] = fit_mode
            sec_data['assigned_visual'] = assigned_vis
            sec_data['director_fx_intensity'] = fx_intensity
            last_assigned_name = assigned_vis.get('name')
            
            self.log_to_console(f"子分鏡區段 [{sec_data['start']:.2f}s - {sec_data['end']:.2f}s] ({sec_name}) 🎬 導演指派: {assigned_vis['name']} [構圖: {fit_mode.upper()} | 後製強度: {int(fx_intensity*100)}%]")


        times = filter_dynamics.get('times', [])
        lowpass = filter_dynamics.get('lowpass', [])
        highpass = filter_dynamics.get('highpass', [])
        mid_ratio = filter_dynamics.get('mid_ratio', [])
        fd_silence_fade = filter_dynamics.get('silence_fade', [])
        fd_percussive = filter_dynamics.get('percussive', [])
        fd_ethereal = filter_dynamics.get('ethereal_index', [])
        fd_sub_bass = filter_dynamics.get('sub_bass_ratio', [])
        fd_roughness = filter_dynamics.get('roughness', [])
        fd_bass_ratio = filter_dynamics.get('bass_ratio', [])
        fd_centroid_norm = filter_dynamics.get('centroid_norm', [])
        fd_stereo_width = filter_dynamics.get('stereo_width', [])
        
        # New actual energy keys
        fd_bass_energy = filter_dynamics.get('bass_energy', [])
        fd_mid_energy = filter_dynamics.get('mid_energy', [])
        fd_high_energy = filter_dynamics.get('high_energy', [])
        fd_total_energy = filter_dynamics.get('total_energy', [])

        # Chord parameters
        fd_chord_name = filter_dynamics.get('chord_name', [])
        fd_chord_hue = filter_dynamics.get('chord_hue', [])
        fd_chord_saturation = filter_dynamics.get('chord_saturation', [])
        fd_chord_brightness = filter_dynamics.get('chord_brightness', [])
        fd_chord_color_hex = filter_dynamics.get('chord_color_hex', [])

        import bisect as _bisect_mod

        def get_telemetry_at_time(t):
            """Return (a_low, a_mid, a_high) tuple for backward compatibility."""
            if not times:
                return 0.0, 0.0, 0.0
            idx = _bisect_mod.bisect_right(times, t) - 1
            idx = max(0, min(idx, len(times) - 1))
            
            # Use actual energies if available, otherwise fallback to filter intensities
            if fd_bass_energy and fd_high_energy:
                a_low = fd_bass_energy[idx] if idx < len(fd_bass_energy) else 0.0
                a_mid = fd_mid_energy[idx] if idx < len(fd_mid_energy) else 0.0
                a_high = fd_high_energy[idx] if idx < len(fd_high_energy) else 0.0
                return min(1.0, a_low * 1.5), min(1.0, a_mid * 1.5), min(1.0, a_high * 1.5)
            else:
                return min(1.0, lowpass[idx] * 2.0), min(1.0, mid_ratio[idx] * 2.0), min(1.0, highpass[idx] * 2.0)

        def get_full_telemetry_at_time(t):
            """Return full audio feature dict for post-processing pipeline."""
            if not times:
                return {'silence_fade': 0.0, 'percussive': 0.0, 'ethereal': 0.0,
                        'sub_bass': 0.0, 'roughness': 0.0, 'bass_ratio': 0.0,
                        'chord_name': 'N.C.', 'chord_hue': 0.0, 'chord_saturation': 0.0,
                        'chord_brightness': 0.1, 'chord_color_hex': '#0a0a0c',
                        'centroid': 0.2, 'stereo_width': 0.5, 'bpm': bpm}
            idx = _bisect_mod.bisect_right(times, t) - 1
            idx = max(0, min(idx, len(times) - 1))
            return {
                'silence_fade': fd_silence_fade[idx] if idx < len(fd_silence_fade) else 0.0,
                'percussive': fd_percussive[idx] if idx < len(fd_percussive) else 0.0,
                'ethereal': fd_ethereal[idx] if idx < len(fd_ethereal) else 0.0,
                'sub_bass': fd_sub_bass[idx] if idx < len(fd_sub_bass) else 0.0,
                'roughness': fd_roughness[idx] if idx < len(fd_roughness) else 0.0,
                'bass_ratio': fd_bass_ratio[idx] if idx < len(fd_bass_ratio) else 0.0,
                'chord_name': fd_chord_name[idx] if idx < len(fd_chord_name) else 'N.C.',
                'chord_hue': fd_chord_hue[idx] if idx < len(fd_chord_hue) else 0.0,
                'chord_saturation': fd_chord_saturation[idx] if idx < len(fd_chord_saturation) else 0.0,
                'chord_brightness': fd_chord_brightness[idx] if idx < len(fd_chord_brightness) else 0.1,
                'chord_color_hex': fd_chord_color_hex[idx] if idx < len(fd_chord_color_hex) else '#0a0a0c',
                'centroid': fd_centroid_norm[idx] if idx < len(fd_centroid_norm) else 0.2,
                'stereo_width': fd_stereo_width[idx] if idx < len(fd_stereo_width) else 0.5,
                'bpm': bpm
            }

        def get_section_at_time(t):
            for sec in storyboard:
                if sec['start'] <= t <= sec['end']:
                    return sec, sec['section']
            return storyboard[0], 'Verse'

        # === Post-processing pipeline (ported from ui.py, optimized) ===
        from PIL import ImageEnhance, ImageChops, ImageDraw  # Fix 3: Import once outside function
        import numpy as np
        import gc
        import platform
        import resource as _resource_mod  # macOS memory monitoring

        # Fix 3: Pre-allocate reusable images (use render_w, render_h to match internal rendering size)
        _flash_white = Image.new('RGBA', (render_w, render_h), (255, 255, 255, 255))
        _flash_black = Image.new('RGBA', (render_w, render_h), (0, 0, 0, 255))
        _black_img = Image.new('RGBA', (render_w, render_h), (0, 0, 0, 255))
        _post_fx_enabled = [True]  # Mutable for memory-based auto-disable
        _grain_frame_counter = [0]  # For grain frame skipping
        _cached_grain_img = [None]  # Cache grain between frames
        _fx_active_on_this_beat = [True]  # State variable for beat-locked probability gating

        # === Post-processing pipeline using new shared PostProcessor ===
        from post_processor import PostProcessor, apply_advanced_transition
        _post_processor = PostProcessor(seed_string=audio_path, genre=resolved_genre, used_themes=used_themes)
        self._last_post_processor = _post_processor  # 暴露給批次迴圈以追蹤已使用主題
        _post_fx_enabled = [True]  # Mutable for memory-based auto-disable

        # Fix 6: Crash logging — write to file alongside output video
        _render_log_path = output_file.rsplit('.', 1)[0] + '_render.log'
        _file_handler = logging.FileHandler(_render_log_path, encoding='utf-8')
        _file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.addHandler(_file_handler)
        logger.info(f"=== 渲染開始 ===")
        logger.info(f"輸出: {output_file}")
        logger.info(f"解析度: {w}x{h}@{fps}fps, 總幀數={total_frames}, BPM={bpm}")
        logger.info(f"系統: {platform.system()} {platform.machine()}")
        logger.info(f"視覺模組: {[v['name'] for v in visuals_data]}")
        logger.info(f"分鏡數: {len(storyboard)}")

        def apply_post_processing(pil_img, t, is_beat, beat_energy, audio_feats, section_name='Verse', section_progress=0.0):
            """Apply VJ-grade post-processing effects chain to a rendered frame."""
            if not _post_fx_enabled[0]:
                return pil_img  # Fix 7: Skip if disabled by memory watchdog

            # Determine post-FX intensity with dynamic song arc modulation
            base_intensity = 0.5
            try:
                base_intensity = active_vis.get('post_fx_intensity', 50) / 100.0
            except Exception:
                base_intensity = self.fx_slider.value() / 100.0

            # Progressive song timeline arc factor (0.7x at start -> 1.15x at end)
            song_progress_ratio = max(0.0, min(1.0, t / max(1.0, duration)))
            timeline_arc = 0.70 + 0.45 * song_progress_ratio

            # Section-based intensity multiplier for visual contrast (Boosted for Hard Techno)
            sec_weights = {
                'Intro': 0.40,
                'Verse': 0.70,
                'Build-up': 1.40,
                'Drop': 2.00,
                'Chorus': 1.60,
                'Bridge': 0.75,
                'Outro': 0.35
            }
            sec_mult = sec_weights.get(section_name, 0.70)
            effective_intensity = max(0.1, min(1.5, base_intensity * timeline_arc * sec_mult))

            adaptive = fx_flags.get('adaptive_modulation', True)
            
            return _post_processor.process(
                pil_img, t, is_beat, beat_energy, audio_feats, fx_flags,
                fx_prob=fx_prob, fx_intensity=effective_intensity, adaptive_modulation=adaptive,
                section_name=section_name, section_progress=section_progress, genre=resolved_genre
            )

        # Helper to construct views inside a clipper parent to resolve CoreAnimation flashing on macOS
        _current_clipper = [None]
        _current_viewA = [None]
        _current_viewB = [None]

        def init_offscreen_views():
            # Clean up old ones if they exist
            if _current_viewA[0] or _current_viewB[0]:
                try:
                    for v in [_current_viewA[0], _current_viewB[0]]:
                        if v:
                            v.setParent(None)
                            page = v.page()
                            v.setPage(None)
                            if page:
                                page.deleteLater()
                            v.close()
                            v.deleteLater()
                except:
                    pass
                try:
                    if _current_clipper[0]:
                        _current_clipper[0].setParent(None)
                        _current_clipper[0].close()
                        _current_clipper[0].deleteLater()
                except:
                    pass

            # Create clipper widget to act as a hardware-compositing boundary
            # Use Tool + WindowTransparentForInput flags to prevent it from overlaying or blocking the main UI window
            clipper = QWidget(self)
            clipper.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowTransparentForInput)
            clipper.setGeometry(0, 0, render_w, render_h)
            clipper.setWindowOpacity(0.01)
            clipper.show()
            clipper.lower()
            _current_clipper[0] = clipper

            # Force 1x scale factor to eliminate Retina resize overhead
            _orig_scale_factor = os.environ.get('QT_SCALE_FACTOR', None)
            os.environ['QT_SCALE_FACTOR'] = '1'

            viewA = QWebEngineView(clipper)
            viewB = QWebEngineView(clipper)
            
            for v in [viewA, viewB]:
                settings = v.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
                
                v.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowTransparentForInput)
                v.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                v.setStyleSheet("background: black;")
                v.page().setBackgroundColor(QColor(0, 0, 0, 255))
                # Set coordinates to (0, 0) relative to clipper to prevent macOS CALayer overlay flashing bugs
                v.setGeometry(0, 0, render_w, render_h)
                v.resize(render_w, render_h)
                self.setup_web_sandbox(v)
            
            viewA.show()
            viewA.raise_()
            viewB.hide()

            # Restore original scale factor
            if _orig_scale_factor is not None:
                os.environ['QT_SCALE_FACTOR'] = _orig_scale_factor
            else:
                os.environ.pop('QT_SCALE_FACTOR', None)

            _current_viewA[0] = viewA
            _current_viewB[0] = viewB

        # Initialize first views
        init_offscreen_views()
        viewA = _current_viewA[0]
        viewB = _current_viewB[0]

        # 模組專屬環形影格快取池 (Per-Module Ring Buffer Cache)
        class ModuleFrameCacheManager:
            def __init__(self, max_frames_per_module=15, max_total_modules=30):
                from collections import deque
                self.max_frames_per_module = max_frames_per_module
                self.max_total_modules = max_total_modules
                self.caches = {}
                self.lru_order = []

            def add_frame(self, module_name: str, pil_img):
                from collections import deque
                if not module_name: return
                if module_name not in self.caches:
                    if len(self.caches) >= self.max_total_modules and self.lru_order:
                        oldest = self.lru_order.pop(0)
                        self.caches.pop(oldest, None)
                    self.caches[module_name] = deque(maxlen=self.max_frames_per_module)
                    self.lru_order.append(module_name)
                else:
                    if module_name in self.lru_order:
                        self.lru_order.remove(module_name)
                    self.lru_order.append(module_name)
                self.caches[module_name].append(pil_img.copy())

            def get_latest_frame(self, module_name: str):
                if module_name in self.caches and len(self.caches[module_name]) > 0:
                    return self.caches[module_name][-1].copy()
                return None

        module_cache_mgr = ModuleFrameCacheManager()
        from post_processor import SongProceduralFluidEngine
        song_fluid_engine = SongProceduralFluidEngine(audio_path)

        def apply_graceful_fallback(pil_cached_img, t_val, beat_e, a_low_val, chord_c):
            """
            Phase 2: 對保底影格注入有機生命力 (動態微光呼吸 + 拍點脈衝微縮放)，防止畫面死鎖與動態靜止。
            """
            if pil_cached_img is None:
                return pil_cached_img
            try:
                import math
                from PIL import ImageEnhance
                # 1. 亮度微光呼吸 (隨時間與低頻能量自然正弦起伏)
                breath_alpha = 0.94 + 0.12 * math.sin(t_val * 4.0) + (float(a_low_val) * 0.10)
                enhanced = ImageEnhance.Brightness(pil_cached_img).enhance(max(0.75, min(1.25, breath_alpha)))
                
                # 2. 拍點脈衝微縮放 (Beat Pulse Micro-zoom 1.00 ~ 1.025x)
                if beat_e > 0.35:
                    w_img, h_img = enhanced.size
                    zoom_factor = 1.0 + min(0.025, float(beat_e) * 0.02)
                    nw, nh = int(w_img * zoom_factor), int(h_img * zoom_factor)
                    scaled = enhanced.resize((nw, nh), Image.Resampling.BILINEAR)
                    left_crop = (nw - w_img) // 2
                    top_crop = (nh - h_img) // 2
                    enhanced = scaled.crop((left_crop, top_crop, left_crop + w_img, top_crop + h_img))
                return enhanced
            except Exception:
                return pil_cached_img

        # Load states
        loadedA = None
        loadedB = None
        consecutive_black_frames = 0
        module_accumulated_time = {}

        def get_html_content(code, custom_css="", custom_html="", inline_assets=None, scaling_mode="auto"):
            return self.get_html_content(code, custom_css, custom_html, inline_assets, scaling_mode=scaling_mode, for_rendering=True)

        def run_js_safely(view, js_code, is_first_frame=False):
            attempts = 5 if is_first_frame else 3
            timeout_ms = 600 if is_first_frame else 120
            for attempt in range(attempts):
                loop = QEventLoop()
                result = {"value": None}
                
                def handle_result(r):
                    result["value"] = r
                    try:
                        loop.quit()
                    except RuntimeError:
                        pass
                    
                check_js = f"""
                (function() {{
                    try {{
                        {js_code};
                    }} catch(e) {{}}
                    try {{
                        if (typeof redraw === 'function') redraw();
                        else if (typeof window.redraw === 'function') window.redraw();
                        else if (window._p5Instance && typeof window._p5Instance.redraw === 'function') window._p5Instance.redraw();
                        else if (typeof draw === 'function') draw();
                        else if (typeof window.draw === 'function') window.draw();
                    }} catch(e) {{}}
                    
                    let canvases = document.querySelectorAll('canvas');
                    let cnv = null;
                    for (let i = canvases.length - 1; i >= 0; i--) {{
                        let c = canvases[i];
                        if (c && c.width > 0 && c.height > 0) {{
                            cnv = c;
                            break;
                        }}
                    }}
                    if (cnv) {{
                        return cnv.toDataURL('image/jpeg', 0.95);
                    }}
                    return "no_canvas";
                }})();
                """
                
                # Safety timeout to prevent permanent event loop hangs
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                timer.start(timeout_ms)
                
                view.page().runJavaScript(check_js, handle_result)
                loop.exec()
                timer.stop()
                
                val = result["value"]
                if val and isinstance(val, str) and val.startswith("data:image/"):
                    return val
                
                QApplication.processEvents()
            return None

        # --- Setup FFMPEG Pipe Stream (Optimized, Zero-Disk-I/O) ---
        self.status_lbl.setText("正在啟動 FFmpeg 即時編碼管道...")
        
        ffmpeg_bin = "ffmpeg"
        for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
            if os.path.exists(p):
                ffmpeg_bin = p
                break

        ffmpeg_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",  # B3: Accept RGBA directly, avoid Python RGBA→RGB conversion
            "-s", f"{render_w}x{render_h}",  # Input is the internal rendering resolution (max 1080p)
            "-r", str(fps),
            "-i", "-", # Read from stdin
        ]

        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend(["-i", audio_path])

        # macOS / AMD Radeon GPU VideoToolbox Hardware Acceleration Encoder
        import platform
        if platform.system() == 'Darwin':
            ffmpeg_cmd.extend([
                "-c:v", "h264_videotoolbox",  # VideoToolbox Hardware GPU encoder
                "-pix_fmt", "nv12",           # Force CPU-to-GPU format conversion
                "-b:v", "60M" if w > 1920 else "25M",  # High bitrate (60M for 4K, 25M for 1080p) for ultra-sharp quality
                "-allow_sw", "1"
            ])
            if render_w != w or render_h != h:
                ffmpeg_cmd.extend(["-vf", f"scale={w}:{h}:flags=lanczos,format=nv12"])
            else:
                ffmpeg_cmd.extend(["-vf", "format=nv12"])
        else:
            ffmpeg_cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
            ])
            if render_w != w or render_h != h:
                ffmpeg_cmd.extend(["-vf", f"scale={w}:{h}:flags=lanczos"])
            ffmpeg_cmd.extend([
                "-preset", "medium",
                "-crf", "16"
            ])

        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            ffmpeg_cmd.extend(["-an"])

        ffmpeg_cmd.append(output_file)

        try:
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,  # Fix: Prevent pipe buffer deadlock if FFmpeg writes to stdout
                stderr=subprocess.PIPE,
                bufsize=8388608  # B3: 8MB buffer for efficient I/O
            )
        except Exception as e:
            if show_popups:
                QMessageBox.critical(self, "錯誤", f"無法啟動 FFmpeg 進行編碼，請確保系統已安裝 FFmpeg。\n詳細錯誤: {e}")
            self.log_to_console(f"無法啟動 FFmpeg: {e}", is_err=True)
            if not is_batch:
                self.set_render_buttons_enabled(True)
                self.btn_cancel_render.setEnabled(False)
            try:
                viewA.close()
                viewB.close()
            except:
                pass
            return False

        # Read FFmpeg stderr on a separate thread to collect logs/errors
        ffmpeg_stderr_accumulator = []
        import threading
        import queue as _queue_mod
        def read_ffmpeg_stderr():
            try:
                while True:
                    line = ffmpeg_process.stderr.readline()
                    if not line:
                        break
                    try:
                        line_str = line.decode('utf-8', errors='ignore')
                    except Exception:
                        line_str = str(line)
                    ffmpeg_stderr_accumulator.append(line_str)
                    # Fix 8: Keep only last 100 lines to prevent unbounded growth
                    if len(ffmpeg_stderr_accumulator) > 100:
                        del ffmpeg_stderr_accumulator[:50]
            except:
                pass

        ffmpeg_stderr_thread = threading.Thread(target=read_ffmpeg_stderr, daemon=True)
        ffmpeg_stderr_thread.start()

        # Fix 1: Background FFmpeg writer thread with bounded queue
        _frame_queue = _queue_mod.Queue(maxsize=4)  # Buffer up to 4 frames
        _writer_error = [None]  # Capture write errors from background thread

        def _ffmpeg_writer_thread_fn():
            """Background thread: reads frames from queue, writes to FFmpeg stdin."""
            while True:
                item = _frame_queue.get()
                if item is None:  # Sentinel value: render is complete
                    break
                try:
                    ffmpeg_process.stdin.write(item)
                except Exception as e:
                    _writer_error[0] = str(e)
                    break
                finally:
                    _frame_queue.task_done()

        _writer_thread = threading.Thread(target=_ffmpeg_writer_thread_fn, daemon=True)
        _writer_thread.start()

        # Load raw audio samples for Strange Attractor rendering
        audio_samples_raw = None
        sr_raw = 22050
        if audio_path and os.path.exists(audio_path):
            try:
                import librosa
                import numpy as np
                audio_samples_raw, sr_raw = librosa.load(audio_path, sr=sr_raw)
                self.log_to_console(f"已成功加載音訊時域信號進行奇異吸引子繪製：{audio_samples_raw.shape[0]} 採樣點")
            except Exception as e:
                logger.error(f"Failed to load audio samples for strange attractor: {e}")

        # Frame Loop using QTimer / Single-threaded Event Loop
        self.progress_bar.setMaximum(total_frames)
        
        loop = QEventLoop()
        beat_energy = 0.0

        # === Beat-driven visual rotation system ===
        # Determines how many beats between visual module switches within a section
        def get_rotation_beat_interval(sec_name, energy, genre_str):
            """Return how many beats to wait before rotating to next visual module."""
            base_intervals = {
                'Drop': (2, 4),
                'Chorus': (2, 4),
                'Build-up': (4, 8),
                'Bridge': (12, 24),
                'Verse': (8, 16),
                'Intro': (16, 32),
                'Outro': (16, 32)
            }
            lo, hi = base_intervals.get(sec_name, (8, 16))
            # Genre adjustments
            if genre_str in ('lo-fi', 'jazz', 'ambient'):
                lo = int(lo * 3.0)
                hi = int(hi * 3.0)
            elif genre_str in ('dnb', 'hard_techno', 'edm'):
                lo = max(2, int(lo * 0.75))
                hi = max(4, int(hi * 0.75))
            # Energy scaling
            if energy > 0.6:
                interval = lo
            elif energy < 0.25:
                interval = hi
            else:
                ratio = (energy - 0.25) / 0.35
                interval = int(hi - ratio * (hi - lo))
            return max(2, interval)

        import random as _rot_random
        rotation_beat_counter = 0
        rotation_beats_until_switch = get_rotation_beat_interval('Verse', 0.5, resolved_genre)
        rotation_visual_idx = {}  # per-section rotation index
        current_rotation_vis = None  # currently active rotated visual
        prev_rotation_vis = None  # previous visual for cross-fade
        rotation_trans_start = -1.0  # timestamp when rotation transition started
        rotation_trans_dur = trans_sec  # use same transition duration as section transitions
        # 讀取使用者選擇的 CPU 運作模式（0=控溫, 1=全力運作）
        _cpu_full_power = self.cpu_mode_select.currentIndex() == 1
        render_delay = 0.001 if _cpu_full_power else 0.002
        if _cpu_full_power:
            self.log_to_console("🔥 CPU 全力運作模式：已跳過溫控保護，以最大速度渲染。")
        else:
            self.log_to_console("🌡️ CPU 控溫模式：啟用過熱保護機制，每 100 幀自動偵測系統溫度。")
        
        # Track start time for current song render
        song_start_time = time.time()

        def format_time_hms(seconds):
            if seconds > 3600:
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                return f"{h}小時{m}分{s}秒"
            else:
                m = int(seconds // 60)
                s = int(seconds % 60)
                return f"{m}分{s}秒"

        def update_render_status_label(frame_idx):
            import time
            p_curr = (frame_idx + 1) / total_frames
            percent = int(p_curr * 100)
            now = time.time()
            
            # 1. 計算本首歌曲剩餘時間
            song_elapsed = now - song_start_time
            song_eta_str = ""
            speed_str = ""
            if p_curr > 0.01 and song_elapsed > 1.5:
                song_eta_sec = ((1.0 - p_curr) / p_curr) * song_elapsed
                song_eta_str = f"本首剩餘: {format_time_hms(song_eta_sec)}"
                fps_rate = (frame_idx + 1) / song_elapsed
                speed_str = f" ({fps_rate:.1f} 幀/秒)"

            if getattr(self, 'is_batch_rendering', False):
                batch_idx = getattr(self, 'batch_current_idx', 0)
                total_songs = getattr(self, 'batch_total_songs', 1)
                batch_start = getattr(self, 'batch_start_time', None)
                
                total_eta_str = ""
                if batch_start is not None:
                    batch_elapsed = now - batch_start
                    completed_songs_equiv = batch_idx + p_curr
                    if completed_songs_equiv > 0.01 and batch_elapsed > 2.0:
                        total_eta_sec = ((total_songs - completed_songs_equiv) / completed_songs_equiv) * batch_elapsed
                        total_eta_str = f"全部剩餘: {format_time_hms(total_eta_sec)}"
                
                eta_combined = " | ".join([s for s in [song_eta_str, total_eta_str] if s])
                if eta_combined:
                    eta_combined = f" | {eta_combined}"
                
                song_name = os.path.basename(audio_path)
                status_text = (
                    f"批次渲染 ({batch_idx + 1}/{total_songs}) - {song_name} | "
                    f"進度: {percent}% ({frame_idx + 1}/{total_frames} 幀){speed_str}{eta_combined}"
                )
            else:
                eta_combined = f" | {song_eta_str}" if song_eta_str else ""
                status_text = f"影片實時串流編碼中: {percent}% ({frame_idx + 1}/{total_frames} 幀){speed_str}{eta_combined}"
                
            self.status_lbl.setText(status_text)

        just_loaded_a = True
        just_loaded_b = True
        
        for i in range(total_frames):
            if i % 5 == 0:  # Fix 4: Process events every 5 frames (was 10)
                QApplication.processEvents()

            # Recycle WebEngine Views to free V8 JS engine and GPU memory
            # Only recycle if frame count is a multiple of 1000 and memory is > 3500MB
            # This avoids expensive process recreation lag spikes when memory is stable.
            if i > 0 and i % 1000 == 0:
                try:
                    import psutil as _psutil_mod
                    process = _psutil_mod.Process()
                    mem_bytes = process.memory_info().rss
                    for child in process.children(recursive=True):
                        try:
                            mem_bytes += child.memory_info().rss
                        except (_psutil_mod.NoSuchProcess, _psutil_mod.AccessDenied):
                            pass
                    mem_mb = mem_bytes / (1024 * 1024)
                except Exception:
                    mem_mb = 0
                
                # Raise threshold to 12GB to avoid constantly destroying WebGL contexts every 1000 frames
                if mem_mb > 12000:
                    self.log_to_console(f"♻️ 記憶體超出閥值 ({mem_mb:.0f}MB > 12000MB)，啟動 WebEngine 視圖深度回收...")
                    logger.info(f"Memory threshold exceeded ({mem_mb:.0f}MB). Re-creating QWebEngineView resources at frame {i}")
                    init_offscreen_views()
                    viewA = _current_viewA[0]
                    viewB = _current_viewB[0]
                    loadedA = None
                    loadedB = None
                    just_loaded_a = True
                    just_loaded_b = True
                    gc.collect()
                elif mem_mb > 6000:
                    # Light GC without destroying GPU WebGL Context
                    gc.collect()
            
            if self.render_aborted:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("中斷渲染任務")
                msg_box.setText("您已手動中斷渲染，請選擇處理方式：\n\n"
                                "【是 (Yes)】：就當前已渲染的進度進行合併並匯出影片\n"
                                "【否 (No)】：直接中斷，不保存任何內容\n"
                                "【取消 (Cancel)】：返回並繼續渲染影片")
                
                yes_btn = msg_box.addButton("是 (Yes)", QMessageBox.ButtonRole.YesRole)
                no_btn = msg_box.addButton("否 (No)", QMessageBox.ButtonRole.NoRole)
                cancel_btn = msg_box.addButton("取消 (Cancel)", QMessageBox.ButtonRole.RejectRole)
                
                msg_box.setDefaultButton(cancel_btn)
                msg_box.exec()
                
                clicked = msg_box.clickedButton()
                if clicked == cancel_btn:
                    self.render_aborted = False
                elif clicked == yes_btn:
                    if i == 0:
                        if show_popups:
                            QMessageBox.warning(self, "中斷", "尚未渲染任何影格，無法進行合併。")
                        self.log_to_console("使用者手動中止渲染。")
                        self.status_lbl.setText("渲染已中止。")
                        try:
                            ffmpeg_process.kill()
                        except:
                            pass
                        if not is_batch:
                            self.set_render_buttons_enabled(True)
                            self.btn_cancel_render.setEnabled(False)
                        try:
                            viewA.close()
                            viewB.close()
                        except:
                            pass
                        return False
                    
                    self.log_to_console(f"使用者手動中止渲染，將就當前進度強制合成前 {i} 影格...")
                    break
                else:
                    self.log_to_console("使用者手動中斷渲染，不保存並清理資源。")
                    self.status_lbl.setText("渲染已中斷並捨棄。")
                    try:
                        ffmpeg_process.kill()
                    except:
                        pass
                    if not is_batch:
                        self.set_render_buttons_enabled(True)
                        self.btn_cancel_render.setEnabled(False)
                    try:
                        viewA.close()
                        viewB.close()
                    except:
                        pass
                    return False
            
            t = i * (1.0 / fps)
            audio_feats = get_full_telemetry_at_time(t)
            perc_env = audio_feats.get('percussive', 0.0)
            bass_env = audio_feats.get('bass_energy', 0.0)
            
            # Beat detection (Fix 5: bisect instead of linear scan + Drum Percussive Coupling)
            is_beat = False
            t_prev = (i - 1) * (1.0 / fps) if i > 0 else 0.0
            if beat_timestamps:
                bt_idx = _bisect_mod.bisect_right(beat_timestamps, t_prev)
                has_beat = bt_idx < len(beat_timestamps) and beat_timestamps[bt_idx] <= t
                if has_beat:
                    is_beat = True
                    beat_energy = 1.0
                else:
                    # 融合打擊樂瞬態包絡，讓大鼓/小鼓爆發時動態抬升 beat_energy
                    beat_energy = max(0.0, beat_energy * 0.90, perc_env * 0.85, bass_env * 0.70)
            
            a_low, a_mid, a_high = get_telemetry_at_time(t)
            sec_data, sec_name = get_section_at_time(t)
            
            # Calculate segment progress
            sec_progress = 0.0
            if sec_data:
                sec_duration = sec_data.get('end', t) - sec_data.get('start', t)
                if sec_duration > 0.01:
                    sec_progress = (t - sec_data['start']) / sec_duration
                    sec_progress = max(0.0, min(1.0, sec_progress))
            
            # Calculate current music energy using total_energy key if available
            if fd_total_energy:
                idx = _bisect_mod.bisect_right(times, t) - 1
                idx = max(0, min(idx, len(times) - 1))
                music_energy = fd_total_energy[idx] if idx < len(fd_total_energy) else 0.0
            else:
                music_energy = (a_low + a_mid + a_high) / 3.0
            
            def get_energy_adapted_visual(base_vis, energy, sec):
                if energy > 0.6 and sec in ['Verse', 'Build-up', 'Bridge']:
                    climax_candidates = candidates_by_sec.get('Drop', []) or candidates_by_sec.get('Chorus', [])
                    if climax_candidates:
                        return climax_candidates[0]
                elif energy < 0.25 and sec in ['Verse', 'Drop', 'Chorus']:
                    ambient_candidates = candidates_by_sec.get('Intro', [])
                    if ambient_candidates:
                        return ambient_candidates[0]
                return base_vis

            # === Beat-driven visual rotation within sections ===
            if is_beat:
                rotation_beat_counter += 1
                
                # A7: Subdivision system — trigger rapid switches on high-energy beats & Hihat rolls
                if resolved_genre not in ('lo-fi', 'ambient', 'jazz'):
                    subdiv_audio = get_full_telemetry_at_time(t)
                    subdiv_bass = subdiv_audio.get('bass_ratio', 0.0)
                    subdiv_perc = subdiv_audio.get('percussive', 0.0)
                    hihat_dens = subdiv_audio.get('hihat_density', 0.0)
                    hihat_trig = subdiv_audio.get('hihat_trigger', False)
                    
                    # Rapid rotation on 16th note Hihat rolls / high percussion density
                    if hihat_dens > 0.6 or hihat_trig or subdiv_bass > 0.6 or subdiv_perc > 0.5:
                        # Force rapid rotation interval during intense Hihat bursts
                        if rotation_beats_until_switch > 1:
                            rotation_beats_until_switch = 1
                    elif hihat_dens > 0.3 or subdiv_bass > 0.3 or subdiv_perc > 0.35:
                        # 8th notes: force rotation every 2 beats
                        if rotation_beats_until_switch > 2:
                            rotation_beats_until_switch = 2
            
            # 🔮 AOT 背景視圖預熱 (Offscreen AOT Pre-warming)
            # 模式 1: 跨段落邊界 AOT 預熱 (Cross-Section Boundary Preload, 提前 2.5 秒)
            preload_lead_sec = 2.5
            next_sec_data, next_sec_name = get_section_at_time(t + preload_lead_sec)
            if next_sec_name != sec_name and not is_transitioning:
                next_assigned_vis = next_sec_data.get('assigned_visual', sorted_visuals[0]) if next_sec_data else sorted_visuals[0]
                target_aot_vis = get_energy_adapted_visual(next_assigned_vis, music_energy, next_sec_name)
                if loadedB != target_aot_vis['name']:
                    viewB.setHtml(get_html_content(
                        target_aot_vis.get('code', ''),
                        custom_css=target_aot_vis.get('custom_css', ''),
                        custom_html=target_aot_vis.get('custom_html', ''),
                        inline_assets=target_aot_vis.get('inline_assets', {}),
                        scaling_mode=target_aot_vis.get('scaling_mode', 'auto')
                    ), get_local_base_url())
                    loadedB = target_aot_vis['name']
                    just_loaded_b = True
            
            # 模式 2: 同段落拍點輪替 AOT 預熱 (Within-Section Rotation Preload, 提前 2 拍)
            elif is_beat and (rotation_beats_until_switch - rotation_beat_counter) <= 2:
                candidates_aot = candidates_by_sec.get(sec_name, sorted_visuals)
                if len(candidates_aot) > 1:
                    cur_idx_aot = rotation_visual_idx.get(sec_name, 0)
                    next_predicted_vis = candidates_aot[(cur_idx_aot + 1) % len(candidates_aot)]
                    if loadedB != next_predicted_vis['name'] and not is_transitioning:
                        viewB.setHtml(get_html_content(
                            next_predicted_vis.get('code', ''),
                            custom_css=next_predicted_vis.get('custom_css', ''),
                            custom_html=next_predicted_vis.get('custom_html', ''),
                            inline_assets=next_predicted_vis.get('inline_assets', {}),
                            scaling_mode=next_predicted_vis.get('scaling_mode', 'auto')
                        ), get_local_base_url())
                        loadedB = next_predicted_vis['name']
                        just_loaded_b = True
            
            if rotation_beat_counter >= rotation_beats_until_switch:
                rotation_beat_counter = 0
                rotation_beats_until_switch = get_rotation_beat_interval(sec_name, music_energy, resolved_genre)
                
                # Rotate to next candidate visual for this section
                candidates = candidates_by_sec.get(sec_name, sorted_visuals)
                if len(candidates) > 1:
                    import random
                    if sec_name not in rotation_visual_idx:
                        rotation_visual_idx[sec_name] = random.randint(0, len(candidates) - 1)
                    
                    prev_idx = rotation_visual_idx[sec_name]
                    next_idx = prev_idx
                    # 隨機挑選下一個視覺模組，且不與當前重複
                    while next_idx == prev_idx:
                        next_idx = random.randint(0, len(candidates) - 1)
                    rotation_visual_idx[sec_name] = next_idx
                    new_vis = candidates[next_idx]
                    if current_rotation_vis is None or new_vis['name'] != current_rotation_vis['name']:
                        prev_rotation_vis = current_rotation_vis
                        current_rotation_vis = new_vis
                        rotation_trans_start = t
                        self.log_to_console(f"[拍點輪替] t={t:.2f}s 切換視覺: {new_vis['name']} (section={sec_name}, energy={music_energy:.2f})")

            # Determine the base visual: use rotation visual if available, otherwise section-assigned
            base_vis = current_rotation_vis if current_rotation_vis else sec_data.get('assigned_visual', sorted_visuals[0])
            
            # Find active visual (energy override can still trump rotation)
            active_vis = get_energy_adapted_visual(base_vis, music_energy, sec_name)
            
            # Transition check (section boundaries)
            is_transitioning = False
            trans_progress = 0.0
            other_vis = None
            
            if t - sec_data['start'] < trans_sec and sec_data['start'] > 0:
                is_transitioning = True
                trans_progress = (t - sec_data['start']) / trans_sec
                prev_sec_data, prev_sec_name = get_section_at_time(sec_data['start'] - 0.01)
                other_vis = get_energy_adapted_visual(prev_sec_data.get('assigned_visual', sorted_visuals[0]), music_energy, prev_sec_name)
                
            elif sec_data['end'] - t < trans_sec and sec_data['end'] < duration:
                is_transitioning = True
                trans_progress = (sec_data['end'] - t) / trans_sec
                next_sec_data, next_sec_name = get_section_at_time(sec_data['end'] + 0.01)
                other_vis = get_energy_adapted_visual(next_sec_data.get('assigned_visual', sorted_visuals[0]), music_energy, next_sec_name)
            
            # Rotation-based cross-fade (within section, between visual modules)
            elif rotation_trans_start > 0 and prev_rotation_vis and (t - rotation_trans_start) < rotation_trans_dur:
                is_transitioning = True
                trans_progress = (t - rotation_trans_start) / rotation_trans_dur
                other_vis = prev_rotation_vis
                
            # Perform page loads if needed
            if loadedA != active_vis['name']:
                viewA.setHtml(get_html_content(
                    active_vis.get('code', ''),
                    custom_css=active_vis.get('custom_css', ''),
                    custom_html=active_vis.get('custom_html', ''),
                    inline_assets=active_vis.get('inline_assets', {}),
                    scaling_mode=active_vis.get('scaling_mode', 'auto')
                ), get_local_base_url())
                
                ev_finished = [False]
                ev = QEventLoop()
                
                def on_load_finished_a(ok):
                    ev_finished[0] = True
                    try:
                        ev.quit()
                    except RuntimeError:
                        pass
                
                viewA.loadFinished.connect(on_load_finished_a)
                timer_a = QTimer()
                timer_a.setSingleShot(True)
                timer_a.timeout.connect(ev.quit)
                timer_a.start(1200)  # Extended timeout (1200ms) to ensure WebGL/P5 shaders finish compiling
                ev.exec()
                timer_a.stop()
                try:
                    viewA.loadFinished.disconnect(on_load_finished_a)
                except Exception:
                    pass
                
                QApplication.processEvents()
                loadedA = active_vis['name']
                just_loaded_a = True
                consecutive_black_frames = 0
                
                # [FIX] GPU Warm-up: execute multiple draw() cycles + GPU flush
                # loadFinished only means HTML parsed; WebGL shaders may still be
                # compiling and p5.js setup() may not have run. Run 8 warm-up draws
                # to ensure Canvas has valid pixels before real frame capture.
                _warmup_js = """
                (function() {
                    for (let wi = 0; wi < 8; wi++) {
                        try {
                            if (typeof redraw === 'function') redraw();
                            else if (typeof window.redraw === 'function') window.redraw();
                            else if (window._p5Instance && typeof window._p5Instance.redraw === 'function') window._p5Instance.redraw();
                            else if (typeof draw === 'function') draw();
                            else if (typeof window.draw === 'function') window.draw();
                        } catch(e) {}
                    }
                    // Force GPU pipeline flush so Compositor surface is populated
                    let canvases = document.querySelectorAll('canvas');
                    for (let c of canvases) {
                        try {
                            let gl = c.getContext('webgl2') || c.getContext('webgl');
                            if (gl) { gl.flush(); }
                        } catch(e) {}
                    }
                    return 'warmed';
                })();
                """
                _warmup_loop = QEventLoop()
                _warmup_timer = QTimer()
                _warmup_timer.setSingleShot(True)
                _warmup_timer.timeout.connect(_warmup_loop.quit)
                _warmup_timer.start(1500)  # 1.5s max wait for warm-up
                viewA.page().runJavaScript(_warmup_js, lambda r: _warmup_loop.quit() if r else None)
                _warmup_loop.exec()
                _warmup_timer.stop()
                QApplication.processEvents()
                
            if is_transitioning and other_vis and loadedB != other_vis['name']:
                viewB.setHtml(get_html_content(
                    other_vis.get('code', ''),
                    custom_css=other_vis.get('custom_css', ''),
                    custom_html=other_vis.get('custom_html', ''),
                    inline_assets=other_vis.get('inline_assets', {}),
                    scaling_mode=other_vis.get('scaling_mode', 'auto')
                ), get_local_base_url())
                
                ev_finished_b = [False]
                ev_b = QEventLoop()
                
                def on_load_finished_b(ok):
                    ev_finished_b[0] = True
                    try:
                        ev_b.quit()
                    except RuntimeError:
                        pass
                
                viewB.loadFinished.connect(on_load_finished_b)
                timer_b = QTimer()
                timer_b.setSingleShot(True)
                timer_b.timeout.connect(ev_b.quit)
                timer_b.start(1200)  # Extended timeout (1200ms) to ensure WebGL/P5 shaders finish compiling
                ev_b.exec()
                timer_b.stop()
                try:
                    viewB.loadFinished.disconnect(on_load_finished_b)
                except Exception:
                    pass
                
                QApplication.processEvents()
                loadedB = other_vis['name']
                just_loaded_b = True

                # [FIX] GPU Warm-up for ViewB: execute multiple draw() cycles + GPU flush
                _warmup_js_b = """
                (function() {
                    for (let wi = 0; wi < 8; wi++) {
                        try {
                            if (typeof redraw === 'function') redraw();
                            else if (typeof window.redraw === 'function') window.redraw();
                            else if (window._p5Instance && typeof window._p5Instance.redraw === 'function') window._p5Instance.redraw();
                            else if (typeof draw === 'function') draw();
                            else if (typeof window.draw === 'function') window.draw();
                        } catch(e) {}
                    }
                    let canvases = document.querySelectorAll('canvas');
                    for (let c of canvases) {
                        try {
                            let gl = c.getContext('webgl2') || c.getContext('webgl');
                            if (gl) { gl.flush(); }
                        } catch(e) {}
                    }
                    return 'warmed';
                })();
                """
                _warmup_loop_b = QEventLoop()
                _warmup_timer_b = QTimer()
                _warmup_timer_b.setSingleShot(True)
                _warmup_timer_b.timeout.connect(_warmup_loop_b.quit)
                _warmup_timer_b.start(1500)
                viewB.page().runJavaScript(_warmup_js_b, lambda r: _warmup_loop_b.quit() if r else None)
                _warmup_loop_b.exec()
                _warmup_timer_b.stop()
                QApplication.processEvents()

            # Inject parameters and redraw
            # Calculate section progress (0.0 → 1.0)
            # Retrieve real-time chord color for dynamic background modulation
            audio_feats = get_full_telemetry_at_time(t)
            chord_hex = audio_feats.get('chord_color_hex', '#0a0a0c')
            hihat_trig_str = "true" if audio_feats.get('hihat_trigger', False) else "false"
            hihat_dens_val = audio_feats.get('hihat_density', 0.0)
            synth_mel_str = "true" if audio_feats.get('synth_melody_active', False) else "false"
            harm_val = audio_feats.get('harmonic', 0.0)
            perc_val = audio_feats.get('percussive', 0.0)
            
            mod_time_a = module_accumulated_time.get(active_vis['name'], 0.0)
            ps_safe = "true"  # Mandatory photosensitive protection
            js = f"window.sectionName='{sec_name}';window.sectionProgress={sec_progress:.4f};window.currentChordColor='{chord_hex}';window.photosensitiveSafe={ps_safe};window.hihatTrigger={hihat_trig_str};window.hihatDensity={hihat_dens_val:.4f};window.synthMelodyActive={synth_mel_str};window.harmonicEnergy={harm_val:.4f};window.percussiveEnergy={perc_val:.4f};window.setFrameParams({t}, {str(is_beat).lower()}, {beat_energy:.4f}, {a_low:.4f}, {a_mid:.4f}, {a_high:.4f}, {mod_time_a:.4f})"
            
            # Draw A
            if not is_transitioning:
                viewB.hide()
            viewA.show()
            viewA.raise_()
            was_just_loaded_a = just_loaded_a
            frame_data_a = run_js_safely(viewA, js, is_first_frame=just_loaded_a)
            just_loaded_a = False
            
            pilA = None
            if frame_data_a and isinstance(frame_data_a, str) and frame_data_a.startswith("data:image/"):
                try:
                    raw_b64_a = frame_data_a.split(",", 1)[1]
                    img_bytes_a = base64.b64decode(raw_b64_a)
                    pilA = Image.open(io.BytesIO(img_bytes_a)).convert("RGBA")
                except Exception as e:
                    logger.warning(f"Error decoding canvas frameA: {e}")
                    pilA = None
            
            if pilA is None:
                ev_delay = QEventLoop()
                delay_ms = 350 if was_just_loaded_a else 12
                QTimer.singleShot(delay_ms, ev_delay.quit)
                ev_delay.exec()
                QApplication.processEvents()
                
                pixA = viewA.grab()
                imgA = pixA.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                img_w_a = imgA.width()
                img_h_a = imgA.height()
                ptrA = imgA.bits()
                ptrA.setsize(imgA.sizeInBytes())
                bufferA = memoryview(ptrA)
                pilA = Image.frombuffer("RGBA", (img_w_a, img_h_a), bufferA, "raw", "RGBA", 0, 1)

            if pilA.width != render_w or pilA.height != render_h:
                pilA = pilA.resize((render_w, render_h), Image.Resampling.BILINEAR)

            # 🛡️ 全局黑畫面終極保底防護 (Phase 2: Universal Anti-Flicker + Graceful Fallback + Linear Dark Blending)
            black_thresh = 2 if sec_name == 'Outro' else 8
            stat_a = pilA.getextrema()
            rgb_max_a = max(ext[1] for ext in stat_a[:3]) if stat_a else 0
            
            def _get_active_fallback():
                mod_c = module_cache_mgr.get_latest_frame(active_vis['name'])
                if mod_c is not None:
                    return apply_graceful_fallback(mod_c, t, beat_energy, a_low, chord_hex)
                elif 'last_valid_pil_frame' in locals() and last_valid_pil_frame is not None:
                    return apply_graceful_fallback(last_valid_pil_frame.copy(), t, beat_energy, a_low, chord_hex)
                else:
                    return song_fluid_engine.render_emergency_frame(render_w, render_h, t, beat_energy, a_low, chord_hex)

            if stat_a and all(ext[1] < black_thresh for ext in stat_a[:3]):
                consecutive_black_frames += 1
                if consecutive_black_frames == 1 or consecutive_black_frames % 30 == 0:
                    logger.warning(f"⚠️ [BlackScreenGuard] Frame {i} (t={t:.2f}s, section={sec_name}) 偵測到全黑影格，啟動保底攔截")
                pilA = _get_active_fallback()
            elif sec_name != 'Outro' and 4 <= rgb_max_a < 16:
                # Phase 2: 臨界半暗區線性軟混合 (Linear Dark Blending)，消除生硬跳變
                blend_w = max(0.0, min(1.0, (rgb_max_a - 4.0) / 12.0))
                fb_frame = _get_active_fallback()
                if fb_frame:
                    try:
                        pilA = Image.blend(fb_frame, pilA, blend_w)
                    except Exception:
                        pass
                consecutive_black_frames = 0
                module_cache_mgr.add_frame(active_vis['name'], pilA)
                last_valid_pil_frame = pilA.copy()
            else:
                consecutive_black_frames = 0
                module_cache_mgr.add_frame(active_vis['name'], pilA)
                last_valid_pil_frame = pilA.copy()
            if False:  # Cleaned legacy branch
                consecutive_black_frames = 0
                module_cache_mgr.add_frame(active_vis['name'], pilA)
                last_valid_pil_frame = pilA.copy()

            # ⏳ 累加當前模組在單曲中的總播放秒數 (Module Accumulated Timeline)
            module_accumulated_time[active_vis['name']] = module_accumulated_time.get(active_vis['name'], 0.0) + (1.0 / fps)

            if is_transitioning and other_vis:
                # Draw B
                viewB.show()
                viewB.raise_()
                was_just_loaded_b = just_loaded_b
                frame_data_b = run_js_safely(viewB, js, is_first_frame=just_loaded_b)
                just_loaded_b = False
                
                pilB = None
                if frame_data_b and isinstance(frame_data_b, str) and frame_data_b.startswith("data:image/"):
                    try:
                        raw_b64_b = frame_data_b.split(",", 1)[1]
                        img_bytes_b = base64.b64decode(raw_b64_b)
                        pilB = Image.open(io.BytesIO(img_bytes_b)).convert("RGBA")
                    except Exception as e:
                        logger.warning(f"Error decoding canvas frameB: {e}")
                        pilB = None
                
                if pilB is None:
                    ev_delay_b = QEventLoop()
                    delay_b_ms = 350 if was_just_loaded_b else 12
                    QTimer.singleShot(delay_b_ms, ev_delay_b.quit)
                    ev_delay_b.exec()
                    QApplication.processEvents()
                    
                    pixB = viewB.grab()
                    imgB = pixB.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    img_w_b = imgB.width()
                    img_h_b = imgB.height()
                    ptrB = imgB.bits()
                    ptrB.setsize(imgB.sizeInBytes())
                    bufferB = memoryview(ptrB)
                    pilB = Image.frombuffer("RGBA", (img_w_b, img_h_b), bufferB, "raw", "RGBA", 0, 1)

                if pilB.width != render_w or pilB.height != render_h:
                    pilB = pilB.resize((render_w, render_h), Image.Resampling.BILINEAR)
                
                # 🛡️ ViewB 黑畫面保底防護 (Phase 2: Universal Anti-Flicker + Graceful Fallback + Linear Dark Blending)
                black_thresh_b = 2 if sec_name == 'Outro' else 8
                stat_b = pilB.getextrema()
                rgb_max_b = max(ext[1] for ext in stat_b[:3]) if stat_b else 0
                
                def _get_active_fallback_b():
                    mod_c_b = module_cache_mgr.get_latest_frame(other_vis['name'])
                    if mod_c_b is not None:
                        return apply_graceful_fallback(mod_c_b, t, beat_energy, a_low, chord_hex)
                    elif pilA is not None:
                        return pilA.copy()
                    else:
                        return song_fluid_engine.render_emergency_frame(render_w, render_h, t, beat_energy, a_low, chord_hex)

                if stat_b and all(ext[1] < black_thresh_b for ext in stat_b[:3]):
                    pilB = _get_active_fallback_b()
                elif sec_name != 'Outro' and 4 <= rgb_max_b < 16:
                    blend_w_b = max(0.0, min(1.0, (rgb_max_b - 4.0) / 12.0))
                    fb_b = _get_active_fallback_b()
                    if fb_b:
                        try:
                            pilB = Image.blend(fb_b, pilB, blend_w_b)
                        except Exception:
                            pass
                    module_cache_mgr.add_frame(other_vis['name'], pilB)
                else:
                    module_cache_mgr.add_frame(other_vis['name'], pilB)

                # Determine transition type dynamically based on the section, energy and pattern rotation
                norm_sec = sec_name.lower().strip()
                trans_rot = int(t * 5.0) + int(audio_seed % 97)
                pat_options = ['diagonal_tl_br', 'diagonal_tr_bl', 'radial_iris', 'horizontal_shutter', 'diamond_expand', 'vertical_curtain']
                wipe_pat = pat_options[trans_rot % len(pat_options)]
                
                if 'intro' in norm_sec or 'outro' in norm_sec:
                    chosen_trans = 'luma_wipe' if trans_rot % 2 == 0 else 'solid_color_transition'
                elif 'verse' in norm_sec:
                    chosen_trans = 'displacement' if trans_rot % 2 == 0 else 'luma_wipe'
                elif 'chorus' in norm_sec or 'drop' in norm_sec:
                    if is_beat or beat_energy > 0.4:
                        chosen_trans = 'zoom_blur' if trans_rot % 3 != 0 else 'solid_color_transition'
                    else:
                        chosen_trans = 'glitch'
                elif 'build' in norm_sec:
                    chosen_trans = 'glitch' if trans_rot % 2 == 0 else 'zoom_blur'
                elif 'bridge' in norm_sec:
                    chosen_trans = 'slide_push' if trans_rot % 2 == 0 else 'solid_color_transition'
                else:
                    chosen_trans = 'displacement'

                # Intensity of the transition is modulated by beat energy
                trans_intensity = 0.4 + 0.6 * beat_energy

                img_to_stream = apply_advanced_transition(
                    pilB, pilA, trans_progress,
                    trans_type=chosen_trans,
                    intensity=trans_intensity,
                    is_beat=is_beat,
                    beat_energy=beat_energy,
                    wipe_pattern=wipe_pat,
                    chord_color_hex=chord_hex
                )
            else:
                img_to_stream = pilA

            # 🛡️ 輸出前終極防護：確保絕不向 FFmpeg 輸出未預期的純黑幀
            final_thresh = 2 if sec_name == 'Outro' else 8
            stat_final = img_to_stream.getextrema()
            if stat_final and all(ext[1] < final_thresh for ext in stat_final[:3]):
                if 'last_valid_pil_frame' in locals() and last_valid_pil_frame is not None:
                    img_to_stream = last_valid_pil_frame.copy()
                else:
                    img_to_stream = song_fluid_engine.render_emergency_frame(render_w, render_h, t, beat_energy, a_low, chord_hex)

            # Apply post-processing effects chain (flash, grain, throb, etc.)
            audio_feats = get_full_telemetry_at_time(t)
            if audio_samples_raw is not None:
                import numpy as np
                sample_idx = int(t * sr_raw)
                samples_slice = audio_samples_raw[sample_idx:sample_idx + 512]
                if len(samples_slice) < 512:
                    pad_len = 512 - len(samples_slice)
                    samples_slice = np.pad(samples_slice, (0, pad_len), 'constant')
                audio_feats['audio_samples'] = samples_slice
            else:
                audio_feats['audio_samples'] = None
                
            img_to_stream = apply_post_processing(img_to_stream, t, is_beat, beat_energy, audio_feats, section_name=sec_name, section_progress=sec_progress)

            # 🔍 實時 QC 與音視動態響應診斷器 (Real-time Quality & AV Response Auditor)
            if '_qc_auditor' not in locals():
                from realtime_qc_auditor import RealtimeRenderQCAuditor
                _qc_auditor = RealtimeRenderQCAuditor(sample_interval=30)

            img_to_stream, qc_boost = _qc_auditor.audit_frame(
                frame_i=i,
                pil_img=img_to_stream,
                t=t,
                is_beat=is_beat,
                beat_energy=beat_energy,
                audio_feats=audio_feats,
                sec_name=sec_name,
                music_energy=music_energy
            )

            # 若 QC 診斷出需要補強熱烈度或響應，動態進行影格修飾
            if qc_boost:
                if qc_boost.get('contrast_boost'):
                    from PIL import ImageEnhance
                    enh = ImageEnhance.Contrast(img_to_stream)
                    img_to_stream = enh.enhance(qc_boost['contrast_boost'])
                if qc_boost.get('force_hold_previous') and 'last_valid_pil_frame' in locals() and last_valid_pil_frame is not None:
                    img_to_stream = last_valid_pil_frame.copy()

            # Fix 1: Send frame to background writer thread via bounded queue
            # Periodic screenshot saving for visual quality assurance and monitoring
            if i % 300 == 0 or i == 30 or i == total_frames - 30:
                try:
                    shot_dir = "/Users/unclerm/.gemini/antigravity/brain/2615a4fe-c83f-4142-acf6-ce1423c09edd/screenshots"
                    os.makedirs(shot_dir, exist_ok=True)
                    song_slug = os.path.splitext(os.path.basename(audio_path))[0]
                    shot_path = os.path.join(shot_dir, f"{song_slug}_frame_{i:05d}.png")
                    img_to_stream.save(shot_path)
                except Exception:
                    pass

            # Check for writer errors first
            if _writer_error[0]:
                self.log_to_console(f"FFmpeg 寫入執行緒錯誤: {_writer_error[0]}", is_err=True)
                logger.error(f"FFmpeg writer thread error: {_writer_error[0]}")
                break
            
            # Non-blocking yield loop: if the queue is full, yield CPU/GPU to system & FFmpeg
            import time as _time_mod
            while _frame_queue.full():
                if self.render_aborted:
                    break
                QApplication.processEvents()
                _time_mod.sleep(0.005)  # Yield 5ms to OS scheduler to avoid CPU fight with FFmpeg

            try:
                # Ensure the image is in RGBA format (as expected by FFmpeg)
                # This prevents channel mismatches and offset issues when post-processing output mode is RGB.
                if img_to_stream.mode != "RGBA":
                    img_to_stream = img_to_stream.convert("RGBA")
                frame_bytes = img_to_stream.tobytes()
                _frame_queue.put(frame_bytes, block=False)  # Non-blocking put to avoid main thread freeze
            except _queue_mod.Full:
                self.log_to_console(f"⚠️ FFmpeg 佇列滿，跳過幀 {i}", is_err=True)
                logger.warning(f"Frame {i} dropped: queue full (concurrency race)")
            except Exception as e:
                self.log_to_console(f"寫入幀佇列時出錯: {e}", is_err=True)
                break

            # Fix 2: Explicit safe cleanup of per-frame objects
            for _v in ['pixA', 'imgA', 'bufferA', 'pilA', 'pixB', 'imgB', 'bufferB', 'pilB', 'img_to_stream']:
                if _v in locals():
                    del locals()[_v]

            # Fix 2: Periodic garbage collection and HTTP Cache cleaning
            if i % 300 == 0:
                try:
                    viewA.page().profile().clearHttpCache()
                    if is_transitioning and other_vis:
                        viewB.page().profile().clearHttpCache()
                except Exception:
                    pass
                gc.collect()
            elif i % 100 == 0:
                gc.collect()

            # Yield CPU to the operating system to prevent overall system lag/sluggishness
            # CPU 運作模式：依使用者 UI 選擇決定是否啟用溫控保護
            if _cpu_full_power:
                # 全力運作模式：跳過溫控偵測，僅做最小 yield 防止 OS 鎖死
                render_delay = 0.001
            elif i % 100 == 0:
                # 控溫模式：CPU過熱保護機制動態延遲與強制冷卻
                thermal_speed_limit, thermal_has_warning = self.check_mac_thermal_state()
                if thermal_has_warning:
                    self.log_to_console("⚠️ 偵測到 macOS 系統高溫警告！進入過熱保護模式，強制暫停 10 秒冷卻...", is_err=True)
                    self.status_lbl.setText("⚠️ CPU 過熱保護中，強制冷卻 10 秒...")
                    _time_mod.sleep(10.0)
                    update_render_status_label(i)
                    render_delay = 0.100  # 冷卻後仍保持較慢的渲染速度
                elif thermal_speed_limit < 80:
                    self.log_to_console(f"⚠️ 偵測到 CPU 受到熱降頻限制 ({thermal_speed_limit}%)！將影格間距調大至 50ms 防止過熱...", is_err=True)
                    render_delay = 0.050
                elif thermal_speed_limit < 100:
                    self.log_to_console(f"⚠️ 偵測到 CPU 輕微受限 ({thermal_speed_limit}%)！將影格間距調大至 20ms 防止過熱...", is_err=True)
                    render_delay = 0.020
                else:
                    render_delay = 0.002
            
            _time_mod.sleep(render_delay)

            # Fix 6+7: Periodic logging + memory monitoring
            if i % 50 == 0:
                try:
                    import psutil as _psutil_mod
                    process = _psutil_mod.Process()
                    mem_bytes = process.memory_info().rss
                    for child in process.children(recursive=True):
                        try:
                            mem_bytes += child.memory_info().rss
                        except (_psutil_mod.NoSuchProcess, _psutil_mod.AccessDenied):
                            pass
                    mem_mb = mem_bytes / (1024 * 1024)
                except Exception:
                    mem_mb = 0
                
                if i % 200 == 0:
                    logger.info(f"幀 {i}/{total_frames} ({int(i/total_frames*100)}%) 記憶體={mem_mb:.0f}MB 佇列={_frame_queue.qsize()}/{_frame_queue.maxsize}")
                
                # Fix 7: Memory watchdog — auto-disable post-fx above threshold (optimized for 32GB iMac)
                if mem_mb > 16384 and _post_fx_enabled[0]:
                    _post_fx_enabled[0] = False
                    logger.warning(f"記憶體 {mem_mb:.0f}MB 超過 16GB 閾值，自動停用後製特效節省記憶體")
                    self.log_to_console(f"⚠️ 記憶體使用 {mem_mb:.0f}MB 超過 16GB 閾值，已自動停用後製特效")
                elif mem_mb > 12288 and i % 100 != 0:  # Force extra GC above 12GB
                    gc.collect()

            self.progress_bar.setValue(i + 1)
            update_render_status_label(i)
            if i % 20 == 0:
                self.log_to_console(f"已發送 {i+1} / {total_frames} 影格到編碼器...")
            QApplication.processEvents()

        # Step 3: Close pipeline and finalize
        if getattr(self, 'is_batch_rendering', False):
            self.batch_completed_frames += total_frames
            
        self.status_lbl.setText("影格發送完畢，正在等待編碼器完成...")
        self.log_to_console("正在等待 FFmpeg 寫入佇列清空...")
        
        # Signal writer thread to stop and wait for queue to drain
        if not _writer_error[0] and _writer_thread.is_alive():
            try:
                _frame_queue.put(None, timeout=1.0)  # Put sentinel with short timeout
            except Exception:
                pass
        
        try:
            ffmpeg_process.stdin.close()
        except:
            pass
        
        try:
            _writer_thread.join(timeout=3.0)  # Wait up to 3 seconds for thread to finish
        except Exception as e:
            logger.warning(f"等待寫入執行緒時出錯: {e}")
        
        try:
            # If aborted or writer error, force terminate/kill immediately
            if self.render_aborted or _writer_error[0]:
                try:
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait(timeout=3.0)
                except Exception:
                    try:
                        ffmpeg_process.kill()
                    except Exception:
                        pass
            else:
                ffmpeg_process.wait(timeout=30)  # Add timeout to prevent permanent hang
                
            ffmpeg_stderr_thread.join(timeout=2.0)

            if not self.render_aborted and ffmpeg_process.returncode == 0:
                self.log_to_console(f"✅ MV 影片成功導出！\n檔案路徑: {output_file}")
                self.status_lbl.setText("渲染成功！")
                logger.info(f"=== 渲染成功 === 輸出: {output_file}")
                
                # Write structured JSON metadata to render.log for downstream tools (e.g. Shorts exporter)
                try:
                    # Build visual credits list with full attribution info
                    visual_credits = []
                    for idx, v in enumerate(visuals_data):
                        visual_credits.append({
                            "index": idx,
                            "name": v.get('name', '未命名'),
                            "author": v.get('author', '未知作者'),
                            "license": v.get('license', 'Creative Commons'),
                            "url": v.get('url', '').strip() or 'OpenProcessing'
                        })
                    
                    # Build storyboard → visual module mapping (which module plays in which time range)
                    storyboard_visual_map = []
                    for sec_data in storyboard:
                        assigned = sec_data.get('assigned_visual', {})
                        # Find index of this visual in visuals_data
                        vis_idx = -1
                        for i, v in enumerate(visuals_data):
                            if v.get('name') == assigned.get('name'):
                                vis_idx = i
                                break
                        storyboard_visual_map.append({
                            "start": sec_data.get('start', 0),
                            "end": sec_data.get('end', 0),
                            "section": sec_data.get('section', 'Verse'),
                            "visual_index": vis_idx
                        })
                    
                    # Serialize storyboard without the non-serializable assigned_visual dict
                    clean_storyboard = [
                        {"start": s.get("start", 0), "end": s.get("end", 0), "section": s.get("section", "Verse")}
                        for s in storyboard
                    ]
                    
                    render_metadata = {
                        "bpm": bpm,
                        "duration": duration,
                        "audio_path": audio_path,
                        "genre": resolved_genre,
                        "storyboard": clean_storyboard,
                        "resolution": f"{w}x{h}",
                        "fps": fps,
                        "total_frames": total_frames,
                        "visual_modules": [v.get('name', '未命名') for v in visuals_data],
                        "visual_credits": visual_credits,
                        "storyboard_visual_map": storyboard_visual_map,
                        "output_file": output_file
                    }
                    logger.info("=== RENDER_METADATA_JSON ===")
                    logger.info(json.dumps(render_metadata, ensure_ascii=False))
                except Exception as _meta_err:
                    logger.warning(f"寫入渲染元資料 JSON 失敗: {_meta_err}")
                
                self.create_credits_file(output_file, visuals_data)
                self.create_social_templates(output_file, audio_path, resolved_genre, bpm, duration, visuals_data)
                if show_popups:
                    QMessageBox.information(self, "完成", f"影片成功渲染並儲存至:\n{output_file}")
                return True
            else:
                err_output = "".join(ffmpeg_stderr_accumulator)
                self.log_to_console(f"❌ FFMPEG 編碼出錯或已被使用者中斷！錯誤代碼: {ffmpeg_process.returncode}\n{err_output}", is_err=True)
                logger.error(f"FFmpeg 失敗 returncode={ffmpeg_process.returncode}: {err_output[:500]}")
                if show_popups and not self.render_aborted:
                    QMessageBox.critical(self, "錯誤", f"FFMPEG 編碼失敗: {err_output}")
                return False
        except subprocess.TimeoutExpired:
            err_output = "".join(ffmpeg_stderr_accumulator)
            self.log_to_console(f"❌ FFmpeg 編碼逾時 (30秒)，最後輸出:\n{err_output[-500:]}", is_err=True)
            logger.error(f"FFmpeg wait() timed out after 30s. Last stderr:\n{err_output}")
            try:
                ffmpeg_process.kill()
            except Exception:
                pass
            return False
        except Exception as e:
            self.log_to_console(f"❌ 編碼結束階段發生異常: {e}", is_err=True)
            logger.exception(f"編碼結束異常: {e}")
            if show_popups and not self.render_aborted:
                QMessageBox.critical(self, "錯誤", f"影片合成失敗: {e}")
            return False
        finally:
            if not is_batch:
                self.set_render_buttons_enabled(True)
                self.btn_cancel_render.setEnabled(False)
            # Cleanup views
            try:
                for v in [viewA, viewB]:
                    if v:
                        v.setParent(None)
                        v.close()
                        v.deleteLater()
            except:
                pass
            try:
                if _current_clipper[0]:
                    _current_clipper[0].setParent(None)
                    _current_clipper[0].close()
                    _current_clipper[0].deleteLater()
                    _current_clipper[0] = None
            except:
                pass
            # Fix 6: Remove file handler to avoid leaking handlers
            try:
                logger.removeHandler(_file_handler)
                _file_handler.close()
            except:
                pass
            # Fix 2: Final GC
            gc.collect()
            logger.info(f"=== 渲染結束，資源已釋放 ===")

    def create_credits_file(self, output_file, visuals_data):
        try:
            credits_path = os.path.splitext(output_file)[0] + "_credits.txt"
            
            content = []
            content.append("======================================================================")
            content.append("Visual/Animation Credits")
            content.append("======================================================================")
            content.append("")
            content.append("Music Video visual elements generated via OpenProcessing.")
            content.append("")
            
            for i, data in enumerate(visuals_data, 1):
                name = data.get("name", "未命名模組")
                author = data.get("author", "未知作者")
                license_mode = data.get("license", "Creative Commons")
                url = data.get("url", "").strip()
                if not url:
                    url = "N/A"
                
                is_uM_variant = False
                orig_name = None
                orig_author = None
                orig_url = None
                orig_license = None
                
                tags = data.get("tags", [])
                if name.startswith("Uncler M - ") or author == "Uncler M" or any("Uncler M" in t for t in tags):
                    is_uM_variant = True
                    
                    # 1. Try to find the original key from starred_ tag
                    orig_key = None
                    for t in tags:
                        if t.startswith("starred_"):
                            orig_key = t.replace("starred_", "")
                            break
                    
                    if orig_key:
                        orig_path = os.path.join(workspace_dir, "custom_visuals", f"{orig_key}.json")
                        if os.path.exists(orig_path):
                            try:
                                with open(orig_path, "r", encoding="utf-8") as f_orig:
                                    orig_data = json.load(f_orig)
                                    orig_name = orig_data.get("name")
                                    orig_author = orig_data.get("author")
                                    orig_url = orig_data.get("url")
                                    orig_license = orig_data.get("license")
                            except:
                                pass
                    
                    # 2. Regex fallback if original info not loaded
                    if not orig_name:
                        import re as _re
                        code_content = data.get("code", "")
                        match = _re.search(r"Inspired\s+by\s+['\"]([^'\"]+)['\"]\s+by\s+['\"]([^'\"]+)['\"]", code_content, _re.IGNORECASE)
                        if match:
                            orig_name = match.group(1)
                            orig_author = match.group(2)
                
                if is_uM_variant and orig_name:
                    content.append(f"[{i}] Secondary Creation: \"{name}\" by {author}")
                    content.append(f"    Inspired by original sketch: \"{orig_name}\" by {orig_author}")
                    final_orig_url = orig_url if orig_url else url
                    if final_orig_url and final_orig_url != "N/A":
                        content.append(f"    Original Link: {final_orig_url}")
                    final_orig_license = orig_license if orig_license else license_mode
                    if final_orig_license:
                        content.append(f"    Original License: {final_orig_license}")
                    content.append(f"    Licensed under: {license_mode}")
                else:
                    content.append(f"[{i}] Original Sketch: \"{name}\" by {author}")
                    content.append(f"    Link: {url}")
                    content.append(f"    Licensed under: {license_mode}")
                content.append("")
                
            content.append("----------------------------------------------------------------------")
            content.append("All visual elements are licensed under Creative Commons.")
            content.append("Please respect the licensing terms and credit the original authors.")
            content.append("======================================================================")
            
            with open(credits_path, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
                
            self.log_to_console(f"已自動生成 YouTube 影片資訊欄 CC 授權說明文字檔：\n{credits_path}")
        except Exception as e:
            self.log_to_console(f"生成授權說明文件失敗: {e}", is_err=True)

    def clean_hashtag(self, text):
        import re
        cleaned = re.sub(r'[^\w]', '', text)
        return cleaned

    def create_social_templates(self, output_file, audio_path, genre, bpm, duration, visuals_data):
        try:
            # Parse artist and song name
            audio_name = os.path.basename(audio_path) if audio_path else "Unknown"
            audio_base, _ = os.path.splitext(audio_name)
            
            artist = "POHAN"
            song = audio_base
            if " - " in audio_base:
                parts = audio_base.split(" - ", 1)
                if parts[0].strip().upper() == "POHAN":
                    song = parts[1].strip()
                elif parts[1].strip().upper() == "POHAN":
                    song = parts[0].strip()
                else:
                    song = parts[1].strip()
            elif "-" in audio_base:
                parts = audio_base.split("-", 1)
                if parts[0].strip().upper() == "POHAN":
                    song = parts[1].strip()
                elif parts[1].strip().upper() == "POHAN":
                    song = parts[0].strip()
                else:
                    song = parts[1].strip()

            # Proactively search YouTube for this track's URL on POHAN channel
            youtube_url = "unknown"
            try:
                query_str = f"POHAN {song}"
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                import urllib.request as _urllib_request
                import urllib.parse as _urllib_parse
                import json as _json
                
                url = "https://www.youtube.com/results?search_query=" + _urllib_parse.quote(query_str)
                req = _urllib_request.Request(url, headers=headers)
                with _urllib_request.urlopen(req, timeout=8) as response:
                    html = response.read().decode("utf-8")
                    match = re.search(r"var ytInitialData = (.*?);</script>", html)
                    if not match:
                        match = re.search(r"window\[\"ytInitialData\"\] = (.*?);</script>", html)
                    if match:
                        yt_data = _json.loads(match.group(1))
                        
                        def find_videos(obj):
                            videos = []
                            if isinstance(obj, dict):
                                if "videoRenderer" in obj:
                                    videos.append(obj["videoRenderer"])
                                else:
                                    for k, v in obj.items():
                                        videos.extend(find_videos(v))
                            elif isinstance(obj, list):
                                for item in obj:
                                    videos.extend(find_videos(item))
                            return videos
                            
                        videos = find_videos(yt_data)
                        for v in videos:
                            v_title = v.get("title", {}).get("runs", [{}])[0].get("text", "")
                            video_id = v.get("videoId", "")
                            owner_runs = v.get("ownerText", {}).get("runs", [{}])
                            channel_name = owner_runs[0].get("text", "") if owner_runs else ""
                            channel_id = owner_runs[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "") if owner_runs else ""
                            
                            channel_matches = (channel_id == "UCuerJAKgF3zLnIvCtwPorLA" or "POHAN" in channel_name.upper() or "POHAN528" in channel_name.upper())
                            
                            song_words = re.findall(r"\w+", song.lower())
                            title_lower = v_title.lower()
                            title_matches = all(w in title_lower for w in song_words)
                            
                            if channel_matches and title_matches:
                                youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                                break
            except Exception as e:
                self.log_to_console(f"YouTube 搜尋歌曲連結時發生例外: {e}")

            # Proactively search Apple Music for this track's URL
            apple_music_url = "unknown"
            try:
                term = f"POHAN {song}"
                import urllib.request as _urllib_request
                import urllib.parse as _urllib_parse
                import json as _json
                
                am_url = f"https://itunes.apple.com/search?term={_urllib_parse.quote(term)}&media=music&entity=song"
                am_headers = {"User-Agent": "Mozilla/5.0"}
                am_req = _urllib_request.Request(am_url, headers=am_headers)
                with _urllib_request.urlopen(am_req, timeout=5) as am_response:
                    am_res = _json.loads(am_response.read().decode("utf-8"))
                    am_results = am_res.get("results", [])
                    if am_results:
                        apple_music_url = am_results[0].get("trackViewUrl", "unknown")
            except Exception as e:
                self.log_to_console(f"Apple Music 搜尋歌曲連結時發生例外: {e}")

            # Format duration into MM:SS
            minutes = int(duration) // 60
            seconds = int(duration) % 60
            duration_str = f"{minutes:02d}:{seconds:02d}"
            
            # Format BPM
            bpm_str = f"{bpm:.0f}" if bpm else "N/A"
            
            social_path = os.path.splitext(output_file)[0] + "_social.txt"
            
            content = []
            content.append("======================================================================")
            content.append("📲 SOCIAL MEDIA UPLOAD TEMPLATES (YOUTUBE / SHORTS / IG / TIKTOK)")
            content.append("======================================================================")
            content.append(f"Track: {song}")
            content.append(f"Artist: {artist}")
            content.append(f"Genre: {genre.capitalize() if genre else 'Ambient'}")
            content.append(f"BPM: {bpm_str}")
            content.append(f"Duration: {duration_str}")
            content.append("======================================================================")
            content.append("")
            
            # 1. YOUTUBE LONG-FORM VIDEO
            content.append("--- [1] YOUTUBE LONG-FORM VIDEO ---")
            content.append("Title:")
            content.append(f"{song} - {artist} | 4K p5.js 音畫互動 MV (Audio-Reactive Visualizer / VJ Loop)")
            content.append("")
            content.append("Description:")
            content.append("🎧 立即收聽 / Stream & Download:")
            content.append(f"👉 YouTube: {youtube_url}")
            content.append(f"👉 Apple Music: {apple_music_url}")
            content.append("")
            content.append("🎵 【音樂資訊 / Track Info】")
            content.append(f"- 歌曲名稱 (Song Title): {song}")
            content.append(f"- 創作者/藝術家 (Artist): {artist}")
            content.append(f"- 音訊長度 (Duration): {duration_str}")
            content.append(f"- 音軌速度 (Tempo): {bpm_str} BPM")
            content.append(f"- 音樂類型 (Genre): {genre.capitalize() if genre else 'Ambient'}")
            content.append("- 視覺技術 (Visuals): 4K Visual Integration Editor (p5.js / WebGL / Custom Shaders)")
            content.append("")
            
            # Render Visual Module Credits / Copyrights
            content.append("🎨 【視覺創作與授權 / Visual Credits & License】")
            for i, data in enumerate(visuals_data, 1):
                name = data.get("name", "未命名模組")
                author = data.get("author", "未知作者")
                license_mode = data.get("license", "Creative Commons")
                url = data.get("url", "").strip()
                if not url or url == "N/A":
                    url = "OpenProcessing"
                
                is_uM_variant = False
                orig_name = None
                orig_author = None
                
                tags = data.get("tags", [])
                if name.startswith("Uncler M - ") or author == "Uncler M" or any("Uncler M" in t for t in tags):
                    is_uM_variant = True
                    orig_key = None
                    for t in tags:
                        if t.startswith("starred_"):
                            orig_key = t.replace("starred_", "")
                            break
                    if orig_key:
                        orig_path = os.path.join(workspace_dir, "custom_visuals", f"{orig_key}.json")
                        if os.path.exists(orig_path):
                            try:
                                with open(orig_path, "r", encoding="utf-8") as f_orig:
                                    orig_data = json.load(f_orig)
                                    orig_name = orig_data.get("name")
                                    orig_author = orig_data.get("author")
                            except:
                                pass
                    if not orig_name:
                        import re as _re
                        code_content = data.get("code", "")
                        match = _re.search(r"Inspired\s+by\s+['\"]([^'\"]+)['\"]\s+by\s+['\"]([^'\"]+)['\"]", code_content, _re.IGNORECASE)
                        if match:
                            orig_name = match.group(1)
                            orig_author = match.group(2)
                
                if is_uM_variant and orig_name:
                    content.append(f"- [{i}] Visual: \"{name}\" by {author} (Secondary Creation)")
                    content.append(f"  * Inspired by original sketch: \"{orig_name}\" by {orig_author}")
                    content.append(f"  * License: {license_mode}")
                else:
                    content.append(f"- [{i}] Visual: \"{name}\" by {author}")
                    content.append(f"  * Link: {url}")
                    content.append(f"  * License: {license_mode}")
            content.append("")

            
            clean_artist = self.clean_hashtag(artist)
            clean_song = self.clean_hashtag(song)
            
            content.append("Hashtags:")
            content.append(f"#4KMV #AudioReactive #Visualizer #MusicVideo #VJLoop #LoFi #Ambient #Techno #{clean_artist} #{clean_song}")
            content.append("")
            content.append("======================================================================")
            content.append("")
            
            # 2. YOUTUBE SHORTS
            content.append("--- [2] YOUTUBE SHORTS ---")
            content.append("Title / Caption:")
            content.append(f"{song} - {artist} | 4K p5.js 音畫互動 #shorts #music #visualizer")
            content.append("")
            content.append("Description:")
            content.append("Experience the immersive 4K audio-reactive visualizer! 🎧✨")
            content.append("體驗沉浸式 4K 音頻響應視覺化！")
            content.append("")
            content.append("Full video on channel! / 完整版 MV 請至頻道收看！")
            content.append("")
            content.append(f"#shorts #music #visualizer #audioreactive #4K #ambient #lofi #techno #vjloop #{clean_artist}")
            content.append("")
            content.append("======================================================================")
            content.append("")
            
            # 3. INSTAGRAM REEL / POST
            content.append("--- [3] INSTAGRAM REEL / POST ---")
            content.append("Caption:")
            content.append(f"🎧 {song} - {artist} | 4K p5.js 音畫互動 MV (Audio-Reactive VJ Loop)")
            content.append("")
            content.append("✨ 沉浸於精準的音頻響應視覺中。由 4K 視覺整合編輯器生成，將每一聲節拍轉化為迷幻的幾何跳動。")
            content.append("✨ Immerse yourself in precise audio-reactive visuals. Generated by our 4K Visual Integration Editor, transforming every beat into mesmerizing geometric pulses.")
            content.append("")
            content.append("👉 Full MV link in bio! / 完整版 MV 連結在個人檔案！")
            content.append("")
            content.append(".")
            content.append(".")
            content.append(".")
            content.append(f"#AudioReactive #Visualizer #MusicVideo #4KMV #VJLoop #LoFi #Ambient #Techno #GenerativeArt #CreativeCoding #p5js #InstagramMusic #{clean_artist}")
            content.append("")
            content.append("======================================================================")
            content.append("")
            
            # 4. TIKTOK VIDEO
            content.append("--- [4] TIKTOK VIDEO ---")
            content.append("Caption & Hashtags:")
            content.append(f"{song} - {artist} 🎧 4K p5.js 音畫互動 Visualizer! 🤯✨ #music #visualizer #audioreactive #4kmv #vj #lofi #ambient #creativecoding #fyp #p5js #{clean_artist}")
            content.append("")
            content.append("======================================================================")
            
            with open(social_path, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
                
            self.log_to_console(f"已自動生成各大平台社群貼文模板文字檔：\n{social_path}")
        except Exception as e:
            self.log_to_console(f"生成社群貼文模板失敗: {e}", is_err=True)
            logger.error(f"Failed to generate social templates: {e}")

    def fetch_and_load_openprocessing(self):
        url = self.op_input.text().strip()
        if not url:
            self.log_to_console("ERROR: 請先輸入 OpenProcessing 作品網址！", is_err=True)
            return
            
        self.log_to_console(f"正在從 OpenProcessing 獲取作品代碼: {url} ...")
        self.btn_op_fetch.setEnabled(False)
        self.btn_op_fetch.setText("⏳ 正在下載...")
        QApplication.processEvents()
        
        try:
            title, sketch_id, code, css, html, assets, author, license_name, file_base = self.perform_op_fetch(url)
            self.custom_css = css
            self.custom_html = html
            self.inline_assets = assets
            self.current_preset_id = sketch_id
            self.editor.setPlainText(code)
            self.author_input.setText(author)
            self.license_input.setText(license_name)
            
            # 自動檢測並下載外部資產
            import re
            check_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
            check_code = re.sub(r'//.*', '', check_code)
            asset_pattern = r'["\'`]([^"\'`]+?\.(?:png|jpg|jpeg|gif|svg|ttf|otf|woff|woff2|mp3|wav|ogg|obj|fbx|gltf|glb))["\'`]'
            asset_names = list(set(re.findall(asset_pattern, check_code)))
            
            if file_base and asset_names:
                assets_dir = os.path.join(workspace_dir, "custom_visuals", "assets", str(sketch_id))
                os.makedirs(assets_dir, exist_ok=True)
                for asset in asset_names:
                    clean_asset = asset.lstrip("./")
                    asset_url = file_base + clean_asset
                    local_file_path = os.path.join(assets_dir, clean_asset)
                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                    
                    self.log_to_console(f"⏳ 正在背景下載外部資產: {clean_asset}...")
                    try:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        asset_resp = requests.get(asset_url, headers=headers, timeout=15)
                        if asset_resp.status_code == 200:
                            with open(local_file_path, "wb") as af:
                                af.write(asset_resp.content)
                            self.log_to_console(f"   [+] 資產 {clean_asset} 下載成功！")
                        else:
                            self.log_to_console(f"   [!] 資產 {clean_asset} 下載失敗 (HTTP {asset_resp.status_code})", is_err=True)
                    except Exception as dl_err:
                        self.log_to_console(f"   [!] 下載資產 {clean_asset} 時出錯: {dl_err}", is_err=True)

            cleaned_title = re.sub(r'[^a-zA-Z0-9_]', '', title)
            if not cleaned_title:
                cleaned_title = f"op_{sketch_id}"
            self.name_input.setText(cleaned_title)
            self.log_to_console(f"SUCCESS: 成功載入作品「{title}」(ID: {sketch_id})！")
            self.adapt_and_repair_code()
        except Exception as e:
            self.log_to_console(f"ERROR: 擷取失敗: {e}", is_err=True)
        finally:
            self.btn_op_fetch.setEnabled(True)
            self.btn_op_fetch.setText("⚡ 【自動抓取程式碼】")
            QApplication.processEvents()

    def open_batch_import_dialog(self):
        from batch_importer import BatchImportDialog
        dialog = BatchImportDialog(self, refresh_callback=self.refresh_presets_list)
        dialog.exec()




    def open_dependency_downloader_dialog(self):
        dlg = DependencyDownloaderDialog(self)
        dlg.exec()

    def open_module_cleanup_dialog(self):
        mode_dlg = CleanupModeDialog(self)
        if mode_dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        if mode_dlg.mode == "auto":
            dialog = ModuleCleanupDialog(self)
            dialog.exec()
        elif mode_dlg.mode == "manual":
            self.start_manual_cleanup()
        elif mode_dlg.mode == "black_screen":
            from black_screen_detector import BlackScreenDetectorDialog
            dialog = BlackScreenDetectorDialog(self)
            dialog.exec()

    def start_manual_cleanup(self):
        progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
        has_saved = os.path.exists(progress_path)
        
        # 檢測到上次未完成的進度時先進行提示
        if has_saved:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("試運行任務選項")
            msg_box.setText("系統偵測到有上次未完成的試運行任務。\n請選擇要如何進行：")
            
            resume_btn = msg_box.addButton("▶️ 繼續未完成的任務", QMessageBox.ButtonRole.AcceptRole)
            start_new_btn = msg_box.addButton("🔁 重頭開始全新試運行", QMessageBox.ButtonRole.YesRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            clicked = msg_box.clickedButton()
            
            if clicked == cancel_btn:
                return
            elif clicked == resume_btn:
                try:
                    with open(progress_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    from batch_importer import TestRunDialog
                    test_dlg = TestRunDialog(data["items"], self)
                    test_dlg.current_idx = data["current_idx"]
                    test_dlg.exec()
                    self.refresh_presets_list()
                    return
                except Exception as e:
                    QMessageBox.warning(self, "讀取失敗", f"讀取上次進度時發生錯誤：{e}")

        save_dir = os.path.join(workspace_dir, "custom_visuals")
        if not os.path.exists(save_dir):
            QMessageBox.warning(self, "目錄不存在", "custom_visuals 目錄不存在，無法進行清理！")
            return
            
        json_files = [f for f in os.listdir(save_dir) if f.endswith(".json")]
        json_files.sort()
        
        if not json_files:
            QMessageBox.information(self, "無模組", "視覺預設模組庫中無任何模組需要清理！")
            return
            
        items_to_test = []
        for filename in json_files:
            filepath = os.path.join(save_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Extract sketch ID from URL if possible
                url = data.get("url", "")
                sketch_id = None
                sketch_match = re.search(r'/sketch/(\d+)', url)
                if not sketch_match:
                    sketch_match = re.search(r'/@[\w\-]+/(\d+)', url)
                if sketch_match:
                    sketch_id = sketch_match.group(1)
                else:
                    sketch_id = filename[:-5]
                
                items_to_test.append({
                    "id": sketch_id,
                    "title": data.get("name", filename[:-5]),
                    "url": url or "https://openprocessing.org",
                    "filename": filename,
                    "filepath": filepath,
                    "code": data.get("code", ""),
                    "custom_html": data.get("custom_html", ""),
                    "custom_css": data.get("custom_css", ""),
                    "save_dir": save_dir
                })
            except Exception as e:
                print(f"Error loading {filename}: {e}")
                
        if not items_to_test:
            QMessageBox.warning(self, "無有效模組", "未能載入任何有效的視覺預設模組。")
            return
            
        from batch_importer import TestRunDialog
        test_dlg = TestRunDialog(items_to_test, self)
        test_dlg.exec()
        
        # 重新整理 Preset 列表
        self.refresh_presets_list()

    def extract_js_object(self, html, var_name):
        import re
        pattern = rf'var\s+{var_name}\s*=\s*'
        match = re.search(pattern, html)
        if not match:
            return None
        
        start_idx = match.end()
        first_brace_idx = html.find('{', start_idx)
        if first_brace_idx == -1:
            return None
            
        try:
            import json
            decoder = json.JSONDecoder()
            # 優先採用標準庫 JSON 解碼器尋找 JSON 尾端索引，防範任何字元截斷問題
            _, end_idx = decoder.raw_decode(html[first_brace_idx:])
            return html[first_brace_idx:first_brace_idx + end_idx]
        except Exception as e:
            # 發生解碼錯誤時，回退至深度計數後備方案
            brace_count = 0
            in_string = False
            string_char = None
            escaped = False
            
            for i in range(first_brace_idx, len(html)):
                char = html[i]
                
                if escaped:
                    escaped = False
                    continue
                    
                if char == '\\':
                    escaped = True
                    continue
                    
                if in_string:
                    if char == string_char:
                        in_string = False
                        string_char = None
                    continue
                    
                if char in ('"', "'", '`'):
                    in_string = True
                    string_char = char
                    continue
                    
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return html[first_brace_idx:i+1]
                        
            return None

    def perform_op_fetch(self, url):
        import re
        import requests
        import json
        
        match = re.search(r'/sketch/(\d+)', url)
        if not match:
            match = re.search(r'/@[\w\-]+/(\d+)', url)
        if not match:
            raise ValueError("無法解析網址中的作品 ID，請確保網址格式正確。")
            
        sketch_id = match.group(1)
        self.last_fetched_sketch_id = sketch_id
        embed_url = f"https://openprocessing.org/sketch/{sketch_id}/embed/"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(embed_url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(f"無法存取 OpenProcessing (HTTP {response.status_code})")
            
        html = response.text
        
        sketch_json = self.extract_js_object(html, "sketch")
        if not sketch_json:
            raise ValueError("無法在頁面中找到作品資料，可能該作品已被設為不公開或網址無效。")
            
        try:
            sketch_data = json.loads(sketch_json)
        except Exception as e:
            raise ValueError(f"解析作品資料失敗: {e}")
            
        # 1. 提取 HTML 中聲明的靜態外部依賴庫
        ext_script_tags = ""
        try:
            script_matches = re.finditer(r'<script([^>]+)>', html, re.IGNORECASE)
            builtin_keywords = ["p5.js", "p5.min.js", "p5.sound", "p5.func", "gsap", "opc.min.js", "opc.js", "p5.flex", "chroma.min.js", "rampensau", "three.js", "three.module.js", "sketch.js", "sketch_embed.js"]
            wrapper_keywords = ["/assets/js/vendor/", "civiccomputing.com", "cloudflareinsights.com", "beacon.min.js", "codemirror", "quill"]
            
            for match in script_matches:
                attrs = match.group(1)
                src_match = re.search(r'src=["\'](.*?)["\']', attrs, re.IGNORECASE)
                if not src_match:
                    continue
                
                src = src_match.group(1)
                src_lower = src.lower()
                
                if any(kw in src_lower for kw in builtin_keywords):
                    continue
                if re.search(r'/assets/.*?/js/', src_lower) or any(kw in src_lower for kw in wrapper_keywords):
                    continue
                    
                abs_src = src if src.startswith(("http://", "https://")) else "https://openprocessing.org" + ("/" + src.lstrip("/"))
                
                if "type=\"module\"" in attrs.lower() or "type='module'" in attrs.lower() or src_lower.endswith(".mjs"):
                    ext_script_tags += f'<script type="module" src="{abs_src}"></script>\n'
                else:
                    ext_script_tags += f'<script src="{abs_src}"></script>\n'
        except Exception:
            pass
            
        # 2. 提取 JSON 中聲明的自訂外部依賴庫
        json_libs_html = ""
        libs_list = sketch_data.get("libraries", [])
        if libs_list and isinstance(libs_list, list):
            for lib in libs_list:
                lib_url = lib.get("url")
                if lib_url:
                    if not lib_url.startswith(("http://", "https://")):
                        lib_url = "https://openprocessing.org" + ("/" + lib_url.lstrip("/"))
                    json_libs_html += f'<script src="{lib_url}"></script>\n'

        title = sketch_data.get("title", f"op_{sketch_id}")
        
        versions = sketch_data.get("versions", [])
        if not versions or not isinstance(versions, list):
            raise ValueError("此作品中未包含任何版本程式碼。")
            
        v0 = versions[0]
        code_objects = v0.get("codeObjects", [])
        if not code_objects or not isinstance(code_objects, list):
            raise ValueError("此作品中未包含任何程式碼檔案。")
            
        def get_order_id(x):
            val = x.get("orderID")
            if val is None:
                return 0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0
        sorted_objects = sorted(code_objects, key=get_order_id)
        
        custom_css = ""
        custom_html = ""
        html_tab_code = ""
        
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            
            if tab_title.lower().endswith('.css'):
                custom_css += tab_code + "\n"
            elif tab_title.lower().endswith(('.html', '.htm')):
                html_tab_code = tab_code
                body_match = re.search(r'<body[^>]*>(.*?)</body>', tab_code, re.DOTALL | re.IGNORECASE)
                if body_match:
                    custom_html += body_match.group(1) + "\n"
                else:
                    cleaned = re.sub(r'<!DOCTYPE[^>]*>', '', tab_code, flags=re.IGNORECASE)
                    cleaned = re.sub(r'<html[^>]*>', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r'</html>', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r'<head[^>]*>.*?</head>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
                    custom_html += cleaned + "\n"

        custom_html = json_libs_html + ext_script_tags + custom_html

        js_objects = []
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            if tab_title.lower().endswith(('.css', '.html', '.htm', '.txt', '.json', '.glsl', '.vert', '.frag')):
                continue
            js_objects.append(obj)

        # Determine JS execution order from HTML scripts, or fallback
        if html_tab_code:
            # 移除非指令碼 HTML 註解，防範註解掉的 script 標籤誤判
            html_no_comments = re.sub(r'<!--.*?-->', '', html_tab_code, flags=re.DOTALL)
            ordered_js_titles = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html_no_comments, re.IGNORECASE)
            
            loaded_script_names = []
            for src_name in ordered_js_titles:
                fname = src_name.split('/')[-1].lower().strip()
                loaded_script_names.append(fname)
                if fname.endswith('.js'):
                    loaded_script_names.append(fname[:-3])
            
            js_lookup = {}
            for obj in js_objects:
                t = obj.get("title", "").lower().strip()
                js_lookup[t] = obj
                if t.endswith(".js"):
                    js_lookup[t[:-3]] = obj
                else:
                    js_lookup[t + ".js"] = obj

            sorted_js_objects = []
            seen_objs = set()
            for src_name in ordered_js_titles:
                normalized_src = src_name.lower().strip()
                if normalized_src in js_lookup:
                    matching_obj = js_lookup[normalized_src]
                    obj_id = id(matching_obj)
                    if obj_id not in seen_objs:
                        sorted_js_objects.append(matching_obj)
                        seen_objs.add(obj_id)

            # 僅保留明確載入的頁籤或主繪圖頁籤，剔除未在 HTML 中引用的備份 JS 頁籤
            for obj in js_objects:
                if id(obj) not in seen_objs:
                    t = obj.get("title", "").lower().strip()
                    if t in ["mysketch", "mysketch.js", "sketch", "sketch.js", "main", "main.js"]:
                        sorted_js_objects.append(obj)
                        seen_objs.add(id(obj))
        else:
            sorted_js_objects = []
            main_sketches = []
            for obj in js_objects:
                t = obj.get("title", "").lower()
                if t == "mysketch.js" or t == "mysketch":
                    main_sketches.append(obj)
                else:
                    sorted_js_objects.append(obj)
            sorted_js_objects.extend(main_sketches)

        # 確保主繪圖檔 (包含 setup/draw 或是主檔名) 串接在最後，避免 shader/tools 變數先被引用而未初始化
        final_js_objects = []
        main_sketches = []
        for obj in sorted_js_objects:
            t = obj.get("title", "").lower().strip()
            code = obj.get("code", "")
            is_main = (
                t in ["mysketch.js", "mysketch", "sketch.js", "sketch", "main.js", "main"] 
                or "function setup(" in code 
                or "function draw(" in code 
                or "void setup(" in code
            )
            if is_main:
                main_sketches.append(obj)
            else:
                final_js_objects.append(obj)
        final_js_objects.extend(main_sketches)
        sorted_js_objects = final_js_objects

        full_code = ""
        import re
        local_import_pattern = r'(\bimport\s+(?:[^"\']*?)\s+from\s+["\'])(?!https?://)([^"\']+)(["\'])'
        for obj in sorted_js_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            full_code += f"// === Tab: {tab_title} ===\n"
            
            # 註解掉本地模組導入 (例如 import ... from './shaderSource.js')，避免合併後同名宣告衝突
            cleaned_code = re.sub(local_import_pattern, r'// \g<0>', tab_code)
            full_code += cleaned_code
            if not cleaned_code.endswith("\n"):
                full_code += "\n"
            full_code += "\n"
            
        inline_assets = {}
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            if tab_title.lower().endswith(('.glsl', '.vert', '.frag', '.json', '.txt')):
                inline_assets[tab_title] = tab_code

        author = ""
        
        # 1. 優先嘗試從 HTML 的 var user 全域變數中解析 fullname（能精確保留大小寫與符號，如 "Che-Yu Wu"）
        user_json = self.extract_js_object(html, "user")
        if user_json:
            try:
                user_data = json.loads(user_json)
                if isinstance(user_data, dict):
                    author = user_data.get("fullname") or user_data.get("username")
            except Exception:
                pass
                
        # 2. 備用：從 og:title 或 twitter:title 元數據中解析（能非常精確地保留大小寫與符號，如 "Che-Yu Wu"）
        if not author:
            # 優先從 og:title 中解析, 格式一般為: <meta property="og:title" content="[Title] - [Author] - OpenProcessing" />
            og_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            if og_match:
                og_content = og_match.group(1).strip()
                # 移除 " - OpenProcessing" 尾綴
                og_content = re.sub(r'\s*-\s*OpenProcessing\s*$', '', og_content, flags=re.IGNORECASE).strip()
                # 如果還有 " - ", 則最後一部分通常是作者名
                if " - " in og_content:
                    author = og_content.split(" - ")[-1].strip()
            
            if not author:
                tw_match = re.search(r'<meta\s+(?:name|property)=["\']twitter:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
                if tw_match:
                    tw_content = tw_match.group(1).strip()
                    tw_content = re.sub(r'\s*-\s*OpenProcessing\s*$', '', tw_content, flags=re.IGNORECASE).strip()
                    if " - " in tw_content:
                        author = tw_content.split(" - ")[-1].strip()

        # 3. 備用：從 sketch_data 內部 user 對象獲取
        if not author:
            user_info = sketch_data.get("user")
            if isinstance(user_info, dict):
                author = user_info.get("fullname") or user_info.get("username")
                
        # 4. 備用：嘗試直接從 sketch_data 最外層獲取 username
        if not author:
            author = sketch_data.get("username")
            
        # 5. 備用：嘗試從 URL 中解析 @username
        if not author:
            match_at = re.search(r'/@([\w\-]+)/', url)
            if match_at:
                author = match_at.group(1)
                
        # 6. 雙重作者抓取備用方案
        if not author:
            title_match = re.search(r'<title>(.*?) by (.*?)</title>', html, re.IGNORECASE)
            if title_match:
                author = title_match.group(2).strip()
                # 濾除可能的 OpenProcessing 尾綴
                if "openprocessing" in author.lower():
                    author = re.sub(r'\s*-\s*openprocessing.*', '', author, flags=re.IGNORECASE).strip()
                    
        # 確保為字串型態
        author = str(author or "").strip()
            
        license_id = sketch_data.get("license")
        license_map = {
            1: "CC BY",
            2: "CC BY-NC",
            3: "CC BY-NC-ND",
            4: "CC BY-NC-SA",
            5: "CC BY-ND",
            6: "CC BY-SA",
            7: "Public Domain / CC0",
            8: "All Rights Reserved"
        }
        license_name = license_map.get(license_id, f"CC {license_id}" if license_id else "Unknown")

        # 嚴格執行 4K MV 視覺預設模組收錄資格檢測 (排除 攝影機/AR/XR/GAME/高耗時加載)
        from batch_importer import validate_visual_module_eligibility
        tags_list = sketch_data.get("tags", [])
        desc_text = sketch_data.get("description", "")
        is_eligible, reject_reason = validate_visual_module_eligibility(
            title=title,
            code=full_code,
            custom_html=custom_html,
            tags=tags_list,
            desc=desc_text
        )
        if not is_eligible:
            raise ValueError(f"該作品不符合 4K MV 視覺模組收錄標準，已被過濾排除。\n原因: {reject_reason}")

        return title, sketch_id, full_code, custom_css, custom_html, inline_assets, author, license_name, sketch_data.get("fileBase")

# Keywords for static check (fast path)
CONTROL_KEYWORDS_CLEANUP = [
    "createSlider", "createButton", "createCheckbox", "createSelect", "createInput", 
    "createRadio", "dat.GUI", "quicksettings", "lil-gui", "gui.add", "gui.addFolder", 
    "OPC.slider", "OPC.button", "OPC.toggle", "OPC.color", "OPC.text", "dat.gui"
]

TEXT_KEYWORDS_CLEANUP = [
    "textFont", "textSize", "textAlign", "strokeText", "fillText"
]

def make_test_html_cleanup(code, custom_css="", custom_html=""):
    is_module = "import " in code or "export " in code
    script_tag = f'<script type="module">{code}</script>' if is_module else f'<script>{code}</script>'
    
    html_template = """<!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body { margin: 0; overflow: hidden; background: #000; display: flex; justify-content: center; align-items: center; }
        canvas { display: block !important; position: absolute !important; left: 50% !important; top: 50% !important; transform: translate(-50%, -50%) !important; width: 100vw !important; height: 100vh !important; max-width: 100vw !important; max-height: 100vh !important; object-fit: cover !important; }
        CUSTOM_CSS_PLACEHOLDER
        /* Enforce final centering in case custom_css overwrote canvas positioning */
        body canvas {
          position: absolute !important;
          left: 50% !important;
          top: 50% !important;
          transform: translate(-50%, -50%) !important;
          width: 100vw !important;
          height: 100vh !important;
          max-width: 100vw !important;
          max-height: 100vh !important;
          object-fit: cover !important;
        }
        /* 強制隱藏所有 GUI 框架容器與表單控制項 (CSS 層級防護) */
        .dg, .dg.ac, .dg.main, .lil-gui, .qs_main, .opc-control,
        input:not([type="hidden"]), button, select, textarea,
        label, fieldset, legend, output, datalist {
          display: none !important;
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
          position: absolute !important;
          top: -99999px !important;
          left: -99999px !important;
          width: 0px !important;
          height: 0px !important;
          z-index: -99999 !important;
        }
      </style>
      <script>
        (function() {
          const _origWarn = console.warn;
          console.warn = function(...args) {
            if (args[0] && typeof args[0] === 'string' && (args[0].includes('vectors of different sizes') || args[0].includes('linger vector'))) {
              return;
            }
            if (typeof _origWarn === 'function') {
              _origWarn.apply(console, args);
            }
          };
        })();
        window.__textCalled = false;
        window.__controlsCreated = false;
        window.__loadingDetected = false;
        window.__jsErrors = [];
        window.__drawCount = 0;
        window.__setupFinished = false;

        window.onerror = function(message, source, lineno, colno, error) {
          const msgStr = String(message || "");
          if (msgStr.indexOf('vertices') !== -1 || msgStr.indexOf('is not defined') !== -1) {
            console.log('[Ignored non-fatal sandbox error]: ' + msgStr);
            return true; // Ignore this non-fatal error
          }
          window.__jsErrors.push(msgStr + " (Line " + lineno + ")");
          return false;
        };
        window.addEventListener('unhandledrejection', function(event) {
          if (event && typeof event.preventDefault === 'function') {
            event.preventDefault();
          }
          const reason = event.reason ? (event.reason.message || String(event.reason)) : "";
          if (reason && (reason.indexOf('vertices') !== -1 || reason.indexOf('is not defined') !== -1)) {
            console.log('[Ignored non-fatal sandbox rejection]: ' + reason);
            return;
          }
          window.__jsErrors.push("Promise Rejected: " + (reason || "Unknown Error"));
        });

        const origCreateElement = Document.prototype.createElement;
        Document.prototype.createElement = function(tagName) {
          const el = origCreateElement.apply(this, arguments);
          const tag = tagName.toLowerCase();
          if (['input', 'button', 'select', 'textarea'].includes(tag)) {
            window.__controlsCreated = true;
            // 隱藏控制項 DOM 元素，而非刪除模組
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
            el.style.setProperty('opacity', '0', 'important');
            el.style.setProperty('pointer-events', 'none', 'important');
            el.style.setProperty('position', 'absolute', 'important');
            el.style.setProperty('top', '-99999px', 'important');
            el.style.setProperty('left', '-99999px', 'important');
            el.style.setProperty('width', '0px', 'important');
            el.style.setProperty('height', '0px', 'important');
            el.style.setProperty('z-index', '-99999', 'important');
          }
          return el;
        };

        // Smart unrelated text filter (與 code_injector.py 同步)
        window.__isUnrelatedVisualText = function(content) {
          if (content === null || content === undefined) return false;
          let str = String(content).trim();
          if (!str || str.length === 0) return false;
          if (/^(?:fps|framerate|frame\s*rate)\s*[:=]?\s*[\d\.]*/i.test(str)) return true;
          if (/^[\d\.]+\s*fps\b/i.test(str)) return true;
          if (/^fps\s*$/i.test(str)) return true;
          if (/^loading(?:\s*[\.\w]*)?$/i.test(str)) return true;
          if (/^please\s+wait/i.test(str)) return true;
          if (/^esperando\b/i.test(str)) return true;
          if (/(?:drag\s+wind|tap\s+to|click\s+to|press\s+['"\\w]|hit\s+space|arrow\s+keys|use\s+mouse|hold\s+mouse|scroll\s+to|snapshot|screenshot|save\s+image|controls?|instructions?|touch\s+to\s+start|press\s+any\s+key)/i.test(str)) return true;
          if (/^(?:speed|size|radius|color|count|frequency|volume|threshold|density|scale|zoom|particles|nodes|iteration|gravity|damping)\s*[:=]\s*[-+]?[\d\.]+/i.test(str)) return true;
          if (/^(?:by\s+[\w\s]+|author\s*:|code\s+by|created\s+by|designed\s+by|copyright|©|\(c\))\b/i.test(str)) return true;
          return false;
        };

        const origFillText = (typeof CanvasRenderingContext2D !== 'undefined') ? CanvasRenderingContext2D.prototype.fillText : null;
        if (origFillText) {
          CanvasRenderingContext2D.prototype.fillText = function() {
            window.__textCalled = true;
            if (arguments.length > 0) {
              const str = arguments[0];
              if (typeof str === 'string' && /loading/i.test(str)) {
                window.__loadingDetected = true;
              }
              // 隱藏無關文字而非刪除模組
              if (window.__isUnrelatedVisualText(str)) return;
            }
            return origFillText.apply(this, arguments);
          };
        }
        const origStrokeText = (typeof CanvasRenderingContext2D !== 'undefined') ? CanvasRenderingContext2D.prototype.strokeText : null;
        if (origStrokeText) {
          CanvasRenderingContext2D.prototype.strokeText = function() {
            window.__textCalled = true;
            if (arguments.length > 0) {
              const str = arguments[0];
              if (typeof str === 'string' && /loading/i.test(str)) {
                window.__loadingDetected = true;
              }
              // 隱藏無關文字而非刪除模組
              if (window.__isUnrelatedVisualText(str)) return;
            }
            return origStrokeText.apply(this, arguments);
          };
        }
      </script>
      <script src="custom_visuals/libs/p5.min.js"></script>
      <script>
        if (typeof p5 !== 'undefined' && p5.prototype) {
          // Preload watchdog: auto unstick if loading stalls > 1.2s
          setTimeout(function() {
            if (window._p5Instance && window._p5Instance._preloadCount > 0) {
              console.log('[Preload Watchdog] Force unstuck preloadCount:', window._p5Instance._preloadCount);
              window._p5Instance._preloadCount = 0;
              if (typeof window._p5Instance._setup === 'function') window._p5Instance._setup();
              else if (typeof window.setup === 'function') window.setup();
            }
          }, 1200);

          // Robust fallback for loadImage
          const _origLoadImage = p5.prototype.loadImage;
          p5.prototype.loadImage = function(path, successCallback, failureCallback) {
            const dummyImg = {
              width: 400, height: 400,
              loadPixels: function() {},
              updatePixels: function() {},
              get: function(x, y, w, h) { return [128, 128, 200, 255]; },
              set: function() {},
              resize: function() {},
              mask: function() {},
              filter: function() {},
              copy: function() {},
              canvas: document.createElement('canvas'),
              elt: document.createElement('canvas')
            };
            if (_origLoadImage) {
              try {
                const res = _origLoadImage.call(this, path, successCallback, function(err) {
                  if (typeof failureCallback === 'function') failureCallback(err);
                  else if (typeof successCallback === 'function') successCallback(dummyImg);
                });
                return res || dummyImg;
              } catch(e) {
                if (typeof successCallback === 'function') successCallback(dummyImg);
                return dummyImg;
              }
            }
            if (typeof successCallback === 'function') successCallback(dummyImg);
            return dummyImg;
          };

          // Robust fallback for loadFont
          const _origLoadFont = p5.prototype.loadFont;
          p5.prototype.loadFont = function(path, onSuccess, onError) {
            const dummyFont = { font: { unitsPerEm: 1000 }, textBounds: function() { return { x:0, y:0, w:100, h:20 }; } };
            if (_origLoadFont) {
              try {
                return _origLoadFont.call(this, path, onSuccess, function(err) {
                  if (onError) onError(err);
                  else if (onSuccess) onSuccess(dummyFont);
                }) || dummyFont;
              } catch(e) { if (onSuccess) onSuccess(dummyFont); return dummyFont; }
            }
            if (onSuccess) onSuccess(dummyFont);
            return dummyFont;
          };

          // Robust fallback for loadSound
          const _origLoadSound = p5.prototype.loadSound;
          p5.prototype.loadSound = function(path, onSuccess, onError) {
            const dummySound = {
              play: function() {}, stop: function() {}, loop: function() {}, pause: function() {},
              isPlaying: function() { return false; }, setVolume: function() {}, rate: function() {},
              duration: function() { return 10; }, currentTime: function() { return 0; }
            };
            if (onSuccess) setTimeout(function() { onSuccess(dummySound); }, 10);
            return dummySound;
          };

          const origSetup = p5.prototype.setup;
          p5.prototype.setup = function() {
            window.__setupFinished = true;
            window._p5Instance = this; // Capture the active instance for the fallback wrapper
            if (origSetup) {
              return origSetup.apply(this, arguments);
            }
          };

          const origDraw = p5.prototype.draw;
          p5.prototype.draw = function() {
            window.__drawCount = (window.__drawCount || 0) + 1;
            window._p5Instance = this; // Keep active instance updated
            if (origDraw) {
              return origDraw.apply(this, arguments);
            }
          };

          const origProtoText = p5.prototype.text;
          p5.prototype.text = function() {
            window.__textCalled = true;
            if (arguments.length > 0) {
              const str = arguments[0];
              if (typeof str === 'string' && /loading/i.test(str)) {
                window.__loadingDetected = true;
              }
              // 隱藏無關文字而非刪除模組
              if (window.__isUnrelatedVisualText(str)) return this;
            }
            if (origProtoText) {
              return origProtoText.apply(this, arguments);
            }
          };

          // ─── 音訊驅動隱藏控制項 (與 code_injector.py createDummyDom 同步) ───
          window._activeMockButtons = window._activeMockButtons || [];
          window.audioLow = 0.5;
          window.audioMid = 0.5;
          window.audioHigh = 0.5;
          window.beatEnergy = 0.5;
          window.isBeat = false;
          window.custom_time_ms = 0;

          function _createHiddenDummyDom(tag, ...createArgs) {
            let realTag = (tag === 'slider' || tag === 'colorpicker' || tag === 'checkbox' || tag === 'radio') ? 'input' : (tag || 'div');
            let dummyEl = document.createElement(realTag);
            dummyEl.style.setProperty('display', 'none', 'important');
            dummyEl.style.setProperty('visibility', 'hidden', 'important');
            dummyEl.style.setProperty('opacity', '0', 'important');
            dummyEl.style.setProperty('pointer-events', 'none', 'important');
            dummyEl.style.setProperty('position', 'absolute', 'important');
            dummyEl.style.setProperty('top', '-99999px', 'important');
            dummyEl.style.setProperty('left', '-99999px', 'important');
            dummyEl.style.setProperty('width', '0px', 'important');
            dummyEl.style.setProperty('height', '0px', 'important');
            dummyEl.style.setProperty('z-index', '-99999', 'important');

            dummyEl.elt = dummyEl;
            dummyEl.class = function() { return this; };
            let dummyIdVal = '';
            dummyEl.id = function(val) { if(val === undefined) return dummyIdVal; dummyIdVal = String(val); return dummyEl; };
            dummyEl.parent = function() { return this; };
            dummyEl.position = function() { return this; };
            dummyEl.size = function() { return this; };
            dummyEl.style = function() { return this; };
            dummyEl.show = function() { return this; };
            dummyEl.hide = function() { return this; };
            dummyEl.html = function() { return this; };
            dummyEl.attribute = function() { return this; };
            dummyEl.removeAttribute = function() { return this; };
            dummyEl.input = function(cb) { return this; };
            dummyEl.changed = function(cb) { return this; };

            if (tag === 'slider') {
              let minVal = createArgs[0] !== undefined ? createArgs[0] : 0;
              let maxVal = createArgs[1] !== undefined ? createArgs[1] : 100;
              let stepVal = createArgs[3] !== undefined ? createArgs[3] : 0;
              const channels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
              let boundProperty = channels[Math.floor(Math.random() * channels.length)];
              let phase = Math.random() * 6.28;
              let spd = 0.5 + Math.random() * 1.5;
              dummyEl.value = function(val) {
                if (val !== undefined) return this;
                let t = (window.custom_time_ms || Date.now()) * 0.001;
                let norm = window[boundProperty] || 0.5;
                let wave = 0.5 + 0.3 * Math.sin(t * spd + phase) + (norm - 0.5) * 0.4;
                wave = Math.max(0, Math.min(1, wave));
                let res = minVal + wave * (maxVal - minVal);
                if (stepVal > 0) res = Math.round((res - minVal) / stepVal) * stepVal + minVal;
                return res;
              };
            } else if (tag === 'checkbox') {
              dummyEl.checked = function(val) {
                if (val !== undefined) return this;
                return (window.audioLow || 0.5) > 0.48 || (window.isBeat || false);
              };
              dummyEl.value = function(val) { return dummyEl.checked(val); };
            } else if (tag === 'button') {
              dummyEl._callbacks = [];
              dummyEl.mousePressed = function(cb) {
                if (typeof cb === 'function') dummyEl._callbacks.push(cb);
                if (!window._activeMockButtons.includes(dummyEl)) window._activeMockButtons.push(dummyEl);
                return this;
              };
              dummyEl.mouseClicked = dummyEl.mousePressed;
              dummyEl.value = function() { return 1; };
            } else if (tag === 'select') {
              dummyEl._options = [];
              dummyEl.option = function(name, val) {
                dummyEl._options.push(val !== undefined ? val : name);
                return dummyEl;
              };
              dummyEl.selected = function(val) {
                if (val !== undefined) return this;
                if (dummyEl._options.length === 0) return '';
                let idx = Math.floor((window.audioMid || 0.5) * dummyEl._options.length) % dummyEl._options.length;
                return dummyEl._options[idx];
              };
              dummyEl.value = dummyEl.selected;
            } else {
              dummyEl.value = function(val) { if(val === undefined) return "0.5"; return this; };
            }

            if (document.body) document.body.appendChild(dummyEl);
            return dummyEl;
          }

          // 音訊時鐘
          function _audioTick() {
            window.custom_time_ms = Date.now();
            if (window.beatEnergy > 0) window.beatEnergy *= 0.92;
            window.audioLow = 0.3 + 0.4 * Math.sin(Date.now() * 0.006);
            window.audioMid = 0.3 + 0.3 * Math.sin(Date.now() * 0.008);
            window.audioHigh = 0.2 + 0.4 * Math.sin(Date.now() * 0.012);
            requestAnimationFrame(_audioTick);
          }
          requestAnimationFrame(_audioTick);

          // 覆蓋 p5 的控制項建立函數，改用隱藏 + 音訊驅動
          window.__controlsCreated = window.__controlsCreated || false;
          p5.prototype.createSlider = function() { window.__controlsCreated = true; return _createHiddenDummyDom('slider', ...arguments); };
          p5.prototype.createButton = function() { window.__controlsCreated = true; return _createHiddenDummyDom('button', ...arguments); };
          p5.prototype.createInput = function() { window.__controlsCreated = true; return _createHiddenDummyDom('input', ...arguments); };
          p5.prototype.createCheckbox = function() { window.__controlsCreated = true; return _createHiddenDummyDom('checkbox', ...arguments); };
          p5.prototype.createSelect = function() { window.__controlsCreated = true; return _createHiddenDummyDom('select', ...arguments); };
          p5.prototype.createRadio = function() { window.__controlsCreated = true; return _createHiddenDummyDom('radio', ...arguments); };
          p5.prototype.createColorPicker = function() { window.__controlsCreated = true; return _createHiddenDummyDom('colorpicker', ...arguments); };
          p5.prototype.createP = function() { return _createHiddenDummyDom('p', ...arguments); };
          p5.prototype.createDiv = function() { return _createHiddenDummyDom('div', ...arguments); };
          p5.prototype.createSpan = function() { return _createHiddenDummyDom('span', ...arguments); };
          // 全域函數同步
          window.createSlider = p5.prototype.createSlider;
          window.createButton = p5.prototype.createButton;
          window.createInput = p5.prototype.createInput;
          window.createCheckbox = p5.prototype.createCheckbox;
          window.createSelect = p5.prototype.createSelect;
          window.createRadio = p5.prototype.createRadio;
          window.createColorPicker = p5.prototype.createColorPicker;
          window.createP = p5.prototype.createP;
          window.createDiv = p5.prototype.createDiv;
          window.createSpan = p5.prototype.createSpan;
        }
      </script>
      <script>{P5_V2_COMPAT_SHIM}</script>
      <script src="custom_visuals/libs/p5.sound.min.js"></script>
      <script src="custom_visuals/libs/p5.func.min.js"></script>
      <script src="custom_visuals/libs/gsap.min.js"></script>
      <script src="custom_visuals/libs/p5.flex.min.js"></script>
      <script src="custom_visuals/libs/rampensau.js"></script>
      <script src="custom_visuals/libs/chroma.min.js"></script>
      <script>
        // Audio Mock & OPC Mock (防止 connect/disconnect 錯誤和 OPC 未定義)
        AUDIO_MOCK_PLACEHOLDER
        if (typeof OPC === 'undefined') {
          const _opcHandler = {
            get: function(target, prop) {
              if (prop in target) return target[prop];
              if (['slider', 'toggle', 'color', 'select', 'text', 'palette', 'range'].includes(prop)) {
                return function(name, value) {
                  if (name && typeof value !== 'undefined' && typeof window[name] === 'undefined') {
                    window[name] = value;
                  }
                  return window.OPC;
                };
              }
              return function() { return window.OPC; };
            }
          };
          window.OPC = new Proxy({
            slider: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
            button: function() { return window.OPC; },
            toggle: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
            color: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
            select: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
            text: function(name, value) { if (name && typeof value !== 'undefined') window[name] = value; return window.OPC; },
            title: function() { return window.OPC; },
            header: function() { return window.OPC; },
            separator: function() { return window.OPC; },
            collapsed: function() { return window.OPC; },
            bezier: function() { return window.OPC; },
            setGlobal: function(name, value) { if (name) window[name] = value; }
          }, _opcHandler);
        }
      </script>
      <script>
        // Periodically check DOM for control elements and loading text, and hide them
        setInterval(function() {
          const selectors = ['input', 'button', 'select', 'textarea', '.dg', '.lil-gui', '.qs_main', '.opc-control'];
          for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
              window.__controlsCreated = true;
              els.forEach(function(el) {
                // 只隱藏非 canvas 的控制項，避免誤傷畫布
                if (el.tagName !== 'CANVAS') {
                  el.style.setProperty('display', 'none', 'important');
                  el.style.setProperty('visibility', 'hidden', 'important');
                  el.style.setProperty('pointer-events', 'none', 'important');
                  el.style.setProperty('position', 'absolute', 'important');
                  el.style.setProperty('top', '-99999px', 'important');
                  el.style.setProperty('left', '-99999px', 'important');
                  el.style.setProperty('width', '0px', 'important');
                  el.style.setProperty('height', '0px', 'important');
                }
              });
            }
          }
          if (document.body && /loading/i.test(document.body.innerText)) {
            window.__loadingDetected = true;
          }
        }, 100);
      </script>
    </head>
    <body>
      CUSTOM_HTML_PLACEHOLDER
      SCRIPT_TAG_PLACEHOLDER
    </body>
    </html>"""
    
    return html_template.replace("CUSTOM_CSS_PLACEHOLDER", custom_css)\
                        .replace("CUSTOM_HTML_PLACEHOLDER", custom_html)\
                        .replace("SCRIPT_TAG_PLACEHOLDER", f"<script>{OVERRIDE_16_9_JS}</script>\n" + script_tag)\
                        .replace("AUDIO_MOCK_PLACEHOLDER", MOCK_NATIVE_AUDIO_JS + "\n" + MOCK_P5_JS)\
                        .replace("{P5_V2_COMPAT_SHIM}", P5_V2_COMPAT_SHIM)


class DependencyDownloaderThread(QThread):
    log_signal = pyqtSignal(str, bool)      # message, is_err
    progress_signal = pyqtSignal(int, int)  # current, total
    finished_signal = pyqtSignal(int, int)  # success_count, failed_count
    
    def __init__(self, custom_visuals_dir, cache_dir, known_libraries):
        super().__init__()
        self.custom_visuals_dir = custom_visuals_dir
        self.cache_dir = cache_dir
        self.known_libraries = known_libraries
        
    def run(self):
        import re
        import json
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # 1. Gather all JS URLs
        all_js_urls = set()
        for lib_url in self.known_libraries.values():
            all_js_urls.add(lib_url)
            
        assets_to_download = []  # items: (url, local_path, display_name)
        
        if os.path.exists(self.custom_visuals_dir):
            for file in os.listdir(self.custom_visuals_dir):
                if file.endswith(".json"):
                    path = os.path.join(self.custom_visuals_dir, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        # Extract JS libraries
                        custom_html = data.get("custom_html", "")
                        js_matches = re.findall(r'src=["\'](https?://[^"\']+)["\']', custom_html, re.IGNORECASE)
                        for m in js_matches:
                            all_js_urls.add(m.strip())
                            
                        # Extract Assets (images, fonts, sounds, models)
                        code = data.get("code", "")
                        url = data.get("url", "")
                        
                        sketch_id = None
                        if url:
                            id_match = re.search(r'/(?:sketch|@[\w\d]+/.*?)/(\d+)', url)
                            if not id_match:
                                id_match = re.search(r'/(\d{5,8})(?:\?|$)', url)
                            if id_match:
                                sketch_id = id_match.group(1)
                                
                        if sketch_id:
                            # 優先使用 presets 保存的 file_base，若無則構造預設 fileBase 靜態 CDN 路徑以防 404
                            file_base = data.get("file_base") or f"https://openprocessing.org/usercontent/sketches/localAssets/{sketch_id}/"
                            if not file_base.endswith("/"):
                                file_base += "/"
                            
                            check_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
                            check_code = re.sub(r'//.*', '', check_code)
                            
                            # Regex to match image, font, audio, and model asset files
                            asset_pattern = r'["\'`]([^"\'`\s]+?\.(?:png|jpg|jpeg|gif|svg|ttf|otf|woff|woff2|mp3|wav|ogg|obj|fbx|gltf|glb))["\'`]'
                            asset_names = list(set(re.findall(asset_pattern, check_code)))
                            
                            for asset in asset_names:
                                clean_asset = asset.lstrip("./")
                                if clean_asset.startswith(("http://", "https://", "data:")):
                                    continue
                                if "#" in clean_asset or "${" in clean_asset or "{" in clean_asset or "}" in clean_asset or "(" in clean_asset or ")" in clean_asset:
                                    continue
                                    
                                local_asset_path = os.path.join(self.custom_visuals_dir, "assets", sketch_id, clean_asset)
                                if not os.path.exists(local_asset_path) or os.path.getsize(local_asset_path) == 0:
                                    asset_download_url = file_base + clean_asset
                                    assets_to_download.append((asset_download_url, local_asset_path, f"{sketch_id}/{clean_asset}"))
                    except Exception:
                        pass
                        
        # 2. Check JS cache
        js_to_download = []
        for url in all_js_urls:
            filename = url.split("/")[-1]
            if "?" in filename:
                filename = filename.split("?")[0]
            if not filename.endswith(".js"):
                filename = f"custom_lib_{abs(hash(url))}.js"
            local_path = os.path.join(self.cache_dir, filename)
            if not os.path.exists(local_path) or os.path.getsize(local_path) < 1024:
                js_to_download.append((url, local_path, filename))
                
        # Combine all downloads
        download_queue = js_to_download + assets_to_download
        total = len(download_queue)
        
        if total == 0:
            self.log_signal.emit("🎉 所有視覺模組所需的本地元件、圖片、字型已全數補齊，無需下載！", False)
            self.progress_signal.emit(100, 100)
            self.finished_signal.emit(0, 0)
            return
            
        self.log_signal.emit(f"⏳ 發現 {len(js_to_download)} 個 JS 庫，{len(assets_to_download)} 個資產檔 (圖片/字型) 缺失。開始多執行緒下載...", False)
        
        success_count = 0
        failed_count = 0
        current = 0
        
        def download_item(url, local_path, display_name):
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    with open(local_path, "wb") as f:
                        f.write(response.read())
                return url, True, display_name, None
            except Exception as e:
                return url, False, display_name, str(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(download_item, url, path, name): url for url, path, name in download_queue}
            for future in as_completed(futures):
                url = futures[future]
                current += 1
                self.progress_signal.emit(current, total)
                try:
                    url, success, display_name, err_msg = future.result()
                    if success:
                        self.log_signal.emit(f"  [+] 下載成功: {display_name}", False)
                        success_count += 1
                    else:
                        self.log_signal.emit(f"  [x] 下載失敗 ({err_msg}): {url}", True)
                        failed_count += 1
                except Exception as exc:
                    self.log_signal.emit(f"  [x] 任務異常: {url} ({exc})", True)
                    failed_count += 1
                    
        self.finished_signal.emit(success_count, failed_count)


class DependencyDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("📥 下載所有模組本地依賴庫與資產")
        self.resize(750, 480)
        self.setStyleSheet("""
            QDialog { background-color: #0b0b0e; color: #e4e4e7; }
            QLabel { font-family: 'Outfit', 'Inter', sans-serif; color: #f4f4f5; font-size: 13px; }
            QTextEdit { background-color: #09090b; color: #10b981; border: 1px solid #27272a; border-radius: 8px; font-family: 'Courier New'; font-size: 11px; }
            QProgressBar { border: 1px solid #27272a; border-radius: 6px; text-align: center; background-color: #18181b; color: #ffffff; font-weight: bold; }
            QProgressBar::chunk { background-color: #10b981; border-radius: 5px; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_close { background-color: #27272a; color: #ffffff; }
        """)
        
        layout = QVBoxLayout(self)
        
        self.info_label = QLabel("正在初始化掃描...", self)
        layout.addWidget(self.info_label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.console_log = QTextEdit(self)
        self.console_log.setReadOnly(True)
        layout.addWidget(self.console_log)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_action = QPushButton("開始下載", self)
        self.btn_action.clicked.connect(self.start_download)
        btn_layout.addWidget(self.btn_action)
        
        self.btn_close = QPushButton("關閉", self)
        self.btn_close.setObjectName("btn_close")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        
        self.thread = None
        self.is_running = False
        
        # Auto scan on open
        QTimer.singleShot(200, self.scan_libraries)
        
    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#10b981"
        self.console_log.append(f"<span style='color: {color};'>{text}</span>")
        self.console_log.moveCursor(QTextCursor.MoveOperation.End)
        
    def scan_libraries(self):
        custom_visuals_dir = os.path.join(workspace_dir, "custom_visuals")
        cache_dir = os.path.join(workspace_dir, "js_cache")
        
        # Scan and count
        all_urls = set()
        combined_libs = {}
        if self.parent_window:
            combined_libs.update(self.parent_window.KNOWN_LIBRARIES)
            
        libraries_preload = {
            "p5.min.js": "https://cdn.jsdelivr.net/npm/p5@2.3.0/lib/p5.min.js",
            "p5.sound.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js",
            "p5.func.min.js": "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js",
            "gsap.min.js": "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
            "opc.min.js": "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js",
            "p5.flex.min.js": "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js",
            "rampensau.min.js": "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js",
            "chroma.min.js": "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js",
            "Tone.min.js": "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js",
            "polybool.min.js": "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js"
        }
        for k, v in libraries_preload.items():
            combined_libs[k] = v
            
        for lib_url in combined_libs.values():
            all_urls.add(lib_url)
            
        json_count = 0
        assets_to_download_count = 0
        if os.path.exists(custom_visuals_dir):
            import re
            for file in os.listdir(custom_visuals_dir):
                if file.endswith(".json"):
                    json_count += 1
                    path = os.path.join(custom_visuals_dir, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        custom_html = data.get("custom_html", "")
                        matches = re.findall(r'src=["\'](https?://[^"\']+)["\']', custom_html, re.IGNORECASE)
                        for m in matches:
                            all_urls.add(m.strip())
                            
                        # Assets scan
                        code = data.get("code", "")
                        url = data.get("url", "")
                        sketch_id = None
                        if url:
                            id_match = re.search(r'/(?:sketch|@[\w\d]+/.*?)/(\d+)', url)
                            if not id_match:
                                id_match = re.search(r'/(\d{5,8})(?:\?|$)', url)
                            if id_match:
                                sketch_id = id_match.group(1)
                                
                        if sketch_id:
                            check_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
                            check_code = re.sub(r'//.*', '', check_code)
                            asset_pattern = r'["\'`]([^"\'`\s]+?\.(?:png|jpg|jpeg|gif|svg|ttf|otf|woff|woff2|mp3|wav|ogg|obj|fbx|gltf|glb))["\'`]'
                            asset_names = list(set(re.findall(asset_pattern, check_code)))
                            for asset in asset_names:
                                clean_asset = asset.lstrip("./")
                                if clean_asset.startswith(("http://", "https://", "data:")):
                                    continue
                                local_asset_path = os.path.join(custom_visuals_dir, "assets", sketch_id, clean_asset)
                                if not os.path.exists(local_asset_path):
                                    assets_to_download_count += 1
                    except Exception:
                        pass
                        
        urls_to_download = []
        for url in all_urls:
            filename = url.split("/")[-1]
            if "?" in filename:
                filename = filename.split("?")[0]
            if not filename.endswith(".js"):
                filename = f"custom_lib_{abs(hash(url))}.js"
            local_path = os.path.join(cache_dir, filename)
            if not os.path.exists(local_path):
                urls_to_download.append(url)
                
        total_missing = len(urls_to_download) + assets_to_download_count
        self.info_label.setText(f"掃描完成！共偵測到 {json_count} 個模組，其中有 {total_missing} 個缺失元件與資產待下載。")
        self.log_to_console(f"🔍 掃描結果：缺失 JS 庫 {len(urls_to_download)} 個，缺失外部資產 (圖片/字型) {assets_to_download_count} 個。")
        if total_missing == 0:
            self.btn_action.setEnabled(False)
            self.btn_action.setText("已全數本地化")
        else:
            self.btn_action.setEnabled(True)
            self.btn_action.setText("開始下載")

    def start_download(self):
        if self.is_running:
            return
            
        self.is_running = True
        self.btn_action.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.progress_bar.setValue(0)
        
        custom_visuals_dir = os.path.join(workspace_dir, "custom_visuals")
        cache_dir = os.path.join(workspace_dir, "js_cache")
        
        combined_libs = {}
        if self.parent_window:
            combined_libs.update(self.parent_window.KNOWN_LIBRARIES)
            
        libraries_preload = {
            "p5.min.js": "https://cdn.jsdelivr.net/npm/p5@2.3.0/lib/p5.min.js",
            "p5.sound.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js",
            "p5.func.min.js": "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js",
            "gsap.min.js": "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
            "opc.min.js": "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js",
            "p5.flex.min.js": "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js",
            "rampensau.min.js": "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js",
            "chroma.min.js": "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js",
            "Tone.min.js": "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js",
            "polybool.min.js": "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js"
        }
        for k, v in libraries_preload.items():
            combined_libs[k] = v
            
        self.thread = DependencyDownloaderThread(custom_visuals_dir, cache_dir, combined_libs)
        self.thread.log_signal.connect(self.log_to_console)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()
        
    def update_progress(self, current, total):
        self.info_label.setText(f"正在下載中... 進度: {current}/{total}")
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            
    def on_finished(self, success_count, failed_count):
        self.is_running = False
        self.btn_action.setEnabled(True)
        self.btn_close.setEnabled(True)
        self.btn_action.setText("重新掃描")
        try:
            self.btn_action.clicked.disconnect()
        except:
            pass
        self.btn_action.clicked.connect(self.scan_libraries)
        self.info_label.setText("下載任務結束！")



class ModuleCleanupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("🧹 視覺模組庫試運行與篩選清理")
        self.resize(750, 450)
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Inter', sans-serif; font-size: 13px; }
            QProgressBar {
                border: 1px solid #27272a; border-radius: 6px; text-align: center;
                background-color: #18181b; color: #f4f4f5; height: 20px; font-weight: bold;
            }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 5px; }
            QTextEdit {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; font-family: 'Courier New', monospace; font-size: 12px;
            }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_start { background-color: #7c3aed; border-color: #7c3aed; color: #ffffff; }
            QPushButton#btn_start:hover { background-color: #8b5cf6; }
        """)

        layout = QVBoxLayout(self)
        
        desc = QLabel("此常駐工具將會逐一對 `custom_visuals` 資料夾內的所有視覺模組進行試運行：\n"
                      "1. 自動過濾並刪除程式碼錯誤的模組\n"
                      "2. 自動隱藏畫面上的拉桿、按鈕等控制項 (DOM / OPC GUI)，改由音訊特徵驅動控制值\n"
                      "3. 自動隱藏與模組視覺表現無關的文字顯示 (Canvas text 或 loading 字樣)\n"
                      "4. 系統將自動在 op_import_errors.txt 記錄清理日誌。", self)
        layout.addWidget(desc)

        # 🔍 指定 TAG 過濾行
        filter_box = QHBoxLayout()
        filter_lbl = QLabel("🏷️ 指定要清理的 TAG (選填，如 'Uncler M'，留空代表清理所有):", self)
        self.cleanup_tag_input = QLineEdit(self)
        self.cleanup_tag_input.setPlaceholderText("例如: Uncler M")
        self.cleanup_tag_input.setStyleSheet("background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; padding: 6px; border-radius: 6px;")
        filter_box.addWidget(filter_lbl)
        filter_box.addWidget(self.cleanup_tag_input)
        layout.addLayout(filter_box)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        layout.addWidget(self.console)
        
        btn_box = QHBoxLayout()
        self.btn_start = QPushButton("開始清理", self)
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self.start_cleanup)
        
        self.btn_cancel = QPushButton("中止", self)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_cleanup)
        
        self.btn_close = QPushButton("關閉", self)
        self.btn_close.clicked.connect(self.close)
        
        btn_box.addWidget(self.btn_start)
        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_close)
        layout.addLayout(btn_box)

        self.files_to_test = []
        self.results = []
        self.current_idx = 0
        self.view = None
        self.view_crashed = False
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.evaluate_next)
        self.current_errors = []
        self.is_cancelled = False
        
        self.clipper = QWidget(self)
        self.clipper.setGeometry(-1000, -1000, 300, 300)
        self.clipper.show()

    def log(self, text, is_err=False):
        color = "#ef4444" if is_err else "#10b981" if "SUCCESS" in text or "✅" in text or "保留" in text else "#f4f4f5"
        self.console.append(f'<span style="color:{color};">{text}</span>')
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        QApplication.processEvents()

    def start_cleanup(self):
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        if not os.path.exists(save_dir):
            self.log("❌ custom_visuals 目錄不存在，無法進行清理！", True)
            return

        all_files = [f for f in os.listdir(save_dir) if f.endswith(".json")]
        all_files.sort()
        
        # 🏷️ TAG 篩選過濾：如果輸入框內有指定 TAG，僅試運行對應標籤的模組
        filter_tag = self.cleanup_tag_input.text().strip().lower()
        if filter_tag:
            self.log(f"🏷️ 僅對標記有 Tag「{self.cleanup_tag_input.text().strip()}」的模組進行清理篩選...")
            self.files_to_test = []
            for f in all_files:
                fpath = os.path.join(save_dir, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as json_in:
                        meta = json.load(json_in)
                    tags = [t.lower() for t in meta.get("tags", [])]
                    if filter_tag in tags:
                        self.files_to_test.append(f)
                except Exception:
                    pass
        else:
            self.files_to_test = all_files

        if not self.files_to_test:
            self.log("ℹ️ 視覺預設模組庫中無任何匹配所選 TAG 的模組需要清理！")
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.btn_close.setEnabled(True)
            return

        self.log(f"🚀 開始對 {len(self.files_to_test)} 個視覺模組進行試運行與篩選清理...")
        self.progress_bar.setRange(0, len(self.files_to_test))
        self.progress_bar.setValue(0)
        
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_close.setEnabled(False)
        
        self.current_idx = 0
        self.results = []
        self.is_cancelled = False
        
        self.timer.start(100)

    def cancel_cleanup(self):
        self.is_cancelled = True
        self.log("⚠️ 正在中止清理程序...", True)

    def handle_console_msg(self, level, message, line_num):
        msg_lower = message.lower()
        # ── 過濾已知的非致命環境錯誤（與 TestRunDialog.handle_js_log 同步）──
        if "failed to fetch" in msg_lower or "audiocontext" in msg_lower or "cors" in msg_lower:
            return
        if "[mock]" in msg_lower or "[loadingwatchdog]" in msg_lower or "audio decoding failed" in msg_lower:
            return
        if "dummy silent buffer" in msg_lower or "decodeaudiodata" in msg_lower:
            return
        if "[preloadguard]" in msg_lower or "[object event]" in msg_lower:
            return
        if "p5.sound" in msg_lower or "p5.min.js" in msg_lower:
            return
        if "opentype" in msg_lower or ".ttf" in msg_lower or ".otf" in msg_lower or ".woff" in msg_lower:
            return
        if "width or height of 0" in msg_lower or "drawimage" in msg_lower:
            return
        if message.strip() in ("[object Event]", "[object ErrorEvent]"):
            return
        if "mime type" in msg_lower or "refused to execute script" in msg_lower or "net::err" in msg_lower:
            return
        # WebGL shader 錯誤（沙盒 GPU 限制）
        if "useprogram" in msg_lower or "webglprogram" in msg_lower or "webgl" in msg_lower:
            return
        if "ensurecompiledoncontext" in msg_lower or "shader" in msg_lower:
            return
        # 缺少外部庫（模組依賴，非我們的問題）
        if any(lib in msg_lower for lib in ["ml5 is not defined", "tone is not defined", "simplex",
                "lil is not defined", "resolvelygia", "svgfont", "opc' has already been declared",
                "matter is not defined", "dat is not defined"]):
            return
        # p5.js DOM 元素方法混淆
        if ".createcanvas is not a function" in msg_lower:
            return
        # JSON/HTML 解析錯誤
        if "is not valid json" in msg_lower and "unexpected token '<'" in msg_lower:
            return
        # 音訊初始化 connect/disconnect（Line 1-2）
        if ("connect" in msg_lower or "disconnect" in msg_lower) and line_num <= 2:
            return
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        if is_err or "uncaught" in msg_lower or "is not defined" in msg_lower or "unexpected token" in msg_lower or "cannot read properties" in msg_lower:
            self.current_errors.append(f"JS Error (Line {line_num}): {message}")

    def evaluate_next(self):
        if self.is_cancelled:
            self.finish_cleanup()
            return

        if self.current_idx >= len(self.files_to_test):
            self.finish_cleanup()
            return

        save_dir = os.path.join(workspace_dir, "custom_visuals")
        filename = self.files_to_test[self.current_idx]
        file_path = os.path.join(save_dir, filename)
        name = filename[:-5]
        
        self.progress_bar.setValue(self.current_idx)
        self.log(f"⌛ [{self.current_idx+1}/{len(self.files_to_test)}] 正在評估: {name} ...")
        
        # 檔案大小安全閥限制（避免加載過大 JSON 導致 Python 解析或 WebEngine 載入時記憶體崩潰卡死）
        try:
            file_size_kb = os.path.getsize(file_path) / 1024.0
            if file_size_kb > 500.0:  # 超過 500KB
                self.results.append({
                    "name": name,
                    "file_path": file_path,
                    "status": "delete",
                    "reason": f"檔案過大 ({file_size_kb:.1f}KB)，不相容收編"
                })
                self.log(f"   🗑️ 已標記刪除: 檔案過大 ({file_size_kb:.1f}KB)")
                self.current_idx += 1
                self.timer.start(10)
                return
        except Exception as size_err:
            print(f"檢查檔案大小出錯: {size_err}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.log(f"   ❌ JSON 解析失敗 {filename}: {e}", True)
            self.results.append({
                "name": name,
                "file_path": file_path,
                "status": "delete",
                "reason": f"JSON Parsing Error: {e}"
            })
            self.current_idx += 1
            self.timer.start(10)
            return

        code = data.get("code", "")
        custom_css = data.get("custom_css", "")
        custom_html = data.get("custom_html", "")
        
        # Fast static checks
        has_static_control = any(kw in code or kw in custom_html for kw in CONTROL_KEYWORDS_CLEANUP)
        has_static_loading = bool(re.search(r'["\'][\s\S]*?loading[\s\S]*?["\']', code, re.IGNORECASE)) or "loading" in custom_html.lower()
        
        # 外部資產依存度靜態審查（分離音訊與非音訊資產）
        AUDIO_ASSET_KEYWORDS = ["loadSound("]
        NON_AUDIO_ASSET_KEYWORDS = ["loadImage(", "loadModel(", "loadFont(", "loadStrings(", "loadTable(", "loadBytes(", "loadXML("]
        inline_assets = data.get("inline_assets", {})
        code_clean = code.replace(" ", "") + "\n" + custom_html.replace(" ", "")
        has_audio_call = any(kw in code_clean for kw in AUDIO_ASSET_KEYWORDS)
        has_non_audio_call = any(kw in code_clean for kw in NON_AUDIO_ASSET_KEYWORDS)
        has_no_inline = not inline_assets
        
        # 音訊資產：自動跳過（我們的 MOCK_P5_JS 已完整攔截 loadSound/p5.SoundFile）
        # 非音訊資產：嘗試從 OpenProcessing 下載
        asset_download_attempted = False
        asset_download_ok = True
        if has_non_audio_call and has_no_inline:
            self.log(f"   📦 偵測到外部資產依賴，嘗試下載...")
            dl_result = self.try_download_assets(data, file_path, code)
            asset_download_attempted = True
            if not dl_result["success"]:
                asset_download_ok = False
                self.log_asset_error(name, dl_result["errors"])
                self.log(f"   ⚠️ 部分資產下載失敗，已記錄錯誤（模組保留，preload guard 會優雅降級）")
            else:
                self.log(f"   ✅ 外部資產下載完成！")
        
        if has_audio_call and has_no_inline and not has_non_audio_call:
            self.log(f"   🔊 僅需音訊資產，自動由 Mock 系統適配（無需下載）")
        
        # 靜態安全檢查：過濾可能在 setup/draw 中因資源加載或無窮遞迴死鎖的 while 迴圈代碼
        # 避免這類代碼在 QWebEngineView 中搶佔 Qt 主線程導致整個清理程序卡死
        has_dangerous_while = False
        if "while" in code:
            if re.search(r'\bwhile\s*\([\s\S]*?\)\s*\{', code):
                has_dangerous_while = True
        
        if has_static_control:
            self.log(f"   🎛️ 偵測到控制項 (Static)，已自動隱藏並橋接音訊調製")
        if has_static_loading:
            self.log(f"   💬 偵測到文字提示/Loading (Static)，已自動啟用智慧隱藏過濾")
        
        if has_dangerous_while:
            reason_str = "包含危險的 while 迴圈 (Static Guard)"
            self.results.append({
                "name": name,
                "file_path": file_path,
                "status": "delete",
                "reason": reason_str
            })
            self.log(f"   🗑️ 已標記刪除: {reason_str}")
            self.current_idx += 1
            self.timer.start(10)
            return

        # Headless Browser Run
        self.current_errors = []
        if not self.view or self.view_crashed:
            if self.view:
                try:
                    self.view.deleteLater()
                except Exception:
                    pass
            self.view = QWebEngineView(self.clipper)
            self.view_crashed = False
            
            from PyQt6.QtWebEngineCore import QWebEngineProfile
            self.profile = QWebEngineProfile()
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            self.profile.clearHttpCache()
            self.page = CustomWebEnginePage(self.handle_console_msg, self.profile, self.view)
            def handle_terminated(status, exit_code):
                self.view_crashed = True
                self.log(f"   ⚠️ 瀏覽器渲染進程終止 (Status: {status}, Code: {exit_code})，將在下一個任務重啟...", True)
            self.page.renderProcessTerminated.connect(handle_terminated)
            self.view.setPage(self.page)
            
            settings = self.view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            self.view.setGeometry(0, 0, 300, 300)
            self.view.show()
        
        html_content = make_test_html_cleanup(code, custom_css, custom_html)
        import random
        dummy_url = QUrl.fromLocalFile(os.path.join(workspace_dir, f"dummy_test_{name}_{random.randint(0, 1000000)}.html"))
        self.view.setHtml(html_content, dummy_url)
        
        loop = QEventLoop()
        def on_load_finished(ok):
            try:
                if loop.isRunning():
                    loop.quit()
            except RuntimeError:
                pass
        self.view.loadFinished.connect(on_load_finished)
        
        def on_load_timeout():
            try:
                if loop.isRunning():
                    loop.quit()
            except RuntimeError:
                pass
        QTimer.singleShot(5000, on_load_timeout)  # 5 秒超時，足夠載入 CDN 腳本
        loop.exec()
        try:
            self.view.loadFinished.disconnect(on_load_finished)
        except Exception:
            pass
        
        # 改用小步長輪詢等待，兼顧極速渲染與物理超時安全，防止 setup/draw 內部的死循環卡死事件循環
        import time
        start_time = time.time()
        runtime_flags = {}
        
        while time.time() - start_time < 1.5:
            QApplication.processEvents() # 不斷派發 Qt 事件，保證 UI 與超時不卡死
            
            loop_poll = QEventLoop()
            poll_flags = {}
            def on_poll_done(val):
                nonlocal poll_flags
                try:
                    from PyQt6 import sip
                    poll_flags = val if isinstance(val, dict) else {}
                    if 'loop_poll' in locals() and loop_poll and not sip.isdeleted(loop_poll):
                        if loop_poll.isRunning():
                            loop_poll.quit()
                except Exception:
                    pass
            
            js_poll = """
            (function() {
                return {
                    textCalled: window.__textCalled || false,
                    controlsCreated: window.__controlsCreated || false,
                    loadingDetected: window.__loadingDetected || false,
                    earlyErrors: window.__jsErrors || [],
                    drawCount: window.__drawCount || 0,
                    setupFinished: window.__setupFinished || false
                };
            })();
            """
            self.view.page().runJavaScript(js_poll, on_poll_done)
            
            def on_timer_timeout():
                try:
                    from PyQt6 import sip
                    if 'loop_poll' in locals() and loop_poll and not sip.isdeleted(loop_poll):
                        if loop_poll.isRunning():
                            loop_poll.quit()
                except Exception:
                    pass
            QTimer.singleShot(80, on_timer_timeout)
            loop_poll.exec()
            
            # 更新狀態
            if poll_flags:
                runtime_flags = poll_flags
                # ── 提前退出條件 ──
                # 條件 1：如果有任何 JS 錯誤，不需要等了，直接跳出
                if self.current_errors or poll_flags.get("earlyErrors"):
                    break
                # 條件 2：如果是 p5 模組且已經成功繪製 2 影格以上，說明初始化完全成功，不需要再等了
                if poll_flags.get("setupFinished") and poll_flags.get("drawCount") >= 2:
                    break
            
            time.sleep(0.03)  # 30毫秒微小等待，讓出 CPU
        
        # 僅清理當前頁面的狀態，不需要銷毀 QWebEngineView，防止頻繁重建引發記憶體耗盡與事件循環崩潰
        if self.view:
            self.view.setHtml("<html></html>")
        gc.collect()
        
        text_called = runtime_flags.get("textCalled", False)
        controls_created = runtime_flags.get("controlsCreated", False)
        loading_detected = runtime_flags.get("loadingDetected", False)
        early_errors = runtime_flags.get("earlyErrors", [])
        
        all_errors = list(set(self.current_errors + early_errors))
        
        status = "keep"
        reasons = []
        if all_errors:
            status = "delete"
            reasons.append(f"代碼執行錯誤: {'; '.join(all_errors)}")
        if controls_created:
            self.log(f"   🎛️ 運行時已自動隱藏動態控制項 (DOM)")
        if loading_detected:
            self.log(f"   💬 運行時已自動隱藏無關文字/載入提示")
            
        reason_str = ", ".join(reasons) if reasons else ("正常且已適配音訊" if controls_created else "正常且畫面乾淨")
        self.results.append({
            "name": name,
            "file_path": file_path,
            "status": status,
            "reason": reason_str
        })
        
        if status == "delete":
            self.log(f"   🗑️ 已標記刪除: {reason_str}")
        else:
            self.log(f"   ✅ {reason_str}，予以保留")
            
        self.current_idx += 1
        self.timer.start(10)

    def try_download_assets(self, data, file_path, code):
        """嘗試從 OpenProcessing 下載模組需要的外部資產檔案。"""
        import requests
        result = {"success": True, "errors": [], "downloaded": []}
        
        url = data.get("url", "")
        sketch_id = None
        sketch_match = re.search(r'/sketch/(\d+)', url)
        if not sketch_match:
            sketch_match = re.search(r'/@[\w\-]+/(\d+)', url)
        if sketch_match:
            sketch_id = sketch_match.group(1)
        
        if not sketch_id:
            result["success"] = False
            result["errors"].append("無法從 URL 中提取 sketch_id")
            return result
        
        # 從代碼中提取資產檔名
        code_no_comments = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code_no_comments = re.sub(r'//.*', '', code_no_comments)
        asset_pattern = r'["\'\`]([^"\'\`]+?\.(?:png|jpg|jpeg|gif|svg|bmp|webp|ttf|otf|woff|woff2|obj|fbx|gltf|glb|json|txt|csv|tsv))["\'\`]'
        asset_names = list(set(re.findall(asset_pattern, code_no_comments)))
        
        if not asset_names:
            # 有 loadImage/loadFont 呼叫但找不到具體檔名，可能是動態路徑
            result["success"] = True  # 不算失敗，preload guard 會處理
            return result
        
        # 過濾掉完整 URL（CDN 等外部資源），只保留相對路徑
        local_assets = []
        for a in asset_names:
            if a.startswith("http://") or a.startswith("https://") or a.startswith("data:"):
                continue
            # 過濾明顯的非資產字串
            if "/" in a and a.count("/") > 3:
                continue
            local_assets.append(a)
        
        if not local_assets:
            result["success"] = True
            return result
        
        # 限制單個模組最多只下載前 5 個資產，避免大量碎檔案下載導致卡死
        local_assets = local_assets[:5]
        
        # 嘗試從 OpenProcessing API 獲取 fileBase
        file_base = data.get("file_base", "")
        if not file_base:
            try:
                api_url = f"https://openprocessing.org/api/sketch/{sketch_id}"
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                resp = requests.get(api_url, headers=headers, timeout=3) # 降低超時至 3 秒
                if resp.status_code == 200:
                    sketch_data = resp.json()
                    file_base = sketch_data.get("fileBase", "")
            except Exception as e:
                result["errors"].append(f"API 請求失敗: {e}")
        
        if not file_base:
            # 構建預設 fileBase
            file_base = f"https://openprocessing.org/sketch/{sketch_id}/files/"
        
        # 下載資產
        assets_dir = os.path.join(workspace_dir, "custom_visuals", "assets", str(sketch_id))
        os.makedirs(assets_dir, exist_ok=True)
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        
        downloaded_count = 0
        failed_count = 0
        
        for asset in local_assets:
            clean_asset = asset.lstrip("./")
            asset_url = file_base + clean_asset
            local_file_path = os.path.join(assets_dir, clean_asset)
            
            # 如果已經下載過，跳過
            if os.path.exists(local_file_path):
                downloaded_count += 1
                continue
            
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            try:
                self.log(f"      📥 下載: {clean_asset}...")
                QApplication.processEvents()
                resp = requests.get(asset_url, headers=headers, timeout=4) # 降低超時至 4 秒
                if resp.status_code == 200:
                    with open(local_file_path, "wb") as af:
                        af.write(resp.content)
                    downloaded_count += 1
                    result["downloaded"].append(clean_asset)
                    self.log(f"      ✅ {clean_asset} ({len(resp.content)} bytes)")
                else:
                    failed_count += 1
                    result["errors"].append(f"{clean_asset}: HTTP {resp.status_code}")
                    self.log(f"      ❌ {clean_asset}: HTTP {resp.status_code}")
            except Exception as dl_err:
                failed_count += 1
                result["errors"].append(f"{clean_asset}: {dl_err}")
                self.log(f"      ❌ {clean_asset}: {dl_err}")
        
        # 如果有任何下載失敗，標記為非完全成功（但不刪除模組）
        if failed_count > 0:
            result["success"] = False
        
        # 更新模組 JSON，保存 file_base 供後續使用
        if file_base and not data.get("file_base"):
            try:
                data["file_base"] = file_base
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        
        return result

    def log_asset_error(self, module_name, errors):
        """將資產下載失敗記錄追加到 op_import_errors.txt。"""
        import datetime
        report_path = os.path.join(workspace_dir, "op_import_errors.txt")
        try:
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"\n[ASSET_DOWNLOAD_FAILED] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Module: {module_name}\n")
                for err in errors:
                    f.write(f"  - {err}\n")
        except Exception as e:
            self.log(f"   ⚠️ 寫入錯誤日誌失敗: {e}", True)

    def finish_cleanup(self):
        # 顯式切斷頁面關聯並銷毀 QWebEngineView，釋放 Chromium 引擎佔用之系統與虛擬記憶體資源
        if self.view:
            try:
                self.view.setPage(None)
                self.view.setParent(None)
                self.view.close()
                self.view.deleteLater()
            except Exception:
                pass
            self.view = None
        gc.collect()

        import datetime
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        report_path = os.path.join(workspace_dir, "op_import_errors.txt")
        
        deleted_count = 0
        kept_count = 0
        deleted_list = []
        
        for item in self.results:
            name = item["name"]
            status = item["status"]
            reason = item["reason"]
            file_path = item["file_path"]
            
            if status == "delete":
                deleted_count += 1
                deleted_list.append(item)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
                        if os.path.exists(thumb_path):
                            os.remove(thumb_path)
                    except Exception as err:
                        print(f"Error deleting file {name}: {err}")
            else:
                kept_count += 1
                
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.log(f"\n🏁 清理程序完成！保留: {kept_count}，刪除: {deleted_count}")
        
        try:
            with open(report_path, "a", encoding="utf-8") as f:
                f.write("\n" + "="*70 + "\n")
                f.write("UI Visual Modules Clean Tool Execution Report (UI 視覺模組篩選清理工具執行報告)\n")
                f.write(f"Execution Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Evaluated: {len(self.results)}\n")
                f.write(f"Kept Count: {kept_count}\n")
                f.write(f"Deleted Count: {deleted_count}\n")
                f.write("======================================================================\n\n")
                
                for idx, item in enumerate(deleted_list, 1):
                    f.write(f"[{idx}] Deleted Module: {item['name']}\n")
                    f.write(f"    Reason: {item['reason']}\n\n")
                    
                f.write("="*70 + "\n")
        except Exception as e:
            print(f"Error logging to report: {e}")

        if self.parent_window and hasattr(self.parent_window, "refresh_presets_list"):
            self.parent_window.refresh_presets_list()
            
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        
        if self.is_cancelled:
            QMessageBox.warning(self, "已中止", f"清理程序已被使用者中止！\n\n已完成評估: {len(self.results)} 個模組，其中刪除了 {deleted_count} 個不合規模組。")
        else:
            QMessageBox.information(self, "清理完成", f"模組庫清理完成！\n\n共計評估: {len(self.results)} 個模組\n保留: {kept_count} 個合規模組\n刪除: {deleted_count} 個不合規模組。\n\n詳細刪除原因請參閱 op_import_errors.txt。")

    def closeEvent(self, event):
        # 當視窗關閉時，中止計時器與清理流程，顯式銷毀 QWebEngineView 防止事件與資源殘留
        self.is_cancelled = True
        self.timer.stop()
        if self.view:
            try:
                self.view.setPage(None)
                self.view.setParent(None)
                self.view.close()
                self.view.deleteLater()
            except Exception:
                pass
            self.view = None
        gc.collect()
        event.accept()


class CleanupModeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("選擇試運行與篩選模式")
        self.resize(500, 290)
        self.mode = None # 'auto', 'manual', 'black_screen', or None
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Inter', sans-serif; font-size: 13px; margin-bottom: 5px; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px;
                text-align: left;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_auto { border-left: 4px solid #7c3aed; }
            QPushButton#btn_manual { border-left: 4px solid #10b981; }
            QPushButton#btn_black { border-left: 4px solid #a855f7; }
            QPushButton#btn_cancel { background-color: #09090b; text-align: center; font-weight: normal; }
        """)
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel("請選擇本機視覺模組庫的試運行與清理模式：", self)
        layout.addWidget(lbl)
        
        self.btn_auto = QPushButton("🤖 自動化快速清理\n   (Headless 靜態與動態審查，自動篩除報錯崩潰模組，自動隱藏控制項/音訊橋接與隱藏無關文字)", self)
        self.btn_auto.setObjectName("btn_auto")
        self.btn_auto.clicked.connect(self.select_auto)
        layout.addWidget(self.btn_auto)
        
        self.btn_black = QPushButton("🎬 畫布黑屏與純色自檢自測清理\n   (執行 15 秒實時畫布像素分析，自動隱藏並備份黑屏或純色畫布)", self)
        self.btn_black.setObjectName("btn_black")
        self.btn_black.clicked.connect(self.select_black_screen)
        layout.addWidget(self.btn_black)
        
        self.btn_manual = QPushButton("👀 手動逐一審查\n   (如同收錄後的工作區，展示預覽畫面與日誌，手動決定保留與否)", self)
        self.btn_manual.setObjectName("btn_manual")
        self.btn_manual.clicked.connect(self.select_manual)
        layout.addWidget(self.btn_manual)
        
        self.btn_cancel = QPushButton("取消", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)
        
    def select_auto(self):
        self.mode = "auto"
        self.accept()
        
    def select_black_screen(self):
        self.mode = "black_screen"
        self.accept()
        
    def select_manual(self):
        self.mode = "manual"
        self.accept()


def main():
    if "--no-sandbox" not in sys.argv:
        sys.argv.append("--no-sandbox")
    if "--disable-web-security" not in sys.argv:
        sys.argv.append("--disable-web-security")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Configure global dark palette as fallback for native OS palette
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(11, 11, 14))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(228, 228, 231))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(18, 18, 27))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(24, 24, 27))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(24, 24, 27))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(228, 228, 231))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(244, 244, 245))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(24, 24, 27))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(244, 244, 245))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(168, 85, 247))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(168, 85, 247))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(dark_palette)

    app.setOrganizationName("VibeCoding")
    app.setOrganizationDomain("vibecoding.com")
    app.setApplicationName("4KMVVisualIntegrationEditor")
    window = StandaloneInjectorApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()