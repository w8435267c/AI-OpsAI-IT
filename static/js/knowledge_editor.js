(function () {
  "use strict";

  const DEBOUNCE_MS = 2000;
  const editor = document.querySelector("#knowledge-editor");
  if (!editor) {
    return;
  }

  const status = editor.querySelector("#autosave-status");
  const reloadLink = editor.querySelector("#autosave-reload");
  const manualSaveButton = editor.querySelector("#manual-save-button");
  const versionLabel = document.querySelector("#working-version-label");
  const lockLabel = document.querySelector("#working-lock-label");
  const restoredFromRow = document.querySelector("#restored-from-row");
  const restoredFromLabel = document.querySelector("#restored-from-label");
  const csrfToken = editor.querySelector('[name="csrfmiddlewaretoken"]');
  const draftId = editor.querySelector('[name="draft_id"]');
  const lockVersion = editor.querySelector('[name="expected_lock_version"]');
  const title = editor.querySelector('[name="title"]');
  const summary = editor.querySelector('[name="summary"]');
  const scope = editor.querySelector('[name="applicable_scope"]');
  const bodyText = editor.querySelector('[name="body_text"]');
  const changeSummary = editor.querySelector('[name="change_summary"]');
  const fields = [title, summary, scope, bodyText, changeSummary];
  let pageVersion = Number(editor.dataset.versionNo);
  const autosaveUrl = editor.dataset.autosaveUrl;
  const saveUrl = editor.dataset.saveUrl;

  if (
    !status ||
    !reloadLink ||
    !manualSaveButton ||
    !versionLabel ||
    !lockLabel ||
    !csrfToken ||
    !draftId ||
    !lockVersion ||
    !autosaveUrl ||
    !saveUrl ||
    !Number.isInteger(pageVersion) ||
    fields.some((field) => !field)
  ) {
    return;
  }

  let debounceTimer = null;
  let inFlight = false;
  let dirty = false;
  let blocked = false;
  let manualPending = false;
  let manualInFlight = false;

  function setStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state;
  }

  function clearDebounce() {
    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  function blockAutosave(message) {
    blocked = true;
    manualPending = false;
    clearDebounce();
    manualSaveButton.disabled = true;
    reloadLink.hidden = false;
    setStatus(message, "blocked");
  }

  function setFieldsDisabled(disabled) {
    fields.forEach((field) => {
      field.disabled = disabled;
    });
  }

  function scheduleAutosave() {
    clearDebounce();
    if (blocked || inFlight || !dirty) {
      return;
    }
    if (manualPending || manualInFlight) {
      return;
    }
    debounceTimer = window.setTimeout(attemptAutosave, DEBOUNCE_MS);
  }

  function buildSnapshot() {
    let parsedScope;
    try {
      parsedScope = JSON.parse(scope.value);
    } catch (error) {
      throw new Error("适用范围不是有效的 JSON 对象。");
    }
    if (
      parsedScope === null ||
      Array.isArray(parsedScope) ||
      typeof parsedScope !== "object"
    ) {
      throw new Error("适用范围不是有效的 JSON 对象。");
    }

    const expectedLockVersion = Number(lockVersion.value);
    if (!Number.isInteger(expectedLockVersion) || expectedLockVersion < 1) {
      throw new Error("当前草稿锁版本无效，请重新加载页面。");
    }

    return {
      draft_id: draftId.value,
      expected_lock_version: expectedLockVersion,
      title: title.value,
      summary: summary.value,
      applicable_scope: parsedScope,
      body_text: bodyText.value,
      change_summary: changeSummary.value,
    };
  }

  function safeErrorMessage(payload, fallback) {
    if (
      payload &&
      payload.error &&
      typeof payload.error.message === "string" &&
      payload.error.message
    ) {
      return payload.error.message;
    }
    return fallback;
  }

  async function attemptAutosave() {
    debounceTimer = null;
    if (blocked || inFlight || !dirty) {
      return;
    }
    if (manualPending || manualInFlight) {
      return;
    }

    let snapshot;
    try {
      snapshot = buildSnapshot();
    } catch (error) {
      setStatus(error.message, "invalid");
      return;
    }

    dirty = false;
    inFlight = true;
    let scheduleNext = false;
    let autosaveSucceeded = false;
    setStatus("自动保存中…", "saving");

    try {
      const response = await fetch(autosaveUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken.value,
        },
        body: JSON.stringify(snapshot),
      });

      let payload = null;
      if ((response.headers.get("Content-Type") || "").includes("application/json")) {
        try {
          payload = await response.json();
        } catch (error) {
          payload = null;
        }
      }

      if (!response.ok) {
        dirty = true;
        if (response.status === 400) {
          setStatus(
            safeErrorMessage(payload, "当前内容无法自动保存，请检查输入。"),
            "invalid",
          );
          return;
        }
        if (response.status === 409) {
          blockAutosave("该草稿已在其他窗口更新，请重新加载后继续编辑。");
          return;
        }
        if (response.status === 403 || response.status === 404) {
          blockAutosave("权限已变化或页面状态已失效，请重新加载。");
          return;
        }
        if (response.status >= 500) {
          blockAutosave("自动保存暂不可用，请重新加载确认后再继续。");
          return;
        }
        blockAutosave("自动保存失败，请重新加载页面确认。");
        return;
      }

      if (
        !payload ||
        payload.ok !== true ||
        !payload.draft ||
        payload.draft.id !== snapshot.draft_id ||
        payload.draft.version_no !== pageVersion ||
        !Number.isInteger(payload.draft.lock_version) ||
        payload.draft.lock_version < 1
      ) {
        dirty = true;
        blockAutosave("服务器返回的草稿状态与当前页面不一致，请重新加载。");
        return;
      }

      lockVersion.value = String(payload.draft.lock_version);
      autosaveSucceeded = true;
      if (dirty) {
        setStatus("有未保存修改", "dirty");
        scheduleNext = true;
      } else {
        setStatus("已自动保存", "saved");
      }
    } catch (error) {
      dirty = true;
      blockAutosave(
        "自动保存结果未知，请重新加载页面确认，当前页面内容不会被自动覆盖。",
      );
    } finally {
      inFlight = false;
      if (manualPending) {
        if (autosaveSucceeded && !blocked) {
          startManualSave();
        } else if (!blocked) {
          manualPending = false;
          manualSaveButton.disabled = false;
        }
      } else if (scheduleNext && dirty && !blocked) {
        scheduleAutosave();
      }
    }
  }

  function isPlainObject(value) {
    return value !== null && !Array.isArray(value) && typeof value === "object";
  }

  function isValidManualResponse(payload, snapshot) {
    return (
      payload &&
      payload.ok === true &&
      payload.saved &&
      payload.saved.id === snapshot.draft_id &&
      payload.saved.version_no === pageVersion &&
      payload.saved.status === "saved" &&
      Number.isInteger(payload.saved.lock_version) &&
      payload.saved.lock_version > 0 &&
      payload.draft &&
      typeof payload.draft.id === "string" &&
      payload.draft.id !== snapshot.draft_id &&
      Number.isInteger(payload.draft.version_no) &&
      payload.draft.version_no > 0 &&
      payload.draft.status === "draft" &&
      typeof payload.draft.status_label === "string" &&
      Number.isInteger(payload.draft.lock_version) &&
      payload.draft.lock_version > 0 &&
      typeof payload.draft.title === "string" &&
      typeof payload.draft.summary === "string" &&
      isPlainObject(payload.draft.applicable_scope) &&
      typeof payload.draft.body_text === "string" &&
      typeof payload.draft.change_summary === "string" &&
      (payload.draft.restored_from_version_no === null ||
        (Number.isInteger(payload.draft.restored_from_version_no) &&
          payload.draft.restored_from_version_no > 0))
    );
  }

  function applyManualResponse(payload) {
    draftId.value = payload.draft.id;
    editor.dataset.versionNo = String(payload.draft.version_no);
    pageVersion = payload.draft.version_no;
    lockVersion.value = String(payload.draft.lock_version);
    title.value = payload.draft.title;
    summary.value = payload.draft.summary;
    scope.value = JSON.stringify(payload.draft.applicable_scope, null, 2);
    bodyText.value = payload.draft.body_text;
    changeSummary.value = payload.draft.change_summary;
    versionLabel.textContent = `v${payload.draft.version_no} · ${payload.draft.status_label}`;
    lockLabel.textContent = `锁版本 ${payload.draft.lock_version}`;
    if (restoredFromRow && restoredFromLabel) {
      if (payload.draft.restored_from_version_no === null) {
        restoredFromRow.hidden = true;
      } else {
        restoredFromLabel.textContent = `恢复自 v${payload.draft.restored_from_version_no}`;
        restoredFromRow.hidden = false;
      }
    }
  }

  async function startManualSave() {
    if (blocked || manualInFlight || !manualPending) {
      return;
    }

    clearDebounce();
    let snapshot;
    try {
      snapshot = buildSnapshot();
    } catch (error) {
      manualPending = false;
      manualSaveButton.disabled = false;
      setStatus(error.message, "invalid");
      return;
    }

    manualPending = false;
    manualInFlight = true;
    dirty = false;
    setFieldsDisabled(true);
    manualSaveButton.disabled = true;
    setStatus("正在保存版本…", "saving");

    try {
      const response = await fetch(saveUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken.value,
        },
        body: JSON.stringify(snapshot),
      });

      let payload = null;
      if ((response.headers.get("Content-Type") || "").includes("application/json")) {
        try {
          payload = await response.json();
        } catch (error) {
          payload = null;
        }
      }

      if (!response.ok) {
        dirty = true;
        if (response.status === 400) {
          setStatus(
            safeErrorMessage(payload, "当前内容无法保存版本，请检查输入。"),
            "invalid",
          );
          return;
        }
        if (response.status === 409) {
          blockAutosave("草稿版本已发生变化，请重新加载后确认当前工作版本。");
          return;
        }
        if (response.status === 403 || response.status === 404) {
          blockAutosave("权限已变化或页面状态已失效，请重新加载。");
          return;
        }
        if (response.status >= 500) {
          blockAutosave("版本保存暂不可用，请重新加载确认服务器当前草稿。");
          return;
        }
        blockAutosave("版本保存失败，请重新加载页面确认服务器当前草稿。");
        return;
      }

      if (!isValidManualResponse(payload, snapshot)) {
        dirty = true;
        blockAutosave("服务器返回的版本状态与当前页面不一致，请重新加载。");
        return;
      }

      applyManualResponse(payload);
      dirty = false;
      clearDebounce();
      setStatus(
        `版本 v${payload.saved.version_no} 已保存，已进入 v${payload.draft.version_no} 继续编辑`,
        "saved",
      );
    } catch (error) {
      dirty = true;
      blockAutosave("版本保存结果未知，请重新加载页面确认服务器当前草稿。");
    } finally {
      manualInFlight = false;
      if (!blocked) {
        setFieldsDisabled(false);
        manualSaveButton.disabled = false;
      }
    }
  }

  function requestManualSave() {
    if (blocked || manualPending || manualInFlight) {
      return;
    }
    manualPending = true;
    manualSaveButton.disabled = true;
    clearDebounce();
    if (inFlight) {
      setStatus("正在等待当前自动保存完成…", "saving");
      return;
    }
    startManualSave();
  }

  function markDirty() {
    if (blocked) {
      return;
    }
    dirty = true;
    setStatus("有未保存修改", "dirty");
    scheduleAutosave();
  }

  fields.forEach((field) => {
    field.addEventListener("input", markDirty);
    field.addEventListener("change", markDirty);
  });
  manualSaveButton.addEventListener("click", requestManualSave);
})();
