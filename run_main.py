import os
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app_dir = os.path.join(root, 'app')
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
os.chdir(root)
if __name__ == '__main__':
    os.execv(sys.executable, [sys.executable, os.path.join(app_dir, 'main.py')])
