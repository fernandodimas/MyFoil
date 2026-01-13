import json
import re
import sys

def robust_fix(content):
    # Pattern to match a valid escape or a bare backslash
    # Group 1 captures valid escape sequences
    pattern = re.compile(r'(\\([\"\\/bfnrt]|u[0-9a-fA-F]{4}))|(\\)')
    
    def replace_func(m):
        if m.group(1):
            return m.group(1) # It's a valid escape, keep it as is
        else:
            return r'\\' # It's a bare backslash, escape it
            
    return pattern.sub(replace_func, content)

def debug_json(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    sanitized = robust_fix(content)
    # Also strip control characters
    sanitized = "".join(ch for ch in sanitized if ord(ch) >= 32 or ch in '\n\r\t')
    
    try:
        json.loads(sanitized, strict=False)
        print("SUCCESS with robust_fix!")
    except json.JSONDecodeError as e:
        print(f"FAILED with robust_fix: {e}")
        pos = e.pos
        print(f"Context at {pos}:")
        print(sanitized[max(0, pos-50):min(len(sanitized), pos+50)])
        print(" " * min(50, pos) + "^")

if __name__ == "__main__":
    debug_json(sys.argv[1])
