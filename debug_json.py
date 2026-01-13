import json
import re
import sys

def debug_json(path):
    print(f"Analyzing {path}...")
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    try:
        json.loads(content)
        print("SUCCESS: JSON is valid.")
        return
    except json.JSONDecodeError as e:
        print(f"FAILED: {e}")
        pos = e.pos
        start = max(0, pos - 50)
        end = min(len(content), pos + 50)
        context = content[start:end]
        print(f"Context at {pos}:")
        print(f"---")
        print(context)
        print(f"---")
        # Point to the exact character
        pointer = " " * (pos - start) + "^"
        print(pointer)
        
        # Test my Stage 1 regex locally
        # re.sub(r'\\(?!(["\\/bfnrt]|u[0-9a-fA-F]{4}))', r'\\\\', content)
        # Note: In Python regex, we need to be careful with backslashes
        # The goal is to match a \ NOT followed by " \ / b f n r t or uXXXX
        pattern = r'\\(?!(["\\/bfnrt]|u[0-9a-fA-F]{4}))'
        print(f"Applying pattern: {pattern}")
        sanitized = re.sub(pattern, r'\\\\', content)
        
        try:
            json.loads(sanitized, strict=False)
            print("SUCCESS: Sanitization worked!")
        except json.JSONDecodeError as e2:
            print(f"FAILED after sanitization: {e2}")
            pos2 = e2.pos
            start2 = max(0, pos2 - 50)
            end2 = min(len(content), pos2 + 50)
            print(f"New Context at {pos2}:")
            print(content[start2:end2])
            print(" " * (pos2 - start2) + "^")

if __name__ == "__main__":
    debug_json(sys.argv[1])
