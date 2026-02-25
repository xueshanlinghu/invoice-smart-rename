import type { InvoiceItem } from "../api/types";

const INVALID_FILENAME_PATTERN = /[<>:"/\\|?*\x00-\x1F]+/g;
const WHITESPACE_PATTERN = /\s+/g;
const EXT_SUFFIX_PATTERN = /\.[A-Za-z0-9]{1,12}$/;

function normalizeSpaces(value: string): string {
  return value.replace(WHITESPACE_PATTERN, " ").trim();
}

function sanitizeComponent(value: string, fallback = "未命名"): string {
  let text = normalizeSpaces(value);
  text = text.replace(INVALID_FILENAME_PATTERN, "-");
  text = text.replace(/[. ]+$/g, "");
  if (!text) return fallback;
  return text;
}

function normalizeBaseName(value: string, ext: string): string {
  let base = sanitizeComponent(value, "未命名");
  const extValue = `.${ext.toLowerCase()}`;
  if (base.toLowerCase().endsWith(extValue)) {
    base = base.slice(0, -extValue.length);
  } else if (EXT_SUFFIX_PATTERN.test(base)) {
    base = base.replace(EXT_SUFFIX_PATTERN, "");
  }
  return sanitizeComponent(base, "未命名");
}

function formatDate(dateValue: string | null): string {
  if (!dateValue) return "19700101";
  const digits = dateValue.replace(/\D+/g, "");
  if (digits.length === 8) return digits;
  return dateValue.replace(/-/g, "");
}

function formatAmount(amount: string | null): string {
  if (!amount) return "0元";
  const value = Number(amount);
  if (!Number.isFinite(value)) return "0元";
  const normalized = value.toFixed(2).replace(/0+$/g, "").replace(/\.$/, "");
  return `${normalized || "0"}元`;
}

function renderTemplate(
  template: string,
  tokens: {
    date: string;
    category: string;
    amount: string;
    ext: string;
  },
): string {
  return template
    .replace(/\{date\}/g, tokens.date)
    .replace(/\{category\}/g, tokens.category)
    .replace(/\{amount\}/g, tokens.amount)
    .replace(/\{ext\}/g, tokens.ext);
}

export function applyNamePreviewLocal(items: InvoiceItem[], template: string): void {
  const counters = new Map<string, number>();
  const ordered = [...items].sort((left, right) => {
    const dateCompare = (left.invoice_date ?? "").localeCompare(right.invoice_date ?? "", "zh-CN");
    if (dateCompare !== 0) return dateCompare;
    return left.old_name.toLowerCase().localeCompare(right.old_name.toLowerCase(), "zh-CN");
  });

  for (const item of ordered) {
    item.action = "skip";
    item.conflict_type = "none";

    if (item.status === "pending" || item.status === "failed") {
      item.suggested_name = null;
      item.action = "manual_edit_required";
      continue;
    }

    const groupKey = `${item.invoice_date ?? ""}|${item.category ?? "其他"}|${item.amount ?? "0.00"}`;
    const nextCount = (counters.get(groupKey) ?? 0) + 1;
    counters.set(groupKey, nextCount);

    let category = item.category || "其他";
    if (nextCount > 1) {
      category = `${category}${nextCount}`;
    }

    const ext = item.file_ext.replace(/^\./, "").toLowerCase();
    const rendered = renderTemplate(template, {
      date: formatDate(item.invoice_date),
      category: sanitizeComponent(category, "其他"),
      amount: sanitizeComponent(formatAmount(item.amount), "0元"),
      ext,
    });

    const baseName = normalizeBaseName(rendered, ext);
    item.suggested_name = `${baseName}.${ext}`;
    item.action = "rename";
  }
}
