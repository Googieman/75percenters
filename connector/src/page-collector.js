globalThis.__srmTrackerCollectAttendance = async () => {
  const CODES = {
    AMBIGUOUS_FORM: "AMBIGUOUS_FORM",
    CONTEXT_INVALID: "CONTEXT_INVALID",
    LOGIN_REQUIRED: "LOGIN_REQUIRED",
    NAVIGATION_CHANGED: "NAVIGATION_CHANGED",
    REQUEST_FAILED: "REQUEST_FAILED",
    RESPONSE_INVALID: "RESPONSE_INVALID",
    TIMEOUT: "TIMEOUT",
    WRONG_FRAME: "WRONG_FRAME",
  };
  const endpoint =
    "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp";
  const requiredField = "hdnFormDetails";
  const supportedFields = [
    "iden",
    "filter",
    "hidchkHostelOpen",
    "hdnFormStatus",
    "hdnFormId",
    "hdnFormDetails",
    "hdnFilename",
    "csrfPreventionSalt",
  ];

  const fail = (errorCode) => ({ ok: false, errorCode });
  const normalize = (value) => value.replace(/\s+/g, " ").trim();
  const normalizeHeader = (value) => normalize(value).toLocaleLowerCase();
  const wholeNumber = (value) => (/^\d+$/.test(value) ? Number(value) : null);

  const parseResponse = (html) => {
    const document = new DOMParser().parseFromString(html, "text/html");
    if (
      document.querySelector("form input[type='password']") ||
      /login/i.test(document.title || "")
    ) {
      return fail(CODES.LOGIN_REQUIRED);
    }
    const expected = [
      ["code"],
      ["description"],
      ["max. hours"],
      ["attended hours", "att. hours"],
      ["absent hours"],
      ["total percentage"],
    ];
    for (const table of document.querySelectorAll("table")) {
      const rows = [...table.querySelectorAll("tr")];
      for (const [index, row] of rows.entries()) {
        const headers = [...row.children].filter((cell) => ["TH", "TD"].includes(cell.tagName));
        const values = headers.map((cell) => normalizeHeader(cell.textContent || ""));
        if (
          values.length !== expected.length ||
          values.some((value, i) => !expected[i].includes(value))
        ) {
          continue;
        }
        const records = [];
        for (const dataRow of rows.slice(index + 1)) {
          const cells = [...dataRow.children].filter((cell) => cell.tagName === "TD");
          if (!cells.length) continue;
          if (cells.length !== 6) return fail(CODES.RESPONSE_INVALID);
          const [code, subject, total, attended, absent, percentage] = cells.map((cell) =>
            normalize(cell.textContent || ""),
          );
          const totalHours = wholeNumber(total);
          const attendedHours = wholeNumber(attended);
          const absentHours = wholeNumber(absent);
          const sourcePercentage = percentage.endsWith("%")
            ? percentage.slice(0, -1).trim()
            : percentage;
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
            return fail(CODES.RESPONSE_INVALID);
          }
          records.push({
            code,
            subject,
            total_hours: totalHours,
            attended_hours: attendedHours,
            absent_hours: absentHours,
            source_percentage: sourcePercentage,
          });
        }
        return records.length ? records : fail(CODES.RESPONSE_INVALID);
      }
    }
    return fail(CODES.RESPONSE_INVALID);
  };

  if (window.top !== window.self) return fail(CODES.WRONG_FRAME);
  const startUrl = window.location.href;
  const forms = [...document.forms].filter((form) =>
    [...form.elements].filter((control) => control.name === requiredField).length > 0,
  );
  if (forms.length !== 1) {
    return fail(forms.length > 1 ? CODES.AMBIGUOUS_FORM : CODES.CONTEXT_INVALID);
  }
  if (!hasAttendanceTable(document)) return fail(CODES.CONTEXT_INVALID);

  const form = forms[0];
  const data = new URLSearchParams();
  for (const name of supportedFields) {
    const matches = controls(name);
    if (matches.length > 1) return fail(CODES.AMBIGUOUS_FORM);
    if (matches.length === 1 && isSuccessfulControl(matches[0])) {
      data.set(name, matches[0].value || "");
    }
  }

  const controller = new AbortController();
  let timer;
  try {
    const body = await Promise.race([
      fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: data.toString(),
        signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok) throw new Error("request failed");
        return response.text();
      }),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new Error("timeout"));
        }, 30_000);
      }),
    ]);
    if (window.location.href !== startUrl) return fail(CODES.NAVIGATION_CHANGED);
    const parsed = parseResponse(body);
    return Array.isArray(parsed) ? { ok: true, records: parsed } : parsed;
  } catch (error) {
    if (error?.message === "timeout" || controller.signal.aborted) {
      return fail(CODES.TIMEOUT);
    }
    return fail(CODES.REQUEST_FAILED);
  } finally {
    if (timer) clearTimeout(timer);
  }

  function controls(name) {
    return [...form.elements].filter((control) => control.name === name);
  }

  function isSuccessfulControl(control) {
    if (control.disabled) return false;
    if (["button", "file", "reset", "submit"].includes(control.type)) return false;
    if (["checkbox", "radio"].includes(control.type) && !control.checked) return false;
    return true;
  }

  function hasAttendanceTable(pageDocument) {
    const expected = [
      ["code"],
      ["description"],
      ["max. hours"],
      ["attended hours", "att. hours"],
      ["absent hours"],
      ["total percentage"],
    ];
    return [...pageDocument.querySelectorAll("table")].some((table) =>
      [...table.querySelectorAll("tr")].some((row) => {
        const headers = [...row.children].filter((cell) => ["TH", "TD"].includes(cell.tagName));
        const values = headers.map((cell) => normalizeHeader(cell.textContent || ""));
        return (
          values.length === expected.length &&
          values.every((value, index) => expected[index].includes(value))
        );
      }),
    );
  }
};
