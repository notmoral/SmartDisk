import hashlib
import concurrent.futures
import os

def compute_hash(filepath, algorithm='md5', chunk_size=65536):
    try:
        hasher = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return None

def compute_partial_hash(filepath, algorithm='md5', bytes_to_read=4096):
    """Хэширует только первые 4 КБ файла для мгновенной проверки"""
    try:
        hasher = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            hasher.update(f.read(bytes_to_read))
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return None

def find_duplicates(candidates_by_size, progress_callback=None):
    partial_hashes = {}
    files_to_hash = [path for paths in candidates_by_size.values() for path in paths]
    total_files = len(files_to_hash)
    processed = 0
    
    if total_files == 0:
        return {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
        future_to_path = {executor.submit(compute_partial_hash, p): p for p in files_to_hash}
        
        for future in concurrent.futures.as_completed(future_to_path):
            path = future_to_path[future]
            h = future.result()
            if h:
                partial_hashes.setdefault(h, []).append(path)
            processed += 1
            if progress_callback and processed % 50 == 0:
                progress_callback(processed, total_files, path)

    partial_candidates = [paths for paths in partial_hashes.values() if len(paths) > 1]
    files_to_full_hash = [path for paths in partial_candidates for path in paths]
    
    final_duplicates = {}
    total_full = len(files_to_full_hash)
    processed_full = 0

    if total_full > 0:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
            future_to_path = {executor.submit(compute_hash, p): p for p in files_to_full_hash}
            
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                h = future.result()
                if h:
                    final_duplicates.setdefault(h, []).append(path)
                processed_full += 1
                if progress_callback:
                    progress_callback(total_files + processed_full, total_files + total_full, path)

    return {h: paths for h, paths in final_duplicates.items() if len(paths) > 1}