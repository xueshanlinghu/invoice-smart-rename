use base64::{
    engine::general_purpose::STANDARD as BASE64_STANDARD,
    Engine as _,
};
use serde::{Deserialize, Serialize};
#[cfg(not(debug_assertions))]
use std::net::TcpListener;
#[cfg(not(debug_assertions))]
use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::{mpsc, Mutex};
use std::thread;
use std::time::Duration;
#[cfg(not(debug_assertions))]
use std::time::Instant;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, PhysicalPosition, PhysicalSize, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;
#[cfg(not(debug_assertions))]
use uuid::Uuid;

#[derive(Debug, Clone, Deserialize)]
pub struct RenamePlanItem {
    pub item_id: String,
    pub source_path: String,
    pub target_path: String,
    pub action: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RenameResultItem {
    pub item_id: String,
    pub source_path: String,
    pub target_path: String,
    pub result: String,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PreviewPayload {
    pub kind: String,
    pub mime: String,
    pub base64_data: String,
    pub file_name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BackendInfo {
    pub api_base_url: String,
    pub session_token: String,
}

struct BackendState {
    info: BackendInfo,
    child: Mutex<Option<CommandChild>>,
}

const MAX_PREVIEW_FILE_SIZE: u64 = 20 * 1024 * 1024;
const RENAME_MAX_RETRIES: u32 = 10;
const RENAME_RETRY_DELAY_MS: u64 = 180;
const WINDOW_MOVE_SETTLE_MS: u64 = 800;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ScreenRect {
    x: i64,
    y: i64,
    width: i64,
    height: i64,
}

impl ScreenRect {
    fn overlap(self, other: Self) -> (i64, i64) {
        let width = (self.x + self.width).min(other.x + other.width) - self.x.max(other.x);
        let height = (self.y + self.height).min(other.y + other.height) - self.y.max(other.y);
        (width.max(0), height.max(0))
    }

    fn center(self) -> (i64, i64) {
        (self.x + self.width / 2, self.y + self.height / 2)
    }
}

fn title_bar_is_visible(window: ScreenRect, work_areas: &[ScreenRect]) -> bool {
    let title_bar = ScreenRect {
        height: window.height.min(48),
        ..window
    };
    work_areas.iter().any(|area| {
        let (width, height) = title_bar.overlap(*area);
        width >= window.width.min(160) && height >= title_bar.height.min(24)
    })
}

fn recovery_area(window: ScreenRect, work_areas: &[ScreenRect]) -> Option<ScreenRect> {
    let overlapping = work_areas.iter().copied().max_by_key(|area| {
        let (width, height) = window.overlap(*area);
        width * height
    })?;
    let (width, height) = window.overlap(overlapping);
    if width > 0 && height > 0 {
        return Some(overlapping);
    }

    let (window_x, window_y) = window.center();
    work_areas.iter().copied().min_by_key(|area| {
        let (area_x, area_y) = area.center();
        let dx = i128::from(window_x - area_x);
        let dy = i128::from(window_y - area_y);
        dx * dx + dy * dy
    })
}

fn centered_position(window: ScreenRect, area: ScreenRect) -> PhysicalPosition<i32> {
    let x = area.x + (area.width - window.width).max(0) / 2;
    let y = area.y + (area.height - window.height).max(0) / 2;
    PhysicalPosition::new(x as i32, y as i32)
}

fn keep_window_visible(window: &tauri::WebviewWindow) -> tauri::Result<()> {
    if !window.is_visible()? || window.is_minimized()? || window.is_maximized()? {
        return Ok(());
    }

    let position = window.outer_position()?;
    let size = window.outer_size()?;
    let bounds = ScreenRect {
        x: i64::from(position.x),
        y: i64::from(position.y),
        width: i64::from(size.width),
        height: i64::from(size.height),
    };
    let work_areas: Vec<ScreenRect> = window
        .available_monitors()?
        .into_iter()
        .map(|monitor| {
            let area = monitor.work_area();
            ScreenRect {
                x: i64::from(area.position.x),
                y: i64::from(area.position.y),
                width: i64::from(area.size.width),
                height: i64::from(area.size.height),
            }
        })
        .collect();

    if !title_bar_is_visible(bounds, &work_areas) {
        if let Some(area) = recovery_area(bounds, &work_areas) {
            window.set_position(centered_position(bounds, area))?;
        }
    }
    Ok(())
}

fn restore_main_window(app: &tauri::AppHandle) -> tauri::Result<()> {
    let Some(window) = app.get_webview_window("main") else {
        return Ok(());
    };
    window.show()?;
    window.unminimize()?;
    window.unmaximize()?;

    let target = window
        .primary_monitor()?
        .or_else(|| window.available_monitors().ok()?.into_iter().next());
    if let Some(monitor) = target {
        let area = monitor.work_area();
        window.set_position(PhysicalPosition::new(area.position.x + 24, area.position.y + 24))?;
        window.set_size(PhysicalSize::new(
            (area.size.width * 4 / 5).max(640),
            (area.size.height * 4 / 5).max(480),
        ))?;
        let size = window.outer_size()?;
        let bounds = ScreenRect {
            x: 0,
            y: 0,
            width: i64::from(size.width),
            height: i64::from(size.height),
        };
        let work_area = ScreenRect {
            x: i64::from(area.position.x),
            y: i64::from(area.position.y),
            width: i64::from(area.size.width),
            height: i64::from(area.size.height),
        };
        window.set_position(centered_position(bounds, work_area))?;
    } else {
        window.center()?;
    }
    window.set_focus()?;
    Ok(())
}

fn watch_window_visibility(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let (sender, receiver) = mpsc::channel();
    let initial_sender = sender.clone();
    window.on_window_event(move |event| {
        if matches!(
            event,
            WindowEvent::Moved(_)
                | WindowEvent::Resized(_)
                | WindowEvent::ScaleFactorChanged { .. }
                | WindowEvent::Focused(true)
        ) {
            let _ = sender.send(());
        }
    });
    let app_handle = app.clone();
    thread::spawn(move || {
        while receiver.recv().is_ok() {
            loop {
                match receiver.recv_timeout(Duration::from_millis(WINDOW_MOVE_SETTLE_MS)) {
                    Ok(()) => continue,
                    Err(mpsc::RecvTimeoutError::Timeout) => break,
                    Err(mpsc::RecvTimeoutError::Disconnected) => return,
                }
            }
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = keep_window_visible(&window);
            } else {
                return;
            }
        }
    });
    let _ = initial_sender.send(());
}

fn stop_backend(process: CommandChild) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        // PyInstaller --onefile starts a child process. Killing only its launcher
        // leaves the server running and keeps the sidecar executable locked.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let status = std::process::Command::new("taskkill")
            .args(["/PID", &process.pid().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        if matches!(status, Ok(status) if status.success()) {
            return;
        }
    }

    let _ = process.kill();
}

fn try_rename_with_retry(source: &PathBuf, target: &PathBuf) -> std::io::Result<()> {
    let mut attempt: u32 = 0;
    loop {
        attempt += 1;
        match std::fs::rename(source, target) {
            Ok(()) => return Ok(()),
            Err(err) => {
                let raw = err.raw_os_error();
                let should_retry = matches!(raw, Some(32) | Some(33));
                if !should_retry || attempt >= RENAME_MAX_RETRIES {
                    return Err(err);
                }
                thread::sleep(Duration::from_millis(RENAME_RETRY_DELAY_MS));
            }
        }
    }
}

#[tauri::command]
fn rename_files(plan_items: Vec<RenamePlanItem>) -> Result<Vec<RenameResultItem>, String> {
    let mut results: Vec<RenameResultItem> = Vec::new();

    for plan in plan_items {
        if plan.action != "rename" {
            results.push(RenameResultItem {
                item_id: plan.item_id,
                source_path: plan.source_path,
                target_path: plan.target_path,
                result: String::from("skipped"),
                message: Some(String::from("skipped_by_plan")),
            });
            continue;
        }

        let source = PathBuf::from(&plan.source_path);
        let target = PathBuf::from(&plan.target_path);
        if !source.exists() {
            results.push(RenameResultItem {
                item_id: plan.item_id,
                source_path: plan.source_path,
                target_path: plan.target_path,
                result: String::from("failed"),
                message: Some(String::from("source_not_found")),
            });
            continue;
        }

        match try_rename_with_retry(&source, &target) {
            Ok(_) => results.push(RenameResultItem {
                item_id: plan.item_id,
                source_path: plan.source_path,
                target_path: plan.target_path,
                result: String::from("renamed"),
                message: None,
            }),
            Err(err) => {
                let message = match err.raw_os_error() {
                    Some(32) | Some(33) => {
                        Some(format!("file_in_use_after_retry:{} (os error {})", err, err.raw_os_error().unwrap_or_default()))
                    }
                    _ => Some(err.to_string()),
                };
                results.push(RenameResultItem {
                    item_id: plan.item_id,
                    source_path: plan.source_path,
                    target_path: plan.target_path,
                    result: String::from("failed"),
                    message,
                });
            }
        }
    }

    Ok(results)
}

#[tauri::command]
fn read_preview_file(source_path: String) -> Result<PreviewPayload, String> {
    let source = PathBuf::from(&source_path);
    if !source.exists() {
        return Err(String::from("source_not_found"));
    }

    let ext = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();

    let (kind, mime) = match ext.as_str() {
        "pdf" => ("pdf", "application/pdf"),
        "png" => ("image", "image/png"),
        "jpg" | "jpeg" => ("image", "image/jpeg"),
        _ => return Err(String::from("unsupported_preview_format")),
    };

    let metadata = std::fs::metadata(&source).map_err(|error| format!("read_metadata_failed:{error}"))?;
    if metadata.len() > MAX_PREVIEW_FILE_SIZE {
        return Err(String::from("preview_file_too_large"));
    }

    let bytes = std::fs::read(&source).map_err(|error| format!("read_file_failed:{error}"))?;
    let base64_data = BASE64_STANDARD.encode(bytes);
    let file_name = source
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_string();

    Ok(PreviewPayload {
        kind: String::from(kind),
        mime: String::from(mime),
        base64_data,
        file_name,
    })
}

#[tauri::command]
fn backend_info(state: tauri::State<'_, BackendState>) -> BackendInfo {
    state.info.clone()
}

#[cfg(not(debug_assertions))]
fn available_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

#[cfg(not(debug_assertions))]
fn start_backend(app: &tauri::App) -> Result<BackendState, String> {
    let port = available_loopback_port()?;
    let token = Uuid::new_v4().to_string();
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    std::fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;

    let sidecar = app
        .shell()
        .sidecar("invoice-backend")
        .map_err(|error| error.to_string())?
        .args([
            "--port".to_string(),
            port.to_string(),
            "--token".to_string(),
            token.clone(),
            "--data-dir".to_string(),
            data_dir.to_string_lossy().into_owned(),
        ]);
    let (mut events, child) = sidecar.spawn().map_err(|error| error.to_string())?;
    tauri::async_runtime::spawn(async move {
        while events.recv().await.is_some() {}
    });

    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(BackendState {
                info: BackendInfo {
                    api_base_url: format!("http://127.0.0.1:{port}"),
                    session_token: token,
                },
                child: Mutex::new(Some(child)),
            });
        }
        thread::sleep(Duration::from_millis(120));
    }
    let _ = child.kill();
    Err(String::from("backend_start_timeout"))
}

