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
  const previewButton = editor.querySelector("#preview-draft-button");
  const submitReviewLink = editor.querySelector("#submit-review-link");
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
  const structuredContentElement = document.getElementById("structured-content");
  const changeSummary = editor.querySelector('[name="change_summary"]');
  const category = editor.querySelector('[name="category"]');
  const fields = [title, summary, scope, bodyText, changeSummary, category];
  let structuredContent = null;
  if (structuredContentElement) {
    try {
      const candidate = JSON.parse(structuredContentElement.textContent || "null");
      if (candidate && candidate.format === "opsai.richtext/1") {
        structuredContent = candidate;
        bodyText.readOnly = true;
        bodyText.setAttribute("aria-describedby", "richtext-editor-notice");
      }
    } catch (error) {
      structuredContent = null;
    }
  }
  let pageVersion = Number(editor.dataset.versionNo);
  const autosaveUrl = editor.dataset.autosaveUrl;
  const saveUrl = editor.dataset.saveUrl;
  const previewUrl = editor.dataset.previewUrl;
  const mediaUploadUrl = editor.dataset.mediaUploadUrl;
  const mediaImageMaxBytes = Number(editor.dataset.mediaImageMaxBytes) || (5 * 1024 * 1024);
  const mediaForm = editor.querySelector("#media-upload-form");
  const mediaStatus = editor.querySelector("#media-upload-status");
  const mediaList = editor.querySelector("#draft-media-list");

  if (
    !status ||
    !reloadLink ||
    !manualSaveButton ||
    !previewButton ||
    !submitReviewLink ||
    !versionLabel ||
    !lockLabel ||
    !csrfToken ||
    !draftId ||
    !lockVersion ||
    !autosaveUrl ||
    !saveUrl ||
    !previewUrl ||
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
  let previewPending = false;
  let submitPending = false;

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
    previewPending = false;
    submitPending = false;
    clearDebounce();
    manualSaveButton.disabled = true;
    previewButton.disabled = true;
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
    if (manualPending || manualInFlight || previewPending) {
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

    if (window.opsaiRichtextEditor) {
      structuredContent = window.opsaiRichtextEditor.getContent();
    }
    return {
      draft_id: draftId.value,
      expected_lock_version: expectedLockVersion,
      title: title.value,
      summary: summary.value,
      applicable_scope: parsedScope,
      body_text: bodyText.value,
      ...(structuredContent ? { structured_content: structuredContent } : {}),
      change_summary: changeSummary.value,
      category: category.value || null,
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
      if (previewPending) {
        previewPending = false;
        previewButton.disabled = false;
        manualSaveButton.disabled = false;
        setStatus(`${error.message} 请修正后再预览。`, "invalid");
      } else {
        setStatus(error.message, "invalid");
      }
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
            previewPending
              ? `${safeErrorMessage(payload, "当前内容无法自动保存，请检查输入。")} 请修正后再预览。`
              : safeErrorMessage(payload, "当前内容无法自动保存，请检查输入。"),
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
      } else if (previewPending) {
        continuePreviewAfterAutosave(autosaveSucceeded);
      } else if (submitPending) {
        continueSubmissionAfterAutosave(autosaveSucceeded);
      } else if (scheduleNext && dirty && !blocked) {
        scheduleAutosave();
      }
    }
  }

  function continuePreviewAfterAutosave(autosaveSucceeded) {
    if (!previewPending || blocked) {
      return;
    }
    if (!autosaveSucceeded) {
      previewPending = false;
      previewButton.disabled = false;
      manualSaveButton.disabled = false;
      return;
    }
    if (dirty) {
      attemptAutosave();
      return;
    }
    previewPending = false;
    window.location.assign(previewUrl);
  }

  function continueSubmissionAfterAutosave(autosaveSucceeded) {
    if (!submitPending || blocked) {
      return;
    }
    if (!autosaveSucceeded) {
      submitPending = false;
      return;
    }
    if (dirty) {
      attemptAutosave();
      return;
    }
    submitPending = false;
    window.location.assign(submitReviewLink.href);
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
      (payload.draft.proposed_category_id === null || typeof payload.draft.proposed_category_id === "string") &&
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
    structuredContent = payload.draft.structured_content?.format === "opsai.richtext/1"
      ? payload.draft.structured_content
      : null;
    changeSummary.value = payload.draft.change_summary;
    category.value = payload.draft.proposed_category_id || "";
    if (mediaForm) {
      const mediaDraftId = mediaForm.querySelector('[name="draft_id"]');
      if (mediaDraftId) {
        mediaDraftId.value = payload.draft.id;
      }
    }
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
    if (blocked || manualInFlight || previewPending || !manualPending) {
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
    previewButton.disabled = true;
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
        previewButton.disabled = false;
      }
    }
  }

  function requestManualSave() {
    if (blocked || manualPending || manualInFlight || previewPending) {
      return;
    }
    manualPending = true;
    manualSaveButton.disabled = true;
    previewButton.disabled = true;
    clearDebounce();
    if (inFlight) {
      setStatus("正在等待当前自动保存完成…", "saving");
      return;
    }
    startManualSave();
  }

  function requestPreview() {
    if (blocked || manualPending || manualInFlight || previewPending) {
      return;
    }
    clearDebounce();
    if (!dirty && !inFlight) {
      window.location.assign(previewUrl);
      return;
    }
    previewPending = true;
    previewButton.disabled = true;
    manualSaveButton.disabled = true;
    if (inFlight) {
      setStatus("正在等待当前自动保存完成…", "saving");
      return;
    }
    if (dirty) {
      attemptAutosave();
    }
  }

  function requestSubmission(event) {
    if (!dirty && !inFlight) {
      return;
    }
    event.preventDefault();
    if (blocked || submitPending || manualPending || manualInFlight || previewPending) {
      return;
    }
    submitPending = true;
    clearDebounce();
    if (inFlight) {
      setStatus("正在等待当前自动保存完成…", "saving");
      return;
    }
    attemptAutosave();
  }

  function markDirty() {
    if (blocked) {
      return;
    }
    dirty = true;
    setStatus("有未保存修改，将在停止输入 2 秒后自动保存", "dirty");
    scheduleAutosave();
  }

  function addMediaListItem(media) {
    if (!mediaList) {
      return;
    }
    mediaList.querySelector("[data-empty-media]")?.remove();
    const item = document.createElement("li");
    item.dataset.mediaId = media.id;
    const name = document.createElement("span");
    name.textContent = media.name;
    const description = document.createElement("span");
    description.textContent = `（${media.scan_message}${media.caption ? `：${media.caption}` : ""}）`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-media-button";
    remove.dataset.removeUrl = `${editor.dataset.mediaUploadUrl.replace("/upload/", `/${media.id}/remove/`)}`;
    remove.textContent = "移除";
    item.append(name, description, remove);
    if (media.kind === "image") {
      const insert = document.createElement("button");
      insert.type = "button";
      insert.className = "insert-media-button";
      insert.dataset.mediaId = media.id;
      insert.dataset.mediaCaption = media.caption || "";
      insert.textContent = "插入正文";
      item.append(insert);
    }
    mediaList.append(item);
  }

  async function removeUninsertedPastedMedia(media) {
    if (!media?.id || !mediaUploadUrl || !draftId?.value) return;
    const removeUrl = mediaUploadUrl.replace("/upload/", `/${media.id}/remove/`);
    const formData = new FormData();
    formData.set("draft_id", draftId.value);
    try {
      await fetch(removeUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken.value },
        body: formData,
      });
    } catch (_error) {
      // The page will show no successful insertion. A later refresh exposes any server-side failure.
    }
  }

  async function uploadPastedImage({ file, token }) {
    if (blocked || !mediaUploadUrl || !mediaStatus || !file) {
      window.opsaiRichtextEditor?.cancelPastedImage(token);
      return;
    }
    if (!["image/png", "image/jpeg"].includes(file.type.toLowerCase()) || file.size > mediaImageMaxBytes) {
      const maximumMb = Math.floor(mediaImageMaxBytes / (1024 * 1024));
      mediaStatus.textContent = `仅支持不超过 ${maximumMb} MB 的 PNG 或 JPEG 粘贴图片。`;
      window.opsaiRichtextEditor?.cancelPastedImage(token);
      return;
    }
    const formData = new FormData();
    formData.set("draft_id", draftId.value);
    formData.set("caption", "");
    formData.set("body_position", "0");
    formData.set("file", file, file.name || (file.type === "image/png" ? "clipboard.png" : "clipboard.jpg"));
    try {
      const response = await fetch(mediaUploadUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken.value },
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || payload.media?.kind !== "image") {
        mediaStatus.textContent = safeErrorMessage(payload, "粘贴图片上传或扫描失败，正文未改变。");
        window.opsaiRichtextEditor?.cancelPastedImage(token);
        return;
      }
      window.opsaiRichtextEditor?.registerMedia(payload.media.id, payload.media.content_url);
      if (!window.opsaiRichtextEditor?.insertPastedImage(token, payload.media.id, payload.media.caption)) {
        await removeUninsertedPastedMedia(payload.media);
        mediaStatus.textContent = "图片已扫描通过，但原光标位置已失效；正文未插入图片。";
        return;
      }
      addMediaListItem(payload.media);
      mediaStatus.textContent = "粘贴图片已扫描通过并插入正文。";
    } catch (error) {
      mediaStatus.textContent = "粘贴图片上传结果未知，正文未插入图片；请刷新后确认。";
      window.opsaiRichtextEditor?.cancelPastedImage(token);
    }
  }

  if (mediaForm && mediaStatus && mediaList && mediaUploadUrl) {
    mediaForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (blocked) {
        return;
      }
      mediaStatus.textContent = "正在上传并扫描…";
      const submitter = mediaForm.querySelector('button[type="submit"]');
      if (submitter) submitter.disabled = true;
      try {
        const response = await fetch(mediaUploadUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrfToken.value },
          body: new FormData(mediaForm),
        });
        const payload = await response.json();
        if (!response.ok || payload.ok !== true) {
          mediaStatus.textContent = safeErrorMessage(payload, "媒体上传失败，请检查文件后重试。");
          return;
        }
        addMediaListItem(payload.media);
        if (payload.media.kind === "image") {
          window.opsaiRichtextEditor?.registerMedia(payload.media.id, payload.media.content_url);
          window.opsaiRichtextEditor?.acceptUploadedImage(payload.media.id, payload.media.caption);
        }
        mediaStatus.textContent = payload.media.scan_message;
        mediaForm.reset();
        const mediaDraftId = mediaForm.querySelector('[name="draft_id"]');
        if (mediaDraftId) mediaDraftId.value = draftId.value;
      } catch (error) {
        mediaStatus.textContent = "媒体上传结果未知，请刷新页面确认。";
      } finally {
        if (submitter) submitter.disabled = false;
      }
    });

    mediaList.addEventListener("click", async (event) => {
      const insert = event.target.closest(".insert-media-button");
      if (insert) {
        window.opsaiRichtextEditor?.insertImage(insert.dataset.mediaId, insert.dataset.mediaCaption || "");
        markDirty();
        return;
      }
      const button = event.target.closest(".remove-media-button");
      if (!button || blocked || !button.dataset.removeUrl) return;
      button.disabled = true;
      const formData = new FormData();
      formData.set("draft_id", draftId.value);
      try {
        const response = await fetch(button.dataset.removeUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrfToken.value },
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok || payload.ok !== true) {
          mediaStatus.textContent = safeErrorMessage(payload, "媒体移除失败，请刷新页面确认。");
          button.disabled = false;
          return;
        }
        button.closest("li")?.remove();
        if (!mediaList.children.length) {
          const empty = document.createElement("li");
          empty.className = "muted";
          empty.dataset.emptyMedia = "";
          empty.textContent = "尚未添加媒体。";
          mediaList.append(empty);
        }
        mediaStatus.textContent = "媒体已从当前草稿移除；历史文件仍按保留策略保存。";
      } catch (error) {
        mediaStatus.textContent = "媒体移除结果未知，请刷新页面确认。";
        button.disabled = false;
      }
    });
  }

  fields.forEach((field) => {
    field.addEventListener("input", markDirty);
    field.addEventListener("change", markDirty);
  });
  document.addEventListener("opsai-richtext-change", markDirty);
  document.addEventListener("opsai-richtext-image-paste", (event) => {
    void uploadPastedImage(event.detail || {});
  });
  window.addEventListener("beforeunload", (event) => {
    if (!dirty && !inFlight && !manualInFlight) {
      return;
    }
    // Do not issue an unreliable write while the document is unloading.  The
    // browser confirmation gives the editor a chance to wait for the existing
    // debounced/CAS-protected request to finish instead.
    event.preventDefault();
    event.returnValue = "";
  });
  manualSaveButton.addEventListener("click", requestManualSave);
  previewButton.addEventListener("click", requestPreview);
  submitReviewLink.addEventListener("click", requestSubmission);
})();
