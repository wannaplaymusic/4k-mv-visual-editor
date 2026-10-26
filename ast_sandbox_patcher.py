import os
import re

class ASTSandboxPatcher:
    """
    p5.js 沙盒 AST 與代碼安全注入守衛 (AST Sandbox Armor & Loop Timeout Injector)
    - 在動態 JS sketch 構建時注入循環超時計數器 (__loop_guard)，阻斷無效 while(true) / for 死循環
    - 凍結 JavaScript 原型鏈 Object.freeze(Object.prototype) 杜絕原型污染
    - 防禦未捕獲異常引發的 QWebEngineView / Chromium 進程假死
    """

    GUARD_HEADER = """
    // --- [AST SANDBOX ARMOR INITIALIZATION] ---
    (function() {
        if (typeof window !== 'undefined') {
            window.__MAX_LOOP_ITERATIONS = 200000;
            try {
                Object.freeze(Object.prototype);
                Object.freeze(Array.prototype);
            } catch (e) {
                console.warn("Sandbox freeze warning:", e);
            }
        }
    })();
    """

    @classmethod
    def patch_sketch_code(cls, js_code: str) -> str:
        """
        對 sketch 源代碼進行區塊作用域安全插樁守護 (Unique Block-Scoped Loop Guard)
        防止同作用域多迴圈重複宣告 `let __iter_f` 導致 SyntaxError，以及無括號單行 if 後接 let 的語法崩潰。
        """
        if not js_code or not isinstance(js_code, str):
            return ""

        w_counter = [0]
        f_counter = [0]

        # 替換 while 循環加入獨立區塊作用域守護
        def _replace_while(match):
            w_counter[0] += 1
            idx = w_counter[0]
            cond = match.group(1)
            body = match.group(2)
            return (
                f"{{ let __iter_w_{idx} = 0; while ({cond}) {{ "
                f"if (++__iter_w_{idx} > (window.__MAX_LOOP_ITERATIONS || 200000)) "
                f"{{ console.warn('Sandbox: Loop timeout limit reached'); break; }} {body} }} }}"
            )

        # 替換標準 3 段式 for 循環加入獨立區塊作用域守護
        def _replace_for(match):
            f_counter[0] += 1
            idx = f_counter[0]
            init = match.group(1)
            cond = match.group(2)
            step = match.group(3)
            body = match.group(4)
            return (
                f"{{ let __iter_f_{idx} = 0; for ({init}; {cond}; {step}) {{ "
                f"if (++__iter_f_{idx} > (window.__MAX_LOOP_ITERATIONS || 200000)) "
                f"{{ console.warn('Sandbox: For-loop timeout limit reached'); break; }} {body} }} }}"
            )

        patched = re.sub(r'\bwhile\s*\(([^()\n]*)\)\s*\{([^{}]*)\}', _replace_while, js_code)
        patched = re.sub(r'\bfor\s*\(([^;()\n]*);([^;()\n]*);([^()\n]*)\)\s*\{([^{}]*)\}', _replace_for, patched)

        return cls.GUARD_HEADER + "\n" + patched
