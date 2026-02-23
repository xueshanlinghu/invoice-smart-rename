<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  NButton,
  NCheckbox,
  NConfigProvider,
  NDatePicker,
  NDynamicTags,
  NEmpty,
  NInput,
  NInputNumber,
  NMessageProvider,
  NModal,
  NProgress,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
} from "naive-ui";
import Draggable from "vuedraggable";
import { useInvoiceStore } from "./stores/invoice";
import { isTauriRuntime } from "./api/tauri";
import type { InvoiceItem } from "./api/types";

const INVALID_FILENAME_CHAR_PATTERN = /[<>:"/\\|?*\x00-\x1F]/g;
const SETTINGS_LOCAL_API_KEY = "invoice.smart-rename.siliconflow-api-key";
const DEFAULT_TEMPLATE = "{date}-{category}-{amount}";

type MappingRow = { id: string; category: string; keywords: string[] };

type SettingsSnapshot = {
  model: string;
  template: string;
  mappingSignature: string;
  localApiKey: string;
};

const store = useInvoiceStore();
const activeTab = ref("work");

const filenameTemplate = ref(DEFAULT_TEMPLATE);
const selectedModel = ref("Qwen/Qwen3-VL-32B-Instruct");
const apiKeyInput = ref("");
const mappingRows = ref<MappingRow[]>([]);
const settingsSaving = ref(false);
const settingsSaveHint = ref("");
const settingsSnapshot = ref<SettingsSnapshot>({
  model: "",
  template: DEFAULT_TEMPLATE,
  mappingSignature: "",
  localApiKey: "",
});

const showDeleteConfirm = ref(false);
const pendingDeleteRowId = ref<string | null>(null);
const showRenameConfirm = ref(false);
const showClearConfirm = ref(false);
const dragging = ref(false);
let unlistenTauriDrop: null | (() => void) = null;

const summaryText = computed(() => {
  const summary = store.task?.summary;
  if (!summary) return "未导入文件";
  return `总计 ${summary.total} | 待识别 ${summary.pending} | 成功 ${summary.ok} | 待复核 ${summary.needs_review} | 失败 ${summary.failed}`;
});

const selectedCount = computed(() => store.selectedIds.length);
const hasSelection = computed(() => selectedCount.value > 0);
const selectedItems = computed(() => (store.task?.items ?? []).filter((item) => item.selected));
const hasSelectedEmptyNewName = computed(() =>
  selectedItems.value.some((item) => !(item.suggested_name ?? "").trim()),
);
const renameDisabledReason = computed(() => {
  if (!store.hasTask) return "";
  if (!hasSelection.value) return "请先勾选要改名的发票";
  if (hasSelectedEmptyNewName.value) return "选中项存在新文件名为空，请先识别后再改名";
  return "";
});
const canExecuteRename = computed(
  () => store.hasTask && hasSelection.value && !hasSelectedEmptyNewName.value && !store.loading,
);

const modelOptions = computed(() =>
  (store.settings?.siliconflow_models ?? []).map((item) => ({ label: item, value: item })),
);

const apiKeyConfigured = computed(() => Boolean(apiKeyInput.value.trim() || store.settings?.api_key_configured));
const statusBarText = computed(() => store.message || "就绪");
const recognizeProgressText = computed(() => {
  if (!store.recognizeTotal) return "";
  return `识别进度 ${store.recognizeDone}/${store.recognizeTotal}（${store.recognizePercent}%）`;
});

const normalizedTemplatePreview = computed(() => normalizeTemplate(filenameTemplate.value));
const currentMappingSignature = computed(() => mappingSignature(rowsToMapping(mappingRows.value)));
const backendSettingsChanged = computed(
  () => selectedModel.value !== settingsSnapshot.value.model
    || normalizedTemplatePreview.value !== settingsSnapshot.value.template
    || currentMappingSignature.value !== settingsSnapshot.value.mappingSignature,
);
const localApiKeyChanged = computed(() => apiKeyInput.value.trim() !== settingsSnapshot.value.localApiKey);
const hasPendingSettingsChanges = computed(() => backendSettingsChanged.value || localApiKeyChanged.value);

onMounted(async () => {
  await store.loadSettings();
  syncSettingsToForm();
  await bindTauriDropEvents();
});

watch(
  () => store.settings,
  () => {
    syncSettingsToForm();
  },
  { deep: true },
);

function loadLocalApiKey(): string {
  try {
    return localStorage.getItem(SETTINGS_LOCAL_API_KEY)?.trim() || "";
  } catch {
    return "";
  }
}

function persistLocalApiKey(nextValue: string) {
  const value = nextValue.trim();
  try {
    if (value) {
      localStorage.setItem(SETTINGS_LOCAL_API_KEY, value);
    } else {
      localStorage.removeItem(SETTINGS_LOCAL_API_KEY);
    }
  } catch {
    // ignore runtime storage errors
  }
}

function syncSettingsToForm() {
  const settings = store.settings;
  if (!settings) return;

  filenameTemplate.value = normalizeTemplate(settings.filename_template || DEFAULT_TEMPLATE);
  selectedModel.value = settings.siliconflow_model || "Qwen/Qwen3-VL-32B-Instruct";
  mappingRows.value = mappingToRows(settings.category_mapping);

  const localApiKey = loadLocalApiKey();
  apiKeyInput.value = localApiKey;
  store.setSessionApiKey(localApiKey);

  settingsSnapshot.value = {
    model: selectedModel.value,
    template: filenameTemplate.value,
    mappingSignature: mappingSignature(rowsToMapping(mappingRows.value)),
    localApiKey,
  };
}

function nextRowId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function sanitizeCategoryText(raw: string): string {
  return raw.replace(INVALID_FILENAME_CHAR_PATTERN, "");
}

function normalizeTemplate(raw: string): string {
  let value = raw.trim();
  if (!value) {
    return DEFAULT_TEMPLATE;
  }
  value = value.replace(/\{ext\}/gi, "");
  value = value.replace(/\.[A-Za-z0-9]{1,12}$/g, "");
  value = value.replace(/[-_.\s]+$/g, "");
  return value || DEFAULT_TEMPLATE;
}

function normalizeKeywords(values: string[]): string[] {
  const unique = new Set<string>();
  for (const value of values) {
    const cleaned = value.trim();
    if (!cleaned) continue;
    unique.add(cleaned);
  }
  return Array.from(unique);
}

async function saveAllSettings() {
  if (!store.settings) return;
  if (!hasPendingSettingsChanges.value) {
    settingsSaveHint.value = "当前没有需要保存的改动";
    return;
  }

  settingsSaving.value = true;
  try {
    const normalizedTemplate = normalizeTemplate(filenameTemplate.value);
    filenameTemplate.value = normalizedTemplate;
    const mapping = rowsToMapping(mappingRows.value);

    if (backendSettingsChanged.value) {
      await store.saveSettings({
        siliconflow_model: selectedModel.value,
        filename_template: normalizedTemplate,
        category_mapping: mapping,
      });
    }

    const localApiKey = apiKeyInput.value.trim();
    persistLocalApiKey(localApiKey);
    store.setSessionApiKey(localApiKey);

    settingsSnapshot.value = {
      model: selectedModel.value,
      template: normalizedTemplate,
      mappingSignature: mappingSignature(mapping),
      localApiKey,
    };

    settingsSaveHint.value = `配置已保存：${new Date().toLocaleTimeString()}`;
    store.message = "设置已保存";
  } catch {
    // error message handled in store
  } finally {
    settingsSaving.value = false;
  }
}

function mappingToRows(mapping: Record<string, string[]>): MappingRow[] {
  const rows = Object.entries(mapping)
    .filter(([category]) => category.trim() && category.trim() !== "其他")
    .map(([category, keywords]) => ({
      id: nextRowId(),
      category: sanitizeCategoryText(category),
      keywords: normalizeKeywords(keywords),
    }));
  return rows.length ? rows : [{ id: nextRowId(), category: "", keywords: [] }];
}

function rowsToMapping(rows: MappingRow[]): Record<string, string[]> {
  const mapping: Record<string, string[]> = {};
  for (const row of rows) {
    const category = sanitizeCategoryText(row.category).trim();
    if (!category || category === "其他") continue;
    mapping[category] = normalizeKeywords(row.keywords);
  }
  return mapping;
}

function mappingSignature(mapping: Record<string, string[]>): string {
  return JSON.stringify(Object.entries(mapping));
}

function addMappingRow() {
  mappingRows.value.push({
    id: nextRowId(),
    category: "",
    keywords: [],
  });
}

function onMappingCategoryUpdate(row: MappingRow, value: string) {
  row.category = sanitizeCategoryText(value);
}

function onMappingKeywordsUpdate(row: MappingRow, values: string[]) {
  row.keywords = normalizeKeywords(values);
}

function removeMappingRow(id: string) {
  mappingRows.value = mappingRows.value.filter((row) => row.id !== id);
  if (!mappingRows.value.length) {
    addMappingRow();
  }
}

function askRemoveMappingRow(id: string) {
  pendingDeleteRowId.value = id;
  showDeleteConfirm.value = true;
}

function cancelRemoveMappingRow() {
  showDeleteConfirm.value = false;
  pendingDeleteRowId.value = null;
}

function confirmRemoveMappingRow() {
  if (pendingDeleteRowId.value) {
    removeMappingRow(pendingDeleteRowId.value);
  }
  showDeleteConfirm.value = false;
  pendingDeleteRowId.value = null;
}

function normalizeDateValue(raw: string | number | null | undefined): string | null {
  if (raw === null || raw === undefined) return null;
  const digits = String(raw).replace(/\D+/g, "");
  if (digits.length !== 8) return null;
  return digits;
}

function datePickerValue(raw: string | null): string | null {
  return normalizeDateValue(raw);
}

function onDateUpdate(item: InvoiceItem, value: string | null) {
  const normalized = normalizeDateValue(value);
  store.setItemInvoiceDate(item.id, normalized);
}

function onCategoryUpdate(item: InvoiceItem, value: string) {
  store.setItemCategory(item.id, sanitizeCategoryText(value));
}

function parseAmountNumber(raw: string | null): number | null {
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function amountDecimals(raw: string | null): number {
  if (!raw) return 0;
  const matched = raw.match(/\.(\d+)/);
  if (!matched) return 0;
  const trimmed = matched[1].replace(/0+$/g, "");
  return Math.min(2, trimmed.length);
}

function hasFraction(raw: string | null): boolean {
  return amountDecimals(raw) > 0;
}

function amountStep(raw: string | null): number {
  const decimals = amountDecimals(raw);
  if (decimals >= 2) return 0.01;
  if (decimals === 1) return 0.1;
  return 1;
}

function amountPrecision(raw: string | null): number {
  return amountDecimals(raw);
}

function formatAmountForLocal(nextValue: number | null, previousRaw: string | null): string | null {
  if (nextValue === null || !Number.isFinite(nextValue)) {
    return null;
  }
  const normalized = Number(nextValue).toFixed(2).replace(/0+$/g, "").replace(/\.$/, "");
  if (!normalized) return "0";
  if (hasFraction(previousRaw)) {
    return normalized;
  }
  if (Number.isInteger(nextValue)) {
    return String(Math.trunc(nextValue));
  }
  return normalized;
}

function amountEditorValue(item: InvoiceItem): number | null {
  return parseAmountNumber(item.amount);
}

function onAmountValueChange(item: InvoiceItem, value: number | null) {
  const next = formatAmountForLocal(value, item.amount);
  store.setItemAmount(item.id, next);
}

function statusType(item: InvoiceItem): "success" | "warning" | "error" | "default" {
  if (item.status === "ok") return "success";
  if (item.status === "needs_review") return "warning";
  if (item.status === "failed") return "error";
  return "default";
}

function statusLabel(item: InvoiceItem): string {
  if (item.status === "ok") return "成功";
  if (item.status === "needs_review") return "待复核";
  if (item.status === "failed") return "失败";
  return "待识别";
}

function failureReasonLabel(item: InvoiceItem): string {
  if (!item.failure_reason) return "";
  if (item.failure_reason === "api_key_not_configured") return "未配置硅基流动 API Key";
  if (item.failure_reason === "missing_required_fields") return "缺少关键字段";
  if (item.failure_reason === "cloud_request_failed") return "云端识别请求失败";
  if (item.failure_reason === "file_not_found") return "文件不存在";
  return item.failure_reason;
}

function allSelectedNext(): boolean {
  if (!store.task?.items.length) return true;
  const selected = store.task.items.filter((item) => item.selected).length;
  return selected !== store.task.items.length;
}

function toWindowsLikePath(raw: string): string {
  let value = raw.trim();
  if (!value) return "";

  if (value.startsWith("file:///")) {
    value = decodeURIComponent(value.slice(8));
  } else if (value.startsWith("file://")) {
    value = decodeURIComponent(value.slice(7));
  }

  if (/^\/[A-Za-z]:\//.test(value)) {
    value = value.slice(1);
  }
  if (/^[A-Za-z]:\//.test(value)) {
    value = value.replaceAll("/", "\\");
  }
  return value;
}

function extractPathsFromDrop(event: DragEvent): string[] {
  const paths = new Set<string>();
  const transfer = event.dataTransfer;
  if (!transfer) return [];

  for (const file of Array.from(transfer.files)) {
    const maybePath = (file as unknown as { path?: string }).path;
    if (maybePath) paths.add(toWindowsLikePath(maybePath));
  }

  const uriList = transfer.getData("text/uri-list");
  if (uriList) {
    for (const line of uriList.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      if (trimmed.startsWith("file://")) {
        paths.add(toWindowsLikePath(trimmed));
      }
    }
  }

  const plainText = transfer.getData("text/plain");
  if (plainText) {
    for (const line of plainText.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (trimmed.startsWith("file://")) {
        paths.add(toWindowsLikePath(trimmed));
      } else if (/^[A-Za-z]:[\\/]/.test(trimmed)) {
        paths.add(toWindowsLikePath(trimmed));
      }
    }
  }

  return Array.from(paths).filter(Boolean);
}

function onDragOver(event: DragEvent) {
  event.preventDefault();
  dragging.value = true;
}

function onDragLeave(event: DragEvent) {
  event.preventDefault();
  const host = event.currentTarget as HTMLElement | null;
  const related = event.relatedTarget as Node | null;
  if (!host || !related || !host.contains(related)) {
    dragging.value = false;
  }
}

async function importByPaths(paths: string[]) {
  const unique = Array.from(new Set(paths.map((item) => item.trim()).filter(Boolean)));
  if (!unique.length) return;
  await store.importByPaths(unique);
}

async function onDrop(event: DragEvent) {
  event.preventDefault();
  dragging.value = false;
  const paths = extractPathsFromDrop(event);
  if (!paths.length) {
    store.message = "未获取到有效路径，请直接拖入文件或文件夹";
    return;
  }
  await importByPaths(paths);
}

async function bindTauriDropEvents() {
  if (!isTauriRuntime()) return;
  try {
    const api = await import("@tauri-apps/api/webviewWindow");
    const getter = (api as unknown as Record<string, () => unknown>).getCurrentWebviewWindow
      ?? (api as unknown as Record<string, () => unknown>).getCurrentWindow;
    if (!getter) return;
    const win = getter() as {
      onDragDropEvent?: (
        handler: (event: { payload?: { type?: string; paths?: string[] } }) => void,
      ) => Promise<() => void>;
    };
    if (!win.onDragDropEvent) return;

    const unlisten = await win.onDragDropEvent((event) => {
      const raw = event as unknown as {
        type?: string;
        payload?: { type?: string; paths?: string[] } | string[] | null;
      };
      const payload = raw.payload;
      const payloadAsRecord = payload && !Array.isArray(payload) ? payload : null;
      const type = payloadAsRecord?.type || raw.type;

      if (type === "over") {
        dragging.value = true;
        return;
      }

      if (type === "drop" || (!type && Array.isArray(payload))) {
        dragging.value = false;
        const rawPaths = Array.isArray(payload)
          ? payload
          : Array.isArray(payloadAsRecord?.paths)
            ? payloadAsRecord?.paths
            : [];
        const paths = rawPaths.map((item) => toWindowsLikePath(String(item))).filter(Boolean);
        if (paths.length) {
          void importByPaths(paths);
        }
        return;
      }

      dragging.value = false;
    });

    unlistenTauriDrop = unlisten;
  } catch {
    // ignore browser runtime
  }
}

function openRenameConfirm() {
  if (!canExecuteRename.value) {
    store.message = renameDisabledReason.value || "当前不可执行改名";
    return;
  }
  showRenameConfirm.value = true;
}

function cancelRenameConfirm() {
  showRenameConfirm.value = false;
}

async function confirmExecuteRename() {
  showRenameConfirm.value = false;
  await store.executeRename();
}

function openClearConfirm() {
  showClearConfirm.value = true;
}

function cancelClearConfirm() {
  showClearConfirm.value = false;
}

async function confirmClearList() {
  showClearConfirm.value = false;
  await store.clearTaskItems();
}

onUnmounted(() => {
  if (unlistenTauriDrop) {
    unlistenTauriDrop();
    unlistenTauriDrop = null;
  }
});
</script>

<template>
  <n-config-provider>
    <n-message-provider>
      <div class="page-shell">
        <n-tabs v-model:value="activeTab" type="line" class="workspace-tabs">
          <n-tab-pane name="work" tab="发票处理">
            <section class="panel work-panel">
              <div
                class="drop-zone work-drop"
                :class="{ dragging }"
                @dragover="onDragOver"
                @dragleave="onDragLeave"
                @drop="onDrop"
              >
                <div class="drop-title">拖拽发票到此处，直接导入并进入列表</div>
                <div class="drop-tip">仅支持拖拽导入，可拖多个文件或整个文件夹（PDF / PNG / JPG）</div>
              </div>

              <div class="toolbar">
                <n-space>
                  <n-button
                    type="primary"
                    :disabled="!store.hasTask || !hasSelection"
                    :loading="store.loading"
                    @click="store.recognize(store.selectedIds)"
                  >
                    识别选中发票
                  </n-button>
                  <n-button
                    :disabled="!store.hasTask || !hasSelection || store.loading"
                    @click="store.removeSelectedItemsFromList()"
                  >
                    移除选中
                  </n-button>
                  <n-button
                    :disabled="!store.hasTask || !store.task?.items.length || store.loading"
                    @click="openClearConfirm"
                  >
                    清空列表
                  </n-button>
                  <n-button
                    type="warning"
                    :disabled="!canExecuteRename"
                    @click="openRenameConfirm"
                  >
                    执行改名
                  </n-button>
                </n-space>
                <n-space>
                  <n-button size="small" @click="store.toggleSelectAll(allSelectedNext())">
                    {{ allSelectedNext() ? "全选" : "全不选" }}
                  </n-button>
                  <n-tag round>{{ selectedCount }} 已选</n-tag>
                </n-space>
              </div>
              <p v-if="hasSelection && hasSelectedEmptyNewName" class="tip">
                {{ renameDisabledReason }}
              </p>

              <div class="table-head">
                <h2>识别列表</h2>
                <span class="tip">{{ summaryText }}</span>
              </div>

              <n-spin :show="store.loading" class="list-spin">
                <div v-if="!store.task?.items.length" class="empty-wrap">
                  <n-empty description="暂无任务数据" />
                </div>
                <div v-else class="table-wrap compact-table">
                  <table>
                    <colgroup>
                      <col class="col-select" />
                      <col class="col-status" />
                      <col class="col-old-name" />
                      <col class="col-item-name" />
                      <col class="col-date" />
                      <col class="col-category" />
                      <col class="col-amount" />
                      <col class="col-new-name" />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>选中</th>
                        <th>状态</th>
                        <th>原文件名</th>
                        <th>项目名称</th>
                        <th>开票日期</th>
                        <th>类别</th>
                        <th>金额</th>
                        <th>新文件名</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in store.task.items" :key="item.id">
                        <td>
                          <n-checkbox
                            :checked="item.selected"
                            @update:checked="(v) => store.setItemSelected(item.id, Boolean(v))"
                          />
                        </td>
                        <td>
                          <n-tag :type="statusType(item)" size="small" round>{{ statusLabel(item) }}</n-tag>
                          <div v-if="item.status === 'failed' && item.failure_reason" class="row-tip">
                            {{ failureReasonLabel(item) }}
                          </div>
                        </td>
                        <td>
                          <div class="old-name" :title="item.old_name">{{ item.old_name }}</div>
                        </td>
                        <td>
                          <n-input :value="item.item_name ?? ''" size="small" readonly placeholder="项目名称" />
                        </td>
                        <td>
                          <n-date-picker
                            type="date"
                            clearable
                            size="small"
                            value-format="yyyyMMdd"
                            :formatted-value="datePickerValue(item.invoice_date)"
                            placeholder="YYYYMMDD"
                            @update:formatted-value="(v) => onDateUpdate(item, v)"
                          />
                        </td>
                        <td>
                          <n-input
                            :value="item.category ?? ''"
                            size="small"
                            placeholder="类别"
                            @update:value="(v) => onCategoryUpdate(item, v)"
                          />
                        </td>
                        <td>
                          <n-input-number
                            :value="amountEditorValue(item)"
                            size="small"
                            :precision="amountPrecision(item.amount)"
                            :step="amountStep(item.amount)"
                            :min="0"
                            @update:value="(v) => onAmountValueChange(item, v)"
                          />
                        </td>
                        <td>
                          <div class="new-name" :title="item.suggested_name ?? ''">{{ item.suggested_name ?? "-" }}</div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </n-spin>
            </section>
          </n-tab-pane>

          <n-tab-pane name="settings" tab="设置">
            <section class="panel settings-panel">
              <div class="settings-stack">
                <div>
                  <label class="label">云模型配置</label>
                  <div class="setting-row">
                    <span class="setting-label">模型选择</span>
                    <n-select
                      v-model:value="selectedModel"
                      :options="modelOptions"
                      placeholder="选择模型"
                    />
                  </div>
                  <div class="setting-row">
                    <span class="setting-label">硅基流动 API Key</span>
                    <n-input
                      v-model:value="apiKeyInput"
                      type="password"
                      show-password-on="click"
                      placeholder="可输入本机专用 API Key（仅保存到 localStorage）"
                    />
                  </div>
                  <p class="tip">说明：此处 API Key 仅保存到本机 localStorage，不写入 .env 文件。</p>
                  <p class="tip" v-if="apiKeyConfigured">当前已检测到可用 API Key（本地或 .env）</p>
                  <p class="tip" v-else>当前未检测到 API Key，识别会失败</p>
                </div>

                <div>
                  <label class="label">命名模板</label>
                  <n-input
                    v-model:value="filenameTemplate"
                    placeholder="{date}-{category}-{amount}"
                  />
                  <p class="tip">扩展名固定沿用原文件扩展名，模板不允许修改扩展名。</p>
                  <p class="tip">可用变量：{date}、{category}、{amount}</p>
                </div>

                <div class="mapping-section">
                  <div class="mapping-head">
                    <label class="label">关键词映射</label>
                    <n-button size="small" class="mapping-add-btn" @click="addMappingRow">新增一行</n-button>
                  </div>
                  <p class="tip">无需配置“其他”，未命中关键词时自动归类为“其他”。</p>
                  <div class="mapping-table">
                    <div class="mapping-row mapping-row-head">
                      <div>优先级 / 类别</div>
                      <div>关键词（回车生成标签）</div>
                      <div>操作</div>
                    </div>
                    <Draggable
                      v-model="mappingRows"
                      item-key="id"
                      handle=".mapping-drag-handle"
                      class="mapping-draggable-list"
                      ghost-class="mapping-row-ghost"
                      chosen-class="mapping-row-chosen"
                      drag-class="mapping-row-drag"
                      :animation="160"
                      :force-fallback="true"
                      :fallback-on-body="true"
                      :fallback-tolerance="2"
                    >
                      <template #item="{ element: row, index }">
                        <div class="mapping-row">
                          <div class="mapping-category-cell">
                            <span class="mapping-order-badge">{{ index + 1 }}</span>
                            <n-input
                              :value="row.category"
                              placeholder="例如：餐饮"
                              @update:value="(v) => onMappingCategoryUpdate(row, v)"
                            />
                          </div>
                          <n-dynamic-tags
                            class="mapping-keywords"
                            :value="row.keywords"
                            :input-style="{ width: '240px', minWidth: '240px' }"
                            :input-props="{ placeholder: '输入关键词后回车' }"
                            @update:value="onMappingKeywordsUpdate(row, $event)"
                          />
                          <n-space class="mapping-actions" :size="6">
                            <button
                              type="button"
                              class="mapping-drag-handle"
                              title="拖拽调整优先级"
                            >
                              拖拽排序
                            </button>
                            <n-button size="small" quaternary @click="askRemoveMappingRow(row.id)">删除</n-button>
                          </n-space>
                        </div>
                      </template>
                    </Draggable>
                  </div>
                  <p class="tip">可拖拽“拖拽”手柄调整优先级。匹配从上到下，命中第一条类别后立即停止；未命中则归类为“其他”。</p>
                </div>

                <div class="settings-actions">
                  <n-button
                    type="primary"
                    :loading="settingsSaving"
                    :disabled="!hasPendingSettingsChanges"
                    @click="saveAllSettings"
                  >
                    保存配置
                  </n-button>
                  <span class="tip" v-if="settingsSaveHint">{{ settingsSaveHint }}</span>
                  <span class="tip" v-else-if="hasPendingSettingsChanges">有未保存的设置改动</span>
                </div>
              </div>
            </section>
          </n-tab-pane>
        </n-tabs>

        <div class="status-bar">
          <div class="status-meta">
            <span class="status-main">{{ statusBarText }}</span>
            <span class="status-summary">{{ summaryText }}</span>
          </div>
          <div v-if="store.isRecognizing || store.recognizeTotal > 0" class="status-progress-wrap">
            <n-progress
              class="status-progress"
              type="line"
              :percentage="store.recognizePercent"
              :show-indicator="false"
              :height="8"
              :processing="store.isRecognizing"
            />
            <span class="status-progress-text">{{ recognizeProgressText }}</span>
          </div>
        </div>

        <n-modal
          v-model:show="showDeleteConfirm"
          preset="dialog"
          title="删除确认"
          positive-text="确认"
          negative-text="取消"
          @positive-click="confirmRemoveMappingRow"
          @negative-click="cancelRemoveMappingRow"
          @after-leave="cancelRemoveMappingRow"
        >
          确认删除这条映射？
        </n-modal>

        <n-modal
          v-model:show="showRenameConfirm"
          preset="dialog"
          title="确认改名"
          positive-text="确认执行"
          negative-text="取消"
          @positive-click="confirmExecuteRename"
          @negative-click="cancelRenameConfirm"
          @after-leave="cancelRenameConfirm"
        >
          将对已选中的发票执行改名操作，是否继续？
        </n-modal>

        <n-modal
          v-model:show="showClearConfirm"
          preset="dialog"
          title="清空确认"
          positive-text="确认清空"
          negative-text="取消"
          @positive-click="confirmClearList"
          @negative-click="cancelClearConfirm"
          @after-leave="cancelClearConfirm"
        >
          仅清空当前列表，不会删除实际文件。确认继续？
        </n-modal>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>
