"""Runtime contracts for the browser-side rich-text autosave state machine."""

# ruff: noqa: E501, UP031

import json
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class KnowledgeEditorRuntimeTests(SimpleTestCase):
    """Execute the shipped browser script with a small DOM/fetch harness.

    This deliberately exercises the production JavaScript event, timer, request
    body, response handling, and unload guard rather than merely searching its
    source text.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.node = shutil.which("node")
        cls.script_path = Path(settings.BASE_DIR) / "static" / "js" / "knowledge_editor.js"
        cls.richtext_source_path = (
            Path(settings.BASE_DIR) / "static" / "js" / "richtext_editor_source.js"
        )

    def test_shipped_tiptap_converter_keeps_empty_structural_nodes(self):
        """Execute the production Tiptap serializer against ProseMirror-shaped JSON."""

        if self.node is None:
            self.skipTest("Node.js is required for the browser runtime contract test.")

        program = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(%(source_path)s, 'utf8');
const converters = source.slice(source.indexOf('function marks'), source.indexOf('\nwindow.addEventListener'));
const context = { globalThis: {} };
vm.runInNewContext(`${converters}\nglobalThis.toServerForTest = toServer;`, context);
const result = [
  {
    type: 'paragraph',
    content: [{ type: 'text', text: 'production converter marker', marks: [] }],
  },
  { type: 'paragraph', content: [] },
  {
    type: 'table',
    content: [{
      type: 'tableRow',
      content: [
        { type: 'tableHeader', attrs: { colspan: 1, rowspan: 1 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: 'head', marks: [] }] }] },
        { type: 'tableHeader', attrs: { colspan: 1, rowspan: 1 }, content: [{ type: 'paragraph', content: [] }] },
      ],
    }],
  },
].map(context.globalThis.toServerForTest);
process.stdout.write(JSON.stringify(result));
""" % {"source_path": json.dumps(str(self.richtext_source_path))}

        result = subprocess.run(
            [self.node, "-e", program],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        converted = json.loads(result.stdout)

        self.assertEqual(converted[0]["content"][0]["text"], "production converter marker")
        self.assertEqual(converted[1]["content"], [])
        self.assertEqual(converted[2]["rows"][0]["cells"][1]["content"], [])

    def test_shipped_tiptap_converter_normalises_text_style_marks(self):
        """The browser serializer must emit only the server mark protocol."""

        if self.node is None:
            self.skipTest("Node.js is required for the browser runtime contract test.")

        program = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(%(source_path)s, 'utf8');
const converters = source.slice(source.indexOf('function marks'), source.indexOf('\nwindow.addEventListener'));
const context = { globalThis: {}, Set };
vm.runInNewContext(`${converters}\nglobalThis.toServerForTest = toServer;`, context);
function convert(marks) {
  return context.globalThis.toServerForTest({
    type: 'paragraph', content: [{ type: 'text', text: 'mark contract', marks }],
  });
}
function failure(marks) {
  try { convert(marks); } catch (error) { return error.message; }
  return null;
}
process.stdout.write(JSON.stringify({
  inert: convert([{ type: 'textStyle', attrs: {} }]),
  valid: convert([{ type: 'bold' }, { type: 'textStyle', attrs: { color: 'blue' } }]),
  unsupported: failure([{ type: 'strike' }]),
  duplicate: failure([{ type: 'bold' }, { type: 'bold' }]),
}));
""" % {"source_path": json.dumps(str(self.richtext_source_path))}

        result = subprocess.run(
            [self.node, "-e", program],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        observed = json.loads(result.stdout)

        self.assertEqual(observed["inert"]["content"][0]["marks"], [])
        self.assertEqual(
            observed["valid"]["content"][0]["marks"],
            [{"type": "bold"}, {"type": "color", "color": "blue"}],
        )
        self.assertEqual(observed["unsupported"], "存在不支持的富文本文字标记，已阻止保存。")
        self.assertEqual(observed["duplicate"], "富文本存在重复文字标记，已阻止保存。")

    def test_richtext_change_posts_latest_snapshot_and_clears_unload_guard_on_success(self):
        if self.node is None:
            self.skipTest("Node.js is required for the browser runtime contract test.")

        program = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(%(source_path)s, 'utf8');

function Target() { this.listeners = new Map(); }
Target.prototype.addEventListener = function (name, callback) {
  const callbacks = this.listeners.get(name) || [];
  callbacks.push(callback);
  this.listeners.set(name, callbacks);
};
Target.prototype.dispatchEvent = function (event) {
  for (const callback of this.listeners.get(event.type) || []) callback(event);
  return true;
};
function Element(value = '') {
  Target.call(this);
  this.value = value;
  this.dataset = {};
  this.hidden = false;
  this.disabled = false;
  this.readOnly = false;
  this.textContent = '';
  this.attributes = {};
}
Element.prototype = Object.create(Target.prototype);
Element.prototype.constructor = Element;
Element.prototype.setAttribute = function (name, value) { this.attributes[name] = value; };
Element.prototype.querySelector = function () { return null; };
Element.prototype.querySelectorAll = function () { return []; };

const timers = [];
const requests = [];
const editor = new Element();
editor.dataset = {
  versionNo: '2', autosaveUrl: '/autosave/', saveUrl: '/save/', previewUrl: '/preview/',
  mediaUploadUrl: '/media/upload/', mediaImageMaxBytes: '5242880',
};
const status = new Element();
const reload = new Element();
const manual = new Element();
const preview = new Element();
const submit = new Element();
const version = new Element();
const lockLabel = new Element();
const csrf = new Element('csrf-token');
const draft = new Element('draft-uuid');
const lock = new Element('1');
const title = new Element('title');
const summary = new Element('summary');
const scope = new Element('{}');
const bodyText = new Element('derived text');
const change = new Element('change');
const category = new Element('');
const fields = {
  '#autosave-status': status, '#autosave-reload': reload, '#manual-save-button': manual,
  '#preview-draft-button': preview, '#submit-review-link': submit,
  '[name="csrfmiddlewaretoken"]': csrf, '[name="draft_id"]': draft,
  '[name="expected_lock_version"]': lock, '[name="title"]': title,
  '[name="summary"]': summary, '[name="applicable_scope"]': scope,
  '[name="body_text"]': bodyText, '[name="change_summary"]': change,
  '[name="category"]': category,
};
editor.querySelector = (selector) => fields[selector] || null;
const document = new Target();
document.querySelector = (selector) => {
  if (selector === '#knowledge-editor') return editor;
  if (selector === '#working-version-label') return version;
  if (selector === '#working-lock-label') return lockLabel;
  return null;
};
document.getElementById = (id) => id === 'structured-content'
  ? { textContent: JSON.stringify({ format: 'opsai.richtext/1', schema_version: 1, content: [] }) }
  : null;
document.querySelectorAll = () => [];
const window = new Target();
window.setTimeout = (callback) => { timers.push(callback); return timers.length; };
window.clearTimeout = () => {};
window.location = { assign: () => {} };
window.opsaiRichtextEditor = {
  getContent: () => ({
    format: 'opsai.richtext/1', schema_version: 1,
    content: [{ type: 'paragraph', content: [{ type: 'text', text: 'runtime autosave marker' }] }],
  }),
};
const context = {
  document, window, Event: class { constructor(type) { this.type = type; } }, JSON, Number, Array, Object,
  fetch: async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true, status: 200, headers: { get: () => 'application/json' },
      json: async () => ({ ok: true, draft: { id: 'draft-uuid', version_no: 2, lock_version: 2 } }),
    };
  },
};
vm.runInNewContext(source, context);
document.dispatchEvent(new context.Event('opsai-richtext-change'));
Promise.resolve(timers[0]()).then(async () => {
  await Promise.resolve();
  await Promise.resolve();
  const unload = { type: 'beforeunload', prevented: false, preventDefault() { this.prevented = true; } };
  window.dispatchEvent(unload);
  process.stdout.write(JSON.stringify({
    requests: requests.length, status: status.textContent, lock: lock.value, unloadPrevented: unload.prevented,
    payload: JSON.parse(requests[0].options.body),
  }));
});
""" % {"source_path": json.dumps(str(self.script_path))}

        result = subprocess.run(
            [self.node, "-e", program],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        observed = json.loads(result.stdout)

        self.assertEqual(observed["requests"], 1)
        self.assertEqual(observed["status"], "已自动保存")
        self.assertEqual(observed["lock"], "2")
        self.assertFalse(observed["unloadPrevented"])
        self.assertEqual(observed["payload"]["expected_lock_version"], 1)
        self.assertEqual(
            observed["payload"]["structured_content"]["content"][0]["content"][0]["text"],
            "runtime autosave marker",
        )
