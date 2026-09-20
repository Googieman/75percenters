import { COLLECTOR_ERROR_CODES } from "./collector.mjs";

const ERROR_CODE_SET = new Set(Object.values(COLLECTOR_ERROR_CODES));
const RECORD_KEYS = [
  "code",
  "subject",
  "total_hours",
  "attended_hours",
  "absent_hours",
  "source_percentage",
];

export { COLLECTOR_ERROR_CODES };

export function createAttendanceUploadPayload(records) {
  return JSON.stringify({ subjects: records });
}

export function isTrustedPopupSender(sender, runtimeUrl, runtimeId) {
  return (
    sender?.id === runtimeId &&
    sender?.url === new URL("popup.html", runtimeUrl).href
  );
}

export function validateCollectorResult(value) {
  if (!value || typeof value !== "object") {
    return { ok: false, errorCode: COLLECTOR_ERROR_CODES.RESULT_INVALID };
  }
  if (value.ok === false && ERROR_CODE_SET.has(value.errorCode)) {
    return { ok: false, errorCode: value.errorCode };
  }
  if (
    value.ok !== true ||
    !Array.isArray(value.records) ||
    value.records.length === 0 ||
    value.records.some((record) => !isRecord(record))
  ) {
    return { ok: false, errorCode: COLLECTOR_ERROR_CODES.RESULT_INVALID };
  }
  return { ok: true, records: value.records };
}

function isRecord(record) {
  if (!record || typeof record !== "object") return false;
  if (JSON.stringify(Object.keys(record).sort()) !== JSON.stringify([...RECORD_KEYS].sort())) {
    return false;
  }
  return (
    typeof record.code === "string" &&
    record.code.length > 0 &&
    typeof record.subject === "string" &&
    record.subject.length > 0 &&
    Number.isSafeInteger(record.total_hours) &&
    record.total_hours >= 0 &&
    Number.isSafeInteger(record.attended_hours) &&
    record.attended_hours >= 0 &&
    Number.isSafeInteger(record.absent_hours) &&
    record.absent_hours >= 0 &&
    record.attended_hours + record.absent_hours === record.total_hours &&
    typeof record.source_percentage === "string" &&
    /^\d+(?:\.\d+)?$/.test(record.source_percentage) &&
    Number(record.source_percentage) >= 0 &&
    Number(record.source_percentage) <= 100
  );
}
