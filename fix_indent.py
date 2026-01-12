import os

file_path = '/Users/fernandosouza/.gemini/antigravity/playground/glacial-zodiac/app/titledb.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

output = []
for i, line in enumerate(lines):
    line_no = i + 1
    # Line 158 to 261 need one level of indentation
    if 158 <= line_no <= 261:
        # Pre-check if it's already indented to avoid double indentation
        if not line.startswith('        '): 
            output.append('    ' + line)
        else:
            output.append(line)
    else:
        output.append(line)

with open(file_path, 'w') as f:
    f.writelines(output)
print("Indentation fixed.")
