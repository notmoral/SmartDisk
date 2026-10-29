use pyo3::prelude::*;
use pyo3::types::{PyList, PyDict};
use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, BufReader};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::UNIX_EPOCH;
use jwalk::WalkDir;
use rayon::prelude::*;
use xxhash_rust::xxh3::Xxh3;

fn compute_partial_hash(path: &Path) -> Option<u64> {
    let mut file = File::open(path).ok()?;
    let mut buffer = [0; 4096];
    let n = file.read(&mut buffer).ok()?;
    let mut hasher = Xxh3::new();
    hasher.update(&buffer[..n]);
    Some(hasher.digest())
}

fn compute_full_hash(path: &Path) -> Option<u64> {
    let file = File::open(path).ok()?;
    let mut reader = BufReader::new(file);
    let mut buffer = [0; 65536];
    let mut hasher = Xxh3::new();
    loop {
        let n = reader.read(&mut buffer).ok()?;
        if n == 0 { break; }
        hasher.update(&buffer[..n]);
    }
    Some(hasher.digest())
}

#[pyfunction]
#[pyo3(signature = (root_path, progress_callback=None))]
fn scan_and_find_duplicates(py: Python, root_path: String, progress_callback: Option<PyObject>) -> PyResult<PyObject> {
    let result = py.allow_threads(|| {
        let mut files_by_size: HashMap<u64, Vec<PathBuf>> = HashMap::new();
        let mut total_files = 0;
        let mut stats_ext: HashMap<String, (u64, u64)> = HashMap::new();
        
        let ignore_dirs = ["windows", "$recycle.bin", "system volume information", "recovery", "perflogs", "node_modules", ".git", "program files", "program files (x86)"];

        if let Some(cb) = &progress_callback {
            Python::with_gil(|py| { let _ = cb.call1(py, (0.05, "Сканирование файловой системы...")); });
        }

        let walker = WalkDir::new(&root_path).skip_hidden(false).process_read_dir(move |_depth, _path, _read_dir_state, children| {
            children.retain(|dir_entry_result| {
                if let Ok(dir_entry) = dir_entry_result {
                    if dir_entry.file_type().is_dir() {
                        let name = dir_entry.file_name().to_string_lossy().to_lowercase();
                        return !ignore_dirs.contains(&name.as_str());
                    }
                }
                true
            });
        });

        let scan_count = Arc::new(AtomicUsize::new(0));

        for entry in walker.into_iter().filter_map(|e| e.ok()) {
            if entry.file_type().is_file() {
                if let Ok(meta) = entry.metadata() {
                    let size = meta.len();
                    if size > 0 {
                        files_by_size.entry(size).or_default().push(entry.path());
                        total_files += 1;
                        
                        let ext = entry.path().extension().and_then(|e| e.to_str()).unwrap_or("no_ext").to_lowercase();
                        let stat = stats_ext.entry(ext).or_insert((0, 0));
                        stat.0 += size;
                        stat.1 += 1;

                        let c = scan_count.fetch_add(1, Ordering::Relaxed);
                        if c % 1000 == 0 {
                            if let Some(cb) = &progress_callback {
                                Python::with_gil(|py| {
                                    let msg = format!("Найдено {} файлов...", total_files);
                                    let _ = cb.call1(py, (0.15, msg));
                                });
                            }
                        }
                    }
                }
            }
        }

        let mut candidates: Vec<PathBuf> = Vec::new();
        for (_, paths) in files_by_size.iter() {
            if paths.len() > 1 {
                candidates.extend(paths.clone());
            }
        }

        let total_candidates = candidates.len();
        if total_candidates == 0 {
            return (total_files, Vec::new(), stats_ext);
        }

        if let Some(cb) = &progress_callback {
            Python::with_gil(|py| { let _ = cb.call1(py, (0.3, "Быстрое хэширование...")); });
        }

        let partial_count = Arc::new(AtomicUsize::new(0));
        let partial_hashes: Vec<(PathBuf, u64)> = candidates.into_par_iter()
            .filter_map(|p| {
                let res = compute_partial_hash(&p).map(|h| (p, h));
                let c = partial_count.fetch_add(1, Ordering::Relaxed);
                if c % 200 == 0 {
                    if let Some(cb) = &progress_callback {
                        Python::with_gil(|py| {
                            let prog = 0.3 + (c as f64 / total_candidates as f64) * 0.3;
                            let _ = cb.call1(py, (prog.min(0.6), "Поиск совпадений..."));
                        });
                    }
                }
                res
            })
            .collect();

        let mut by_partial: HashMap<u64, Vec<PathBuf>> = HashMap::new();
        for (path, hash) in partial_hashes {
            by_partial.entry(hash).or_default().push(path);
        }

        let mut full_candidates: Vec<PathBuf> = Vec::new();
        for (_, paths) in by_partial.iter() {
            if paths.len() > 1 {
                full_candidates.extend(paths.clone());
            }
        }

        if let Some(cb) = &progress_callback {
            Python::with_gil(|py| { let _ = cb.call1(py, (0.6, "Полное хэширование...")); });
        }

        let total_full = full_candidates.len();
        let full_count = Arc::new(AtomicUsize::new(0));
        
        let full_hashes: Vec<(PathBuf, u64)> = full_candidates.into_par_iter()
            .filter_map(|p| {
                let res = compute_full_hash(&p).map(|h| (p, h));
                let c = full_count.fetch_add(1, Ordering::Relaxed);
                if c % 20 == 0 && total_full > 0 {
                    if let Some(cb) = &progress_callback {
                        Python::with_gil(|py| {
                            let prog = 0.6 + (c as f64 / total_full as f64) * 0.35;
                            let _ = cb.call1(py, (prog.min(0.95), "Проверка..."));
                        });
                    }
                }
                res
            })
            .collect();

        let mut by_full: HashMap<u64, Vec<PathBuf>> = HashMap::new();
        for (path, hash) in full_hashes {
            by_full.entry(hash).or_default().push(path);
        }

        let mut final_duplicates: Vec<Vec<(PathBuf, u64, u64)>> = Vec::new();
        for (_, paths) in by_full.into_iter() {
            if paths.len() > 1 {
                let mut group_data = Vec::new();
                for p in paths {
                    let mut size = 0;
                    let mut mtime = 0;
                    if let Ok(meta) = std::fs::metadata(&p) {
                        size = meta.len();
                        if let Ok(modified) = meta.modified() {
                            if let Ok(duration) = modified.duration_since(UNIX_EPOCH) {
                                mtime = duration.as_secs();
                            }
                        }
                    }
                    group_data.push((p, size, mtime));
                }
                final_duplicates.push(group_data);
            }
        }
        
        (total_files, final_duplicates, stats_ext)
    });

    let (total_files, duplicates, stats_ext) = result;

    let py_dict = PyDict::new_bound(py);
    py_dict.set_item("total_files", total_files)?;
    
    let py_dups = PyList::empty_bound(py);
    for group in duplicates {
        let py_group = PyList::empty_bound(py);
        for (p, size, mtime) in group {
            let file_dict = PyDict::new_bound(py);
            file_dict.set_item("path", p.to_string_lossy().to_string())?;
            file_dict.set_item("size_bytes", size)?;
            file_dict.set_item("mtime", mtime)?;
            py_group.append(file_dict)?;
        }
        py_dups.append(py_group)?;
    }
    py_dict.set_item("duplicates", py_dups)?;

    let py_stats = PyDict::new_bound(py);
    for (ext, (size, count)) in stats_ext {
        let stat_dict = PyDict::new_bound(py);
        stat_dict.set_item("size", size)?;
        stat_dict.set_item("count", count)?;
        py_stats.set_item(ext, stat_dict)?;
    }
    py_dict.set_item("stats_ext", py_stats)?;

    Ok(py_dict.into_any().unbind())
}

#[pymodule]
fn smartdisk_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_and_find_duplicates, m)?)?;
    Ok(())
}