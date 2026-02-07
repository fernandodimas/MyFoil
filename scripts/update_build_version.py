import os
import datetime

def update():
    # Find app/constants.py relative to the script location or current dir
    # Assuming run from project root
    path = os.path.join(os.getcwd(), 'app/constants.py')
    if not os.path.exists(path):
        print(f"Error: {path} not found")
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
