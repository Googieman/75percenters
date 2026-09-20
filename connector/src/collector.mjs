export const ATTENDANCE_ENDPOINT =
  "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp";

export const COLLECTOR_ERROR_CODES = Object.freeze({
  AMBIGUOUS_FORM: "AMBIGUOUS_FORM",
  CONTEXT_INVALID: "CONTEXT_INVALID",
  LOGIN_REQUIRED: "LOGIN_REQUIRED",
  NAVIGATION_CHANGED: "NAVIGATION_CHANGED",
  REQUEST_FAILED: "REQUEST_FAILED",
  RESPONSE_INVALID: "RESPONSE_INVALID",
  RESULT_INVALID: "RESULT_INVALID",
  TIMEOUT: "TIMEOUT",
  WRONG_FRAME: "WRONG_FRAME",
});

const REQUIRED_FORM_FIELD = "hdnFormDetails";
const SUPPORTED_FORM_FIELDS = [
  "iden",
  "filter",
  "hidchkHostelOpen",
  "hdnFormStatus",
  "hdnFormId",
  "hdnFormDetails",
  "hdnFilename",
  "csrfPreventionSalt",
];
const HEADER_VARIANTS = {
  code: new Set(["code"]),
  subject: new Set(["description"]),
  total_hours: new Set(["max. hours"]),
  attended_hours: new Set(["attended hours", "att. hours"]),
  absent_hours: new Set(["absent hours"]),
  source_percentage: new Set(["total percentage"]),
};

const failure = (errorCode) => ({ ok: false, errorCode });

export function parseCollectorResponse(html, Parser = globalThis.DOMParser) {
  if (typeof Parser !== "function") return failure(COLLECTOR_ERROR_CODES.RESPONSE_INVALID);
  const document = new Parser().parseFromString(html, "text/html");
  if (
    document.querySelector("form input[type='password']") ||
    /login/i.test(document.title || "")
  ) {
    return failure(COLLECTOR_ERROR_CODES.LOGIN_REQUIRED);
  }

  for (const table of document.querySelectorAll("table")) {
    const rows = [...table.querySelectorAll("tr")];
    for (const [index, row] of rows.entries()) {
      const headers = [...row.children].filter((cell) => ["TH", "TD"].includes(cell.tagName));
      const normalized = headers.map((cell) => normalizeHeader(cell.textContent || ""));
      if (!matchesHeaders(normalized)) continue;

      const records = [];
      for (const dataRow of rows.slice(index + 1)) {
        const cells = [...dataRow.children].filter((cell) => cell.tagName === "TD");
        if (cells.length === 0) continue;
        if (cells.length !== 6) return failure(COLLECTOR_ERROR_CODES.RESPONSE_INVALID);
        const record = parseRecord(cells.map((cell) => normalize(cell.textContent || "")));
        if (!record) return failure(COLLECTOR_ERROR_CODES.RESPONSE_INVALID);
        records.push(record);
      }
      return records.length > 0 ? records : failure(COLLECTOR_ERROR_CODES.RESPONSE_INVALID);
    }
  }
  return failure(COLLECTOR_ERROR_CODES.RESPONSE_INVALID);
}

export async function collectAttendance({
  document,
  fetchImpl = globalThis.fetch,
  isTopLevel = () => true,
  locationHref = () => globalThis.location?.href || "",
  timeoutMs = 30_000,
}) {
  if (!isTopLevel()) return failure(COLLECTOR_ERROR_CODES.WRONG_FRAME);
  if (!document || typeof fetchImpl !== "function") {
    return failure(COLLECTOR_ERROR_CODES.CONTEXT_INVALID);
  }

  const startUrl = locationHref();
  const forms = [...document.forms].filter((form) =>
    namedControls(form, REQUIRED_FORM_FIELD).length > 0,
  );
  if (forms.length !== 1) {
    return failure(
      forms.length > 1
        ? COLLECTOR_ERROR_CODES.AMBIGUOUS_FORM
        : COLLECTOR_ERROR_CODES.CONTEXT_INVALID,
    );
  }
  if (!hasAttendanceTable(document)) return failure(COLLECTOR_ERROR_CODES.CONTEXT_INVALID);

  const form = forms[0];
  const formData = new URLSearchParams();
  for (const name of SUPPORTED_FORM_FIELDS) {
    const controls = namedControls(form, name);
    if (controls.length > 1) return failure(COLLECTOR_ERROR_CODES.AMBIGUOUS_FORM);
    if (controls.length === 1 && isSuccessfulControl(controls[0])) {
      formData.set(name, controls[0].value || "");
    }
  }

  const controller = new AbortController();
  let timer;
  try {
    const body = await Promise.race([
      Promise.resolve()
        .then(() =>
          fetchImpl(ATTENDANCE_ENDPOINT, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString(),
            signal: controller.signal,
          }),
        )
        .then(async (response) => {
          if (!response?.ok) throw new Error("request failed");
          return response.text();
        }),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new Error("timeout"));
        }, timeoutMs);
      }),
    ]);

    if (locationHref() !== startUrl) return failure(COLLECTOR_ERROR_CODES.NAVIGATION_CHANGED);
    const parser = document.defaultView?.DOMParser || globalThis.DOMParser;
    const parsed = parseCollectorResponse(body, parser);
    return Array.isArray(parsed) ? { ok: true, records: parsed } : parsed;
  } catch (error) {
    if (error?.message === "timeout" || controller.signal.aborted) {
      return failure(COLLECTOR_ERROR_CODES.TIMEOUT);
    }
    return failure(COLLECTOR_ERROR_CODES.REQUEST_FAILED);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function namedControls(form, name) {
  return [...form.elements].filter((control) => control.name === name);
}

function isSuccessfulControl(control) {
  if (control.disabled) return false;
  if (["button", "file", "reset", "submit"].includes(control.type)) return false;
  if (["checkbox", "radio"].includes(control.type) && !control.checked) return false;
  return true;
}

function matchesHeaders(headers) {
  const fields = Object.values(HEADER_VARIANTS);
  return headers.length === fields.length && headers.every((header, index) => fields[index].has(header));
}

function hasAttendanceTable(document) {
  return [...document.querySelectorAll("table")].some((table) =>
    [...table.querySelectorAll("tr")].some((row) => {
      const headers = [...row.children].filter((cell) => ["TH", "TD"].includes(cell.tagName));
      return matchesHeaders(headers.map((cell) => normalizeHeader(cell.textContent || "")));
    }),
  );
}

function parseRecord(cells) {
  const [code, subject, total, attended, absent, percentage] = cells;
  const totalHours = wholeNumber(total);
  const attendedHours = wholeNumber(attended);
  const absentHours = wholeNumber(absent);
  const sourcePercentage = percentage.endsWith("%") ? percentage.slice(0, -1).trim() : percentage;
  const numericPercentage = Number(sourcePercentage);
  if (
    !code ||
    !subject ||
    totalHours === null ||
    attendedHours === null ||
    absentHours === null ||
    attendedHours + absentHours !== totalHours ||
    !Number.isFinite(numericPercentage) ||
    numericPercentage < 0 ||
    numericPercentage > 100
  ) {
    return null;
  }
  return {
    code,
    subject,
    total_hours: totalHours,
    attended_hours: attendedHours,
    absent_hours: absentHours,
    source_percentage: sourcePercentage,
  };
}

function wholeNumber(value) {
  return /^\d+$/.test(value) ? Number(value) : null;
}

function normalize(value) {
  return value.replace(/\s+/g, " ").trim();
}

function normalizeHeader(value) {
  return normalize(value).toLocaleLowerCase();
}
