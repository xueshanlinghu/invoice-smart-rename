export type InvoiceStatus = "pending" | "ok" | "needs_review" | "failed";
export type RenameAction = "rename" | "skip" | "manual_edit_required";
export type ConflictType = "none" | "same_name" | "exists_other";
export type CommitResultStatus = "pending" | "renamed" | "skipped" | "failed";

export interface TaskSummary {
  total: number;
  pending: number;
  ok: number;
  needs_review: number;
  failed: number;
  conflict: number;
  rename_ready: number;
  renamed: number;
  skipped: number;
}

export interface InvoiceItem {
  id: string;
  source_path: string;
  old_name: string;
  file_ext: string;
  invoice_date: string | null;
  item_name: string | null;
  amount: string | null;
  category: string | null;
  vendor_name: string | null;
  extracted_text: string | null;
  status: InvoiceStatus;
  failure_reason: string | null;
  suggested_name: string | null;
  manual_name: string | null;
  selected: boolean;
  action: RenameAction | null;
  conflict_type: ConflictType;
  result: CommitResultStatus;
  result_message: string | null;
  updated_at: string;
}

export interface TaskState {
  id: string;
  created_at: string;
  updated_at: string;
  template: string;
  summary: TaskSummary;
  items: InvoiceItem[];
}

export interface CommitPlanItem {
  item_id: string;
  source_path: string;
  target_path: string;
  old_name: string;
  target_name: string;
  action: RenameAction;
  conflict_type: ConflictType;
  reason: string | null;
}

export interface CommitPlanResponse {
  task_id: string;
  dry_run: boolean;
  plan: CommitPlanItem[];
}

export interface CommitRenameItemResult {
  item_id: string;
  source_path: string;
  target_path: string;
  result: CommitResultStatus;
  message: string | null;
}

export interface CommitRenameResponse {
  task_id: string;
  results: CommitRenameItemResult[];
}

export interface SyncItemPatch {
  item_id: string;
  invoice_date: string | null;
  amount: string | null;
  category: string | null;
}

export interface AppSettings {
  siliconflow_base_url: string;
  siliconflow_model: string;
  siliconflow_models: string[];
  api_key_configured: boolean;
  filename_template: string;
  category_mapping: Record<string, string[]>;
}

export interface AppSettingsUpdate {
  siliconflow_base_url?: string;
  siliconflow_model?: string;
  siliconflow_models?: string[];
  siliconflow_api_key?: string;
  filename_template?: string;
  category_mapping?: Record<string, string[]>;
}
