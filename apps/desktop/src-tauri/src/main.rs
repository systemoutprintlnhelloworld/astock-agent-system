use tauri::{AppHandle, Manager, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendSidecar(std::sync::Mutex<Option<CommandChild>>);

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
        .join("..").join("..")
        .canonicalize()
        .unwrap_or(current_dir)
        .to_string_lossy()
        .to_string()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendSidecar(std::sync::Mutex::new(None)))
        .setup(|app| {
            let project_root = locate_project_root(&app.handle());
            let (mut receiver, child) = app
                .shell()
                .sidecar("binaries/astock-backend")?
                .args(["--host", "127.0.0.1", "--port", "8000", "--project-root", &project_root])
                .spawn()?;

            tauri::async_runtime::spawn(async move {
                while let Some(event) = receiver.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("backend: {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("backend: {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(payload) => {
                            println!("backend terminated: {:?}", payload.code);
                        }
                        CommandEvent::Error(error) => {
                            eprintln!("backend sidecar error: {error}");
                        }
                        _ => {}
                    }
                }
            });

            let state = app.state::<BackendSidecar>();
            *state.0.lock().expect("sidecar state poisoned") = Some(child);
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                let state = window.state::<BackendSidecar>();
                let child = state.0.lock().expect("sidecar state poisoned").take();
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running AStock Agent desktop shell");
}
