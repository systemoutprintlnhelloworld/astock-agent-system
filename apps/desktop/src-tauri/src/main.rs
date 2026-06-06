use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use tauri::{AppHandle, Manager, WindowEvent};

#[cfg(windows)]
const BACKEND_BINARY_NAMES: &[&str] = &[
    "astock-backend.exe",
    "astock-backend-x86_64-pc-windows-msvc.exe",
];

#[cfg(not(windows))]
const BACKEND_BINARY_NAMES: &[&str] = &["astock-backend"];

struct BackendSidecar(std::sync::Mutex<Option<Child>>);

const DEFAULT_BACKEND_PORT: u16 = 8000;
const MAX_BACKEND_PORT: u16 = 8020;

fn locate_project_root(app: &AppHandle) -> String {
    if let Ok(resource_dir) = app.path().resource_dir() {
        if resource_dir.join("config").join("config.yaml").exists() {
            return resource_dir.to_string_lossy().to_string();
        }
    }

    let current_dir = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    for candidate in current_dir.ancestors() {
        if candidate.join("config").join("config.yaml").exists()
            && candidate.join("data").join("samples").exists()
        {
            return candidate.to_string_lossy().to_string();
        }
    }
    current_dir
        .join("..")
        .join("..")
        .canonicalize()
        .unwrap_or(current_dir)
        .to_string_lossy()
        .to_string()
}

fn push_backend_candidates(candidates: &mut Vec<PathBuf>, base: &Path) {
    for binary_name in BACKEND_BINARY_NAMES {
        candidates.push(base.join(binary_name));
        candidates.push(base.join("binaries").join(binary_name));
    }
}

fn candidate_backend_paths(app: &AppHandle) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(resource_dir) = app.path().resource_dir() {
        push_backend_candidates(&mut candidates, &resource_dir);
    }

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(exe_dir) = current_exe.parent() {
            push_backend_candidates(&mut candidates, exe_dir);
        }
    }

    if let Ok(current_dir) = std::env::current_dir() {
        push_backend_candidates(&mut candidates, &current_dir);
    }

    push_backend_candidates(&mut candidates, Path::new(env!("CARGO_MANIFEST_DIR")));
    candidates
}

fn is_astock_backend_healthy(port: u16) -> bool {
    let address = format!("127.0.0.1:{port}");
    let Ok(socket_address) = address.parse() else {
        return false;
    };

    let Ok(mut stream) = TcpStream::connect_timeout(&socket_address, Duration::from_millis(350))
    else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(350)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(350)));

    let request = "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }

    response.contains("200 OK") && response.contains("AStock") && response.contains("event_types")
}

fn is_port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn select_backend_port() -> (u16, bool) {
    for port in DEFAULT_BACKEND_PORT..=MAX_BACKEND_PORT {
        if is_astock_backend_healthy(port) {
            return (port, false);
        }
    }

    for port in DEFAULT_BACKEND_PORT..=MAX_BACKEND_PORT {
        if is_port_available(port) {
            return (port, true);
        }
    }

    (DEFAULT_BACKEND_PORT, true)
}

fn spawn_backend_sidecar(app: &AppHandle, project_root: &str, port: u16) -> Option<Child> {
    let candidates = candidate_backend_paths(app);
    let port_arg = port.to_string();
    for candidate in &candidates {
        if !candidate.exists() {
            continue;
        }

        match Command::new(candidate)
            .args([
                "--host",
                "127.0.0.1",
                "--port",
                port_arg.as_str(),
                "--project-root",
                project_root,
            ])
            .env("ASTOCK_PROJECT_ROOT", project_root)
            .env("ASTOCK_BACKEND_PORT", &port_arg)
            .current_dir(project_root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        {
            Ok(child) => {
                println!(
                    "backend sidecar started on 127.0.0.1:{port}: {}",
                    candidate.display()
                );
                return Some(child);
            }
            Err(error) => {
                eprintln!(
                    "failed to start backend sidecar {}: {error}",
                    candidate.display()
                );
            }
        }
    }

    eprintln!("backend sidecar not found; tried these locations:");
    for candidate in candidates {
        eprintln!("  {}", candidate.display());
    }
    None
}

fn main() {
    tauri::Builder::default()
        .manage(BackendSidecar(std::sync::Mutex::new(None)))
        .setup(|app| {
            let project_root = locate_project_root(&app.handle());
            let (backend_port, should_spawn) = select_backend_port();
            if should_spawn {
                let child = spawn_backend_sidecar(&app.handle(), &project_root, backend_port);
                if let Some(child) = child {
                    let state = app.state::<BackendSidecar>();
                    *state.0.lock().expect("sidecar state poisoned") = Some(child);
                }
            } else {
                println!("using existing AStock backend on 127.0.0.1:{backend_port}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                let state = window.state::<BackendSidecar>();
                let child = state.0.lock().expect("sidecar state poisoned").take();
                if let Some(mut child) = child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running AStock Agent desktop shell");
}
