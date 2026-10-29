import os
import string

def get_all_drives():
    return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]

def find_empty_folders(root_paths):
    empty_folders = []
    ignore_dirs = {'windows', '$recycle.bin', 'system volume information', 'recovery', 'perflogs'}
    
    for root in root_paths:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False, onerror=lambda x: None):
            dirnames[:] = [d for d in dirnames if d.lower() not in ignore_dirs]
            if not dirnames and not filenames and dirpath != root:
                if not any(ig in dirpath.lower() for ig in ignore_dirs):
                    empty_folders.append(dirpath)
    return empty_folders

def find_large_files_py(files, limit=50):
    file_data = []
    for f in files:
        try:
            size = os.path.getsize(f)
            if size > 50 * 1024 * 1024:
                file_data.append((f, size))
        except:
            pass
    file_data.sort(key=lambda x: x[1], reverse=True)
    return [{"path": str(f), "size_mb": round(size / (1024 * 1024), 2)} for f, size in file_data[:limit]]