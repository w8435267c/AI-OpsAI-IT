import { Editor, Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import { TextStyle } from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
import Link from "@tiptap/extension-link";
import { Table } from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";

function createImageNode(mediaUrls) {
  return Node.create({
    name: "internalImage", group: "block", atom: true, selectable: true,
    addAttributes() { return { mediaLinkId: {}, caption: { default: "" }, width: { default: "full" } }; },
    renderHTML({ HTMLAttributes }) {
      const url = mediaUrls[HTMLAttributes.mediaLinkId];
      if (!url) return ["div", { class: "rich-media-missing" }, "受控图片不可读取"];
      return ["figure", mergeAttributes({ class: `article-image rich-image--${HTMLAttributes.width}` }, HTMLAttributes), ["img", { src: url, alt: HTMLAttributes.caption, loading: "lazy" }], ["figcaption", {}, HTMLAttributes.caption]];
    },
  });
}
const calloutNode = Node.create({
  name: "callout", group: "block", content: "block+",
  addAttributes() { return { kind: { default: "info" } }; },
  renderHTML({ HTMLAttributes }) { return ["aside", mergeAttributes({ class: `rich-callout rich-callout--${HTMLAttributes.kind}` }, HTMLAttributes), 0]; },
});

function marks(value = []) { return value.map((mark) => mark.type === "color" ? { type: "textStyle", attrs: { color: mark.color } } : mark.type === "link" ? { type: "link", attrs: { href: mark.href } } : { type: mark.type }); }
function inline(nodes) { return nodes.map((node) => node.type === "hardBreak" ? { type: "hardBreak" } : { type: "text", text: node.text, marks: marks(node.marks) }); }
function cellFromServer(cell) { return { type: cell.type === "tableHeader" ? "tableHeader" : "tableCell", attrs: { colspan: cell.colspan || 1, rowspan: cell.rowspan || 1 }, content: [{ type: "paragraph", content: inline(cell.content) }] }; }
function fromServer(node) {
  if (["heading", "paragraph"].includes(node.type)) return { type: node.type, ...(node.level ? { attrs: { level: node.level } } : {}), content: inline(node.content) };
  if (["orderedList", "bulletList"].includes(node.type)) return { type: node.type, content: node.items.map((item) => ({ type: "listItem", content: item.content.map(fromServer) })) };
  if (node.type === "blockquote" || node.type === "callout") return { type: node.type, ...(node.type === "callout" ? { attrs: { kind: node.kind } } : {}), content: node.content.map(fromServer) };
  if (node.type === "codeBlock") return { type: "codeBlock", attrs: { language: node.language || null }, content: node.text ? [{ type: "text", text: node.text }] : [] };
  if (node.type === "image") return { type: "internalImage", attrs: { mediaLinkId: node.media_link_id, caption: node.caption, width: node.width } };
  if (node.type === "table") return { type: "table", content: node.rows.map((row) => ({ type: "tableRow", content: row.cells.map(cellFromServer) })) };
  throw new Error("存在不支持的富文本节点，已阻止破坏性保存。");
}
function serverMarks(value = []) {
  const normalised = [];
  const seen = new Set();
  for (const mark of value) {
    let serverMark;
    // TextStyle is the Tiptap implementation extension behind Color.  A
    // TextStyle mark without a color has no OpsAI document meaning and must
    // not be serialised as an unsupported "textStyle" server-side mark.
    if (mark.type === "textStyle") {
      if (!mark.attrs?.color) continue;
      serverMark = { type: "color", color: mark.attrs.color };
    } else if (mark.type === "link") {
      serverMark = { type: "link", href: mark.attrs?.href };
    } else if (["bold", "italic", "underline"].includes(mark.type)) {
      serverMark = { type: mark.type };
    } else {
      throw new Error("存在不支持的富文本文字标记，已阻止保存。");
    }
    if (seen.has(serverMark.type)) {
      throw new Error("富文本存在重复文字标记，已阻止保存。");
    }
    seen.add(serverMark.type);
    normalised.push(serverMark);
  }
  return normalised;
}
function toInline(nodes = []) { return nodes.map((node) => node.type === "hardBreak" ? { type: "hardBreak" } : { type: "text", text: node.text || "", marks: serverMarks(node.marks) }); }
function cellToServer(cell) { const result = { type: cell.type === "tableHeader" ? "tableHeader" : "tableCell", content: toInline(cell.content?.[0]?.content || []) }; if (cell.attrs?.colspan > 1) result.colspan = cell.attrs.colspan; if (cell.attrs?.rowspan > 1) result.rowspan = cell.attrs.rowspan; return result; }
function toServer(node) {
  if (["heading", "paragraph"].includes(node.type)) return { type: node.type, ...(node.type === "heading" ? { level: node.attrs.level } : {}), content: toInline(node.content) };
  if (["orderedList", "bulletList"].includes(node.type)) return { type: node.type, items: (node.content || []).map((item) => ({ content: (item.content || []).map(toServer) })) };
  if (node.type === "blockquote" || node.type === "callout") return { type: node.type, ...(node.type === "callout" ? { kind: node.attrs.kind } : {}), content: (node.content || []).map(toServer) };
  if (node.type === "codeBlock") return { type: "codeBlock", language: node.attrs?.language || "", text: (node.content || []).map((part) => part.text || "").join("") };
  if (node.type === "internalImage") return { type: "image", media_link_id: node.attrs.mediaLinkId, caption: node.attrs.caption || "", width: node.attrs.width || "full" };
  if (node.type === "table") return { type: "table", rows: (node.content || []).map((row) => ({ cells: (row.content || []).map(cellToServer) })) };
  throw new Error("存在不支持的富文本节点，已阻止破坏性保存。");
}

window.addEventListener("DOMContentLoaded", () => {
  const host = document.getElementById("richtext-editor-host");
  const source = document.getElementById("structured-content");
  const mediaElement = document.getElementById("rich-media-urls");
  const status = document.getElementById("richtext-editor-notice");
  if (!host || !source || !mediaElement) return;
  const body = JSON.parse(source.textContent || "null");
  if (!body || body.format !== "opsai.richtext/1") return;
  const mediaUrls = JSON.parse(mediaElement.textContent || "{}");
  let selectedImagePos = null;
  let replaceRequested = false;
  let pendingPaste = null;
  let pasteSequence = 0;
  const editor = new Editor({
    element: host,
    extensions: [StarterKit.configure({ link: false, underline: false }), Underline, TextStyle, Color, Link.configure({ openOnClick: false, protocols: ["http", "https"] }), Table.configure({ resizable: true }), TableRow, TableHeader, TableCell, createImageNode(mediaUrls), calloutNode],
    content: { type: "doc", content: body.content.map(fromServer) },
    onUpdate: () => document.dispatchEvent(new Event("opsai-richtext-change")),
    onTransaction: ({ transaction }) => {
      if (pendingPaste) pendingPaste.position = transaction.mapping.map(pendingPaste.position, 1);
    },
    onSelectionUpdate: ({ editor: activeEditor }) => {
      const node = activeEditor.state.selection.node;
      selectedImagePos = node?.type.name === "internalImage" ? activeEditor.state.selection.from : null;
      if (status) status.textContent = selectedImagePos === null ? "选择图片后可替换、删除、移动、修改说明或宽度。" : "已选中正文图片，可使用图片操作按钮。";
    },
    editorProps: {
      handlePaste: (_view, event) => {
        const clipboard = event.clipboardData;
        const imageItem = Array.from(clipboard?.items || []).find((item) =>
          ["image/png", "image/jpeg"].includes(item.type.toLowerCase()),
        );
        if (!imageItem) {
          if ((clipboard?.getData("text/html") || "").match(/<img\b/i) && status) {
            status.textContent = "剪贴板未提供可上传的 PNG/JPEG 图片数据；请使用图片上传。";
          }
          return false;
        }
        const file = imageItem.getAsFile();
        if (!file || file.size <= 0) {
          if (status) status.textContent = "剪贴板图片数据不可读取；请使用图片上传。";
          return false;
        }
        if (file.size > 5 * 1024 * 1024) {
          if (status) status.textContent = "剪贴板图片超过 5 MB 限制，未上传。";
          return false;
        }
        if (pendingPaste) {
          if (status) status.textContent = "上一张粘贴图片仍在扫描，请等待完成后再粘贴。";
          return false;
        }
        const token = window.crypto?.randomUUID?.() || `clipboard-${Date.now()}-${++pasteSequence}`;
        pendingPaste = { token, position: editor.state.selection.from };
        document.dispatchEvent(new CustomEvent("opsai-richtext-image-paste", { detail: { file, token } }));
        if (status) status.textContent = "正在上传并扫描粘贴图片…";
        event.preventDefault();
        return true;
      },
    },
  });
  function selectedImage() { return selectedImagePos === null ? null : editor.state.doc.nodeAt(selectedImagePos); }
  function requireImage() { if (!selectedImage()) { if (status) status.textContent = "请先单击正文中的图片。"; return false; } return true; }
  function updateSelectedImage(attrs) { if (!requireImage()) return false; const node = selectedImage(); return editor.chain().focus().command(({ tr }) => { tr.setNodeMarkup(selectedImagePos, undefined, { ...node.attrs, ...attrs }); return true; }).run(); }
  function deleteSelectedImage() { if (!requireImage()) return false; const node = selectedImage(); return editor.chain().focus().command(({ tr }) => { tr.delete(selectedImagePos, selectedImagePos + node.nodeSize); return true; }).run(); }
  function moveSelectedImage(direction) { if (!requireImage()) return false; const node = selectedImage(); const doc = editor.state.doc; const before = direction < 0 ? doc.resolve(selectedImagePos).before(1) : selectedImagePos + node.nodeSize; const target = direction < 0 ? Math.max(0, before - 1) : Math.min(doc.content.size, before + 1); if (target === selectedImagePos) return false; return editor.chain().focus().command(({ tr }) => { tr.delete(selectedImagePos, selectedImagePos + node.nodeSize); tr.insert(target > selectedImagePos ? target - node.nodeSize : target, node); return true; }).run(); }
  const commands = {
    undo: () => editor.chain().focus().undo().run(), redo: () => editor.chain().focus().redo().run(), heading: () => editor.chain().focus().toggleHeading({ level: 2 }).run(), bold: () => editor.chain().focus().toggleBold().run(), italic: () => editor.chain().focus().toggleItalic().run(), underline: () => editor.chain().focus().toggleUnderline().run(), color: () => editor.chain().focus().setColor("blue").run(), bulletList: () => editor.chain().focus().toggleBulletList().run(), orderedList: () => editor.chain().focus().toggleOrderedList().run(), blockquote: () => editor.chain().focus().toggleBlockquote().run(), codeBlock: () => editor.chain().focus().toggleCodeBlock().run(), table: () => editor.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run(), callout: () => editor.chain().focus().insertContent({ type: "callout", attrs: { kind: "info" }, content: [{ type: "paragraph", content: [{ type: "text", text: "提示内容" }] }] }).run(),
    addRowBefore: () => editor.chain().focus().addRowBefore().run(), addRowAfter: () => editor.chain().focus().addRowAfter().run(), deleteRow: () => editor.chain().focus().deleteRow().run(), addColumnBefore: () => editor.chain().focus().addColumnBefore().run(), addColumnAfter: () => editor.chain().focus().addColumnAfter().run(), deleteColumn: () => editor.chain().focus().deleteColumn().run(), toggleHeaderRow: () => editor.chain().focus().toggleHeaderRow().run(), mergeCells: () => editor.chain().focus().mergeCells().run(), splitCell: () => editor.chain().focus().splitCell().run(),
    replaceImage: () => { if (requireImage()) { replaceRequested = true; document.getElementById("media-file")?.click(); } }, deleteImage: deleteSelectedImage, moveImageUp: () => moveSelectedImage(-1), moveImageDown: () => moveSelectedImage(1), imageCaption: () => { if (!requireImage()) return; const value = window.prompt("图片说明", selectedImage().attrs.caption || ""); if (value !== null) updateSelectedImage({ caption: value }); }, imageWidth: () => { if (!requireImage()) return; const value = window.prompt("图片宽度（full / wide / half）", selectedImage().attrs.width || "full"); if (["full", "wide", "half"].includes(value)) updateSelectedImage({ width: value }); else if (status) status.textContent = "图片宽度仅支持 full、wide 或 half。"; },
  };
  document.querySelectorAll("[data-rich-command]").forEach((button) => button.addEventListener("click", () => commands[button.dataset.richCommand]?.()));
  window.opsaiRichtextEditor = {
    getContent: () => ({ format: "opsai.richtext/1", schema_version: 1, content: editor.getJSON().content.map(toServer) }),
    insertImage: (mediaLinkId, caption = "") => editor.chain().focus().insertContent({ type: "internalImage", attrs: { mediaLinkId, caption, width: "full" } }).run(),
    registerMedia: (mediaLinkId, url) => { mediaUrls[mediaLinkId] = url; },
    insertPastedImage: (token, mediaLinkId, caption = "") => {
      if (!pendingPaste || pendingPaste.token !== token) return false;
      const position = Math.min(pendingPaste.position, editor.state.doc.content.size);
      pendingPaste = null;
      return editor.chain().focus().insertContentAt(position, {
        type: "internalImage",
        attrs: { mediaLinkId, caption, width: "full" },
      }).run();
    },
    cancelPastedImage: (token) => {
      if (pendingPaste?.token === token) pendingPaste = null;
    },
    acceptUploadedImage: (mediaLinkId, caption = "") => { if (replaceRequested && requireImage()) { replaceRequested = false; return updateSelectedImage({ mediaLinkId, caption }); } replaceRequested = false; return editor.chain().focus().insertContent({ type: "internalImage", attrs: { mediaLinkId, caption, width: "full" } }).run(); },
    destroy: () => editor.destroy(),
  };
});
