use serde::{Deserialize, Serialize};
use std::path::PathBuf;

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

        match std::fs::rename(&source, &target) {
            Ok(_) => results.push(RenameResultItem {
                item_id: plan.item_id,
                source_path: plan.source_path,
                target_path: plan.target_path,
                result: String::from("renamed"),
                message: None,
            }),
            Err(err) => results.push(RenameResultItem {
                item_id: plan.item_id,
                source_path: plan.source_path,
                target_path: plan.target_path,
                result: String::from("failed"),
                message: Some(err.to_string()),
            }),
        }
    }

    Ok(results)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![rename_files])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

