import re
import math
import logging

logger = logging.getLogger("VisualStudio.ASTParamEngine")

class ASTParamEngine:
    """
    JavaScript AST 參數解析與雙向熱修補引擎
    - 掃描變數宣告 (`let`, `var`, `const`) 與數值常數
    - 支援 `@wizard(min=0, max=100, step=1, label="粒子密度")` 註解標籤
    - 啟發式自動推算數值範圍與步長
    - 生成沙盒記憶體熱更新語句 (Hot-Patching)
    - 提供精確代碼回寫 (Code Text Patching)
    """

    # 匹配變數宣告：let/var/const 名稱 = 數值; 允許尾部註解
    VAR_PATTERN = re.compile(
        r'^(?P<indent>\s*)(?P<decl>let|var|const)\s+(?P<name>[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?P<val>-?\d+(?:\.\d+)?)\s*;\s*(?://(?P<comment>.*))?$',
        re.MULTILINE
    )

    # 匹配 @wizard(...) 標籤
    WIZARD_TAG_PATTERN = re.compile(
        r'@wizard\s*\(\s*(?P<args>.*?)\s*\)'
    )

    @classmethod
    def parse_params(cls, code_text: str) -> list:
        """
        解析代碼中的所有可調參數
        回傳參數列表：[{name, value, min, max, step, label, is_int, line_num}]
        """
        params = []
        lines = code_text.split('\n')

        for idx, line in enumerate(lines):
            line_num = idx + 1
            # 排除系統保留變數或常見迴圈計數器
            match = cls.VAR_PATTERN.match(line)
            if not match:
                continue

            name = match.group("name")
            raw_val = match.group("val")
            comment = match.group("comment") or ""

            # 忽略 i, j, k, w, h, _ 開頭的臨時變數
            if name in {"i", "j", "k", "w", "h", "x", "y", "z", "dx", "dy", "dz", "theta", "phi", "windowWidth", "windowHeight"}:
                continue
            if name.startswith("_"):
                continue

            is_int = ("." not in raw_val)
            val = int(raw_val) if is_int else float(raw_val)

            # 解析 @wizard 標籤
            tag_meta = cls._parse_wizard_comment(comment)

            label = tag_meta.get("label", cls._humanize_name(name))
            min_v = tag_meta.get("min")
            max_v = tag_meta.get("max")
            step = tag_meta.get("step")

            # 若無 @wizard 標籤，使用啟發式推算
            if min_v is None or max_v is None or step is None:
                h_min, h_max, h_step = cls._infer_range_and_step(val, is_int)
                min_v = min_v if min_v is not None else h_min
                max_v = max_v if max_v is not None else h_max
                step = step if step is not None else h_step

            params.append({
                "name": name,
                "value": val,
                "min": min_v,
                "max": max_v,
                "step": step,
                "label": label,
                "is_int": is_int,
                "line_num": line_num,
                "has_wizard_tag": bool(tag_meta)
            })

        return params

    @classmethod
    def _parse_wizard_comment(cls, comment_text: str) -> dict:
        """解析 // @wizard(min=0, max=100, step=1, label="粒子密度")"""
        res = {}
        if not comment_text:
            return res

        tag_match = cls.WIZARD_TAG_PATTERN.search(comment_text)
        if not tag_match:
            return res

        args_str = tag_match.group("args")
        # 提取鍵值對：key=value
        kv_pairs = re.findall(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,]+))', args_str)
        for key, v_double, v_single, v_raw in kv_pairs:
            key = key.strip().lower()
            val_str = v_double or v_single or v_raw
            val_str = val_str.strip()

            if key == "label":
                res["label"] = val_str
            elif key in {"min", "max", "step"}:
                try:
                    res[key] = int(val_str) if "." not in val_str else float(val_str)
                except ValueError:
                    pass

        return res

    @classmethod
    def _humanize_name(cls, camel_case_name: str) -> str:
        """駝峰命名轉人類友好名稱：particleCount -> Particle Count"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', camel_case_name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1)
        words = s2.replace('_', ' ').split()
        return " ".join([w.capitalize() for w in words])

    @classmethod
    def _infer_range_and_step(cls, val: float, is_int: bool) -> tuple:
        """啟發式動態推算合理數值滑桿範圍與步長"""
        if is_int:
            if val <= 0:
                min_v = val - 100
                max_v = max(100, abs(val) * 3)
                step = 1
            elif val <= 10:
                min_v = 0
                max_v = max(20, val * 3)
                step = 1
            elif val <= 100:
                min_v = 0
                max_v = val * 3
                step = 1
            elif val <= 1000:
                min_v = 10
                max_v = max(2000, val * 3)
                step = 10
            else:
                min_v = 100
                max_v = val * 3
                step = 50
            return int(min_v), int(max_v), int(step)
        else:
            # 浮點數
            abs_v = abs(val)
            if abs_v == 0.0:
                return -1.0, 1.0, 0.01
            elif abs_v < 0.01:
                return 0.0, float(f"{val * 4:.4f}"), float(f"{abs_v / 10:.4f}")
            elif abs_v <= 1.0:
                min_v = 0.0 if val >= 0 else -1.0
                max_v = 1.0 if val <= 1.0 and val >= 0 else max(2.0, val * 2)
                return float(f"{min_v:.2f}"), float(f"{max_v:.2f}"), 0.01
            elif abs_v <= 10.0:
                min_v = 0.0 if val >= 0 else -val * 2
                max_v = val * 2.5
                return float(f"{min_v:.1f}"), float(f"{max_v:.1f}"), 0.1
            else:
                min_v = 0.0 if val >= 0 else -val * 2
                max_v = val * 2.5
                return float(f"{min_v:.1f}"), float(f"{max_v:.1f}"), 1.0

    @classmethod
    def generate_hot_patch_js(cls, param_name: str, new_value) -> str:
        """
        生成注入 WebGL / p5.js 沙盒的記憶體覆寫代碼
        不重載畫布、不打斷 60FPS 動畫
        """
        val_str = str(new_value)
        return f"""(function() {{
            try {{
                if (typeof window.{param_name} !== 'undefined') {{
                    window.{param_name} = {val_str};
                }}
                if (typeof {param_name} !== 'undefined') {{
                    {param_name} = {val_str};
                }}
                if (window.onVisualParamChanged) {{
                    window.onVisualParamChanged('{param_name}', {val_str});
                }}
            }} catch(e) {{
                console.warn('[ASTParamEngine] Hot-patch param failed for {param_name}:', e);
            }}
        }})();"""

    @classmethod
    def patch_code_text(cls, code_text: str, param_name: str, new_value) -> str:
        """
        精確修改代碼文字中的變數賦值，保持原始排版與註解
        """
        lines = code_text.split('\n')
        target_pattern = re.compile(
            rf'^(?P<indent>\s*)(?P<decl>let|var|const)\s+{re.escape(param_name)}\s*=\s*(?P<val>-?\d+(?:\.\d+)?)(?P<rest>\s*;.*)$'
        )

        new_val_str = str(new_value)
        patched = False

        for idx, line in enumerate(lines):
            match = target_pattern.match(line)
            if match:
                indent = match.group("indent")
                decl = match.group("decl")
                rest = match.group("rest")
                lines[idx] = f"{indent}{decl} {param_name} = {new_val_str}{rest}"
                patched = True
                break

        return "\n".join(lines)