#[cfg(debug_assertions)]
fn start_backend(_app: &tauri::App) -> Result<BackendState, String> {
    // Development keeps using `npm run dev:api` for reload support.
    Ok(BackendState {
        info: BackendInfo {
            api_base_url: String::from("http://127.0.0.1:8765"),
            session_token: String::new(),
        },
        child: Mutex::new(None),
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let backend = start_backend(app).map_err(std::io::Error::other)?;
            app.manage(backend);

            let restore_item = MenuItem::with_id(
                app,
                "restore-main-window",
                "恢复窗口到主屏",
                true,
                None::<&str>,
            )?;
            let restore_id = restore_item.id().clone();
            let quit_item = MenuItem::with_id(app, "quit-app", "退出程序", true, None::<&str>)?;
            let quit_id = quit_item.id().clone();
            let tray_menu = Menu::with_items(app, &[&restore_item, &quit_item])?;
            let mut tray_builder = TrayIconBuilder::new()
                .menu(&tray_menu)
                .tooltip("发票智能识别并重命名")
                .on_menu_event(move |handle, event| {
                    if event.id() == &restore_id {
                        let _ = restore_main_window(handle);
                    } else if event.id() == &quit_id {
                        handle.exit(0);
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray_builder = tray_builder.icon(icon.clone());
            }
            app.manage(tray_builder.build(app)?);
            watch_window_visibility(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![rename_files, read_preview_file, backend_info])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
            let state = handle.state::<BackendState>();
            if let Ok(mut child) = state.child.lock() {
                if let Some(process) = child.take() {
                    stop_backend(process);
                }
            };
        }
    });
}

#[cfg(test)]
mod window_tests {
    use super::{centered_position, recovery_area, title_bar_is_visible, ScreenRect};

    fn rect(x: i64, y: i64, width: i64, height: i64) -> ScreenRect {
        ScreenRect { x, y, width, height }
    }

    #[test]
    fn leaves_window_with_accessible_title_bar_alone() {
        let areas = [rect(0, 0, 3072, 1824), rect(3072, 0, 1920, 1040)];
        assert!(title_bar_is_visible(rect(2980, 100, 1200, 760), &areas));
        assert!(!title_bar_is_visible(rect(1000, -700, 1200, 760), &areas));
    }

    #[test]
    fn recovers_to_monitor_containing_most_of_window() {
        let areas = [rect(0, 0, 3072, 1824), rect(3072, 0, 1920, 1040)];
        let hidden_title = rect(3200, -100, 1200, 800);
        assert_eq!(recovery_area(hidden_title, &areas), Some(areas[1]));
        assert_eq!(centered_position(hidden_title, areas[1]).x, 3432);
        assert_eq!(centered_position(hidden_title, areas[1]).y, 120);
    }

    #[test]
    fn recovers_from_gap_or_disconnected_monitor() {
        let areas = [rect(-1920, 0, 1920, 1040), rect(0, 0, 3072, 1824)];
        let hidden_window = rect(-5000, 300, 1200, 800);
        assert!(!title_bar_is_visible(hidden_window, &areas));
        assert_eq!(recovery_area(hidden_window, &areas), Some(areas[0]));
        assert_eq!(recovery_area(hidden_window, &[]), None);
    }
}
