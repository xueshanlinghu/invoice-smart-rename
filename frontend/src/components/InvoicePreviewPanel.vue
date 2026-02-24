<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NSpin, NSpace, NTag } from "naive-ui";
import type { InvoiceItem, PreviewPayload } from "../api/types";
import { readPreviewFile } from "../api/tauri";

type PreviewKind = "none" | "image" | "pdf";

const props = defineProps<{
  item: InvoiceItem | null;
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

const loading = ref(false);
const errorText = ref("");
const previewKind = ref<PreviewKind>("none");
const previewFileName = ref("");
const imageDataUrl = ref("");
const pdfDataUrl = ref("");
const scale = ref(1);
let requestToken = 0;

const scalePercentText = computed(() => `${Math.round(scale.value * 100)}%`);
const canZoomOut = computed(() => scale.value > 0.5);
const canZoomIn = computed(() => scale.value < 3);
const displayFileName = computed(() => previewFileName.value || props.item?.old_name || "未选择文件");

const fieldRows = computed(() => [
  { label: "开票日期", value: props.item?.invoice_date || "-" },
  { label: "项目名称", value: props.item?.item_name || "-" },
  { label: "类别", value: props.item?.category || "-" },
  { label: "金额", value: props.item?.amount || "-" },
  { label: "状态", value: statusLabel(props.item?.status ?? null) },
]);

const failureReason = computed(() => {
  const reason = props.item?.failure_reason;
  if (!reason) return "";
  if (reason === "api_key_not_configured") return "未配置硅基流动 API Key";
  if (reason === "missing_required_fields") return "缺少关键字段";
  if (reason === "cloud_request_failed") return "云端识别请求失败";
  if (reason === "file_not_found") return "文件不存在";
  return reason;
});

function statusLabel(status: string | null): string {
  if (status === "ok") return "成功";
  if (status === "needs_review") return "待复核";
  if (status === "failed") return "失败";
  if (status === "pending") return "待识别";
  return "-";
}

function resetPreviewState() {
  errorText.value = "";
  previewKind.value = "none";
  previewFileName.value = "";
  imageDataUrl.value = "";
  pdfDataUrl.value = "";
}

function normalizeErrorMessage(rawError: unknown): string {
  const text = String(rawError ?? "");
  if (text.includes("unknown command") || text.includes("read_preview_file")) {
    return "预览命令未生效，请重启桌面进程（npm run tauri:dev）";
  }
  if (text.includes("missing required key")) {
    return "预览参数传递异常，请重启桌面进程后重试";
  }
  if (text.includes("source_not_found")) return "文件不存在或已被移动";
  if (text.includes("unsupported_preview_format")) return "暂不支持该文件格式预览";
  if (text.includes("preview_file_too_large")) return "文件过大，当前不支持内嵌预览";
  if (text.includes("read_file_failed")) return "读取文件失败，请检查文件是否被占用";
  if (text.includes("read_metadata_failed")) return "读取文件信息失败";
  return "预览加载失败";
}

function assignPayload(payload: PreviewPayload) {
  previewFileName.value = payload.file_name;
  scale.value = 1;
  errorText.value = "";

  if (payload.kind === "image") {
    previewKind.value = "image";
    imageDataUrl.value = `data:${payload.mime};base64,${payload.base64_data}`;
    pdfDataUrl.value = "";
    return;
  }

  if (payload.kind === "pdf") {
    previewKind.value = "pdf";
    imageDataUrl.value = "";
    pdfDataUrl.value = `data:${payload.mime};base64,${payload.base64_data}#page=1`;
    return;
  }

  throw new Error("unsupported_preview_kind");
}

async function refreshPreview() {
  const item = props.item;
  if (!props.open || !item) return;

  const currentToken = requestToken + 1;
  requestToken = currentToken;
  loading.value = true;
  errorText.value = "";
  previewFileName.value = item.old_name;

  try {
    const payload = await readPreviewFile(item.source_path);
    if (currentToken !== requestToken) return;
    assignPayload(payload);
  } catch (error) {
    if (currentToken !== requestToken) return;
    resetPreviewState();
    errorText.value = normalizeErrorMessage(error);
  } finally {
    if (currentToken === requestToken) {
      loading.value = false;
    }
  }
}

function applyScale(nextScale: number) {
  const clamped = Math.min(3, Math.max(0.5, Number(nextScale.toFixed(2))));
  if (clamped === scale.value) return;
  scale.value = clamped;
}

function zoomIn() {
  applyScale(scale.value + 0.1);
}

function zoomOut() {
  applyScale(scale.value - 0.1);
}

function resetZoom() {
  applyScale(1);
}

function onWheel(event: WheelEvent) {
  if (!props.open || previewKind.value === "none") return;
  event.preventDefault();
  if (event.deltaY < 0) {
    zoomIn();
  } else {
    zoomOut();
  }
}

watch(
  () => [props.open, props.item?.id] as const,
  async ([open]) => {
    if (!open) return;
    await refreshPreview();
  },
  { immediate: true },
);

watch(
  () => props.open,
  (open) => {
    if (open) return;
    requestToken += 1;
    loading.value = false;
    resetPreviewState();
  },
);
</script>

<template>
  <aside class="preview-panel">
    <header class="preview-header">
      <div>
        <h3>原文件预览</h3>
        <p class="preview-file-name" :title="displayFileName">{{ displayFileName }}</p>
      </div>
      <n-space>
        <n-button size="small" :disabled="!canZoomOut" @click="zoomOut">-</n-button>
        <n-button size="small" :disabled="!canZoomIn" @click="zoomIn">+</n-button>
        <n-button size="small" @click="resetZoom">重置</n-button>
        <n-tag round>{{ scalePercentText }}</n-tag>
        <n-button size="small" tertiary @click="emit('close')">关闭预览</n-button>
      </n-space>
    </header>

    <div class="preview-fields">
      <div class="field-item" v-for="field in fieldRows" :key="field.label">
        <span class="field-label">{{ field.label }}</span>
        <span class="field-value" :title="field.value">{{ field.value }}</span>
      </div>
      <div class="field-item field-failure" v-if="failureReason">
        <span class="field-label">失败原因</span>
        <span class="field-value" :title="failureReason">{{ failureReason }}</span>
      </div>
    </div>

    <div class="preview-body" @wheel="onWheel">
      <n-spin :show="loading" class="preview-spin">
        <div class="preview-content">
          <n-empty v-if="!item" description="请选择一条记录查看预览" />
          <n-empty v-else-if="errorText" :description="errorText" />
          <div v-else-if="previewKind === 'image'" class="image-wrap">
            <img class="preview-image" :src="imageDataUrl" alt="预览图" :style="{ transform: `scale(${scale})` }" />
          </div>
          <div v-else-if="previewKind === 'pdf'" class="pdf-wrap">
            <iframe
              class="preview-pdf-frame"
              :src="pdfDataUrl"
              title="PDF预览"
              :style="{ transform: `scale(${scale})` }"
            />
          </div>
          <n-empty v-else description="暂无可预览内容" />
        </div>
      </n-spin>
    </div>
  </aside>
</template>

<style scoped>
.preview-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(52, 97, 94, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(53, 98, 95, 0.12);
  background: #edf5f4;
}

.preview-header h3 {
  margin: 0;
  font-size: 14px;
  color: #234d53;
}

.preview-file-name {
  margin: 4px 0 0;
  font-size: 12px;
  color: #4e6f76;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(53, 98, 95, 0.12);
  background: rgba(240, 249, 247, 0.55);
}

.field-item {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.field-label {
  flex: 0 0 auto;
  font-size: 12px;
  color: #4b6970;
}

.field-value {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12px;
  color: #1f4f56;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.field-failure {
  grid-column: 1 / -1;
}

.preview-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px 12px 14px;
}

.preview-spin,
.preview-spin :deep(.n-spin-container),
.preview-spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.preview-content {
  height: 100%;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-wrap,
.pdf-wrap {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  overflow: auto;
  padding: 4px;
}

.preview-image,
.preview-pdf-frame {
  transform-origin: top center;
  border: 1px solid rgba(59, 106, 101, 0.16);
  border-radius: 8px;
  box-shadow: 0 5px 18px rgba(30, 75, 71, 0.14);
}

.preview-image {
  max-width: 100%;
}

.preview-pdf-frame {
  width: 100%;
  min-height: 780px;
  background: #fff;
}

@media (max-width: 1200px) {
  .preview-fields {
    grid-template-columns: 1fr;
  }
}
</style>
