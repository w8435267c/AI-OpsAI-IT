(function () {
  "use strict";

  const DEBOUNCE_MS = 2000;
  const editor = document.querySelector("#knowledge-editor");
  if (!editor) {
    return;
  }

  const status = editor.querySelector("#autosave-status");
  const reloadLink = editor.querySelector("#autosave-reload");
  const csrfToken = editor.querySelector('[name="csrfmiddlewaretoken"]');
  const draftId = editor.querySelector('[name="draft_id"]');
  const lockVersion = editor.querySelector('[name="expected_lock_version"]');
  const title = editor.querySelector('[name="title"]');
  const summary = editor.querySelector('[name="summary"]');
  const scope = editor.querySelector('[name="applicable_scope"]');
  const bodyText = editor.querySelector('[name="body_text"]');
  const changeSummary = editor.querySelector('[name="change_summary"]');
  const fields = [title, summary, scope, bodyText, changeSummary];
  const pageVersion = Number(editor.dataset.versionNo);
  const autosaveUrl = editor.dataset.autosaveUrl;

  if (
    !status ||
    !reloadLink ||
    !csrfToken ||
    !draftId ||
    !lockVersion ||
    !autosaveUrl ||
    !Number.isInteger(pageVersion) ||
    fields.some((field) => !field)
  ) {
    return;
  }

  let debounceTimer = null;
  let inFlight = false;
  let dirty = false;
  let blocked = false;

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
    clearDebounce();
    reloadLink.hidden = false;
    setStatus(message, "blocked");
  }

  function scheduleAutosave() {
    clearDebounce();
    if (blocked || inFlight || !dirty) {
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
      if (scheduleNext && dirty && !blocked) {
        scheduleAutosave();
      }
    }
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
})();
