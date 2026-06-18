import os
import datetime

def update():
    # Find constants.py in multiple possible locations:
    # 1. app/constants.py (running from project root, e.g. pre-commit hook)
    # 2. constants.py (running inside Docker where WORKDIR=/app)
    # 3. Relative to this script's location
    candidates = [
        os.path.join(os.getcwd(), 'app', 'constants.py'),
        os.path.join(os.getcwd(), 'constants.py'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'constants.py'),
    ]

    path = None
    for candidate in candidates:
        if os.path.exists(candidate):
            path = candidate
            break

    if not path:
        print(f"Error: constants.py not found in any of: {candidates}")
        return

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_version = datetime.datetime.now().strftime('%Y%m%d_%H%M')

    updated = False
    with open(path, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.strip().startswith('BUILD_VERSION ='):
                f.write(f"BUILD_VERSION = '{new_version}'\n")
                updated = True
            else:
                f.write(line)

    if updated:
        print(f"Updated BUILD_VERSION to {new_version}")
    else:
        print("Warning: BUILD_VERSION line not found in constants.py")

if __name__ == "__main__":
    update()

