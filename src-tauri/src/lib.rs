use base64::{
    engine::general_purpose::STANDARD as BASE64_STANDARD,
    Engine as _,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

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

const MAX_PREVIEW_FILE_SIZE: u64 = 20 * 1024 * 1024;
const RENAME_MAX_RETRIES: u32 = 10;
const RENAME_RETRY_DELAY_MS: u64 = 180;

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![rename_files, read_preview_file])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
