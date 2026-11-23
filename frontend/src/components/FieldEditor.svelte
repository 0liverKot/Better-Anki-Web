<script lang="ts" module>
  const AUDIO_EXTS = /\.(mp3|ogg|oga|wav|m4a|aac|flac|opus|webm|mp4|mov)$/i;

  // Elements the rich editor may render. Anything else (script, iframe, svg, style,
  // object, ...) means the field is edited as HTML source instead, so it can't run code
  // in this page and nothing in it gets lost.
  const RICH_TAGS = new Set(
    (
      'A ABBR B BDI BDO BIG BLOCKQUOTE BR CAPTION CENTER CITE CODE COL COLGROUP DATA DD DEL ' +
      'DFN DIV DL DT EM FIGCAPTION FIGURE FONT H1 H2 H3 H4 H5 H6 HR I IMG INS KBD LI MARK OL P ' +
      'PRE Q RP RT RUBY S SAMP SMALL SPAN STRIKE STRONG SUB SUP TABLE TBODY TD TFOOT TH THEAD ' +
      'TIME TR TT U UL VAR WBR ANKI-MATHJAX'
    ).split(' '),
  );
  const URL_ATTRS = new Set(['href', 'src', 'xlink:href', 'action', 'formaction', 'srcset', 'background', 'poster']);

  function parse(html: string): DocumentFragment {
    // <template> content is inert: no scripts run, no images load, no handlers fire.
    const template = document.createElement('template');
    template.innerHTML = html;
    return template.content;
  }

  /** True if the HTML can be shown in the rich (contenteditable) editor safely. */
  export function isRichSafe(html: string): boolean {
    for (const el of parse(html).querySelectorAll('*')) {
      if (!RICH_TAGS.has(el.tagName.toUpperCase())) return false;
      for (const attr of Array.from(el.attributes)) {
        const name = attr.name.toLowerCase();
        if (name.startsWith('on')) return false;
        if (URL_ATTRS.has(name) && /^(javascript|vbscript|data:text\/html)/i.test(attr.value.replace(/[\s\u0000-\u001f]/g, ''))) {
          return false;
        }
      }
    }
    return true;
  }

  function escapeAttr(value: string): string {
    return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  /** Stored HTML -> editor HTML: point media filenames at the server. */
  function toDisplay(html: string, mediaBase: string): string {
    const fragment = parse(html);
    fragment.querySelectorAll('img[src]').forEach((img) => {
      const src = img.getAttribute('src') ?? '';
      if (/^([a-z][a-z0-9+.-]*:|\/)/i.test(src)) return; // absolute URLs stay as they are
      img.setAttribute('data-src', src);
      img.setAttribute('src', mediaBase + encodeURIComponent(src));
    });
    const holder = document.createElement('div');
    holder.appendChild(fragment);
    return holder.innerHTML;
  }

  /** Editor HTML -> stored HTML: image srcs back to bare media filenames. */
  function toStorage(html: string): string {
    const fragment = parse(html);
    fragment.querySelectorAll('img[data-src]').forEach((img) => {
      img.setAttribute('src', img.getAttribute('data-src') ?? '');
      img.removeAttribute('data-src');
    });
    const holder = document.createElement('div');
    holder.appendChild(fragment);
    const out = holder.innerHTML.trim();
    // An emptied contenteditable often leaves a lone <br> behind.
    return /^(<br\s*\/?>|\s|&nbsp;)*$/i.test(out) ? '' : out;
  }

  export function plainText(html: string): string {
    return (parse(html).textContent ?? '').trim();
  }
</script>

<script lang="ts">
  import { toast } from '../lib/toast.svelte';

  interface Props {
    id: string;
    label: string;
    /** The field as Anki stores it (raw HTML). */
    value: string;
    mediaBase: string;
    sticky?: boolean;
    onfocus?: () => void;
    onupload: (file: File) => Promise<string>;
  }

  let { id, label, value = $bindable(''), mediaBase, sticky = false, onfocus, onupload }: Props = $props();

  let el: HTMLDivElement | undefined = $state();
  let textarea: HTMLTextAreaElement | undefined = $state();
  // Fields with content the rich editor can't show safely are locked to HTML source.
  const locked = $derived(!isRichSafe(value));
  let htmlMode = $state(false);
  const showHtml = $derived(htmlMode || locked);

  // Keep the contenteditable in sync with `value` without fighting the user's typing:
  // only re-render when the value changed from outside (reset, note type switch, HTML
  // mode) or the element was just created.
  let lastEmitted: string | null = null;
  let renderedEl: HTMLDivElement | null = null;
  $effect(() => {
    const current = value;
    if (!el || showHtml) return;
    if (current !== lastEmitted || el !== renderedEl) {
      el.innerHTML = toDisplay(current, mediaBase);
      lastEmitted = current;
      renderedEl = el;
    }
  });

  function emitFromRich(): void {
    if (!el) return;
    const stored = toStorage(el.innerHTML);
    lastEmitted = stored;
    value = stored;
  }

  export function focus(): void {
    if (showHtml) textarea?.focus();
    else el?.focus();
  }

  export function toggleHtml(): void {
    if (locked) {
      toast('This field has scripts or embedded content, so it can only be edited as HTML here.');
      return;
    }
    htmlMode = !htmlMode;
    queueMicrotask(focus);
  }

  /** Make sure the caret is inside the rich editor before inserting. */
  function ensureCaret(): void {
    if (!el) return;
    const selection = window.getSelection();
    if (document.activeElement !== el) el.focus();
    if (!selection || !selection.rangeCount || !el.contains(selection.anchorNode)) {
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  }

  function insertIntoTextarea(text: string, caretBack = 0): void {
    if (!textarea) return;
    textarea.focus();
    const { selectionStart: start, selectionEnd: end } = textarea;
    textarea.setRangeText(text, start, end, 'end');
    textarea.selectionStart = textarea.selectionEnd = start + text.length - caretBack;
    value = textarea.value;
  }

  /** Apply a formatting command (bold, italic, ...) in the rich editor. */
  export function format(command: string): void {
    if (showHtml) return;
    ensureCaret();
    document.execCommand(command);
    emitFromRich();
  }

  /** Wrap the selection, e.g. in "{{c1::" and "}}". With no selection, puts the caret between. */
  export function wrap(before: string, after: string): void {
    if (showHtml && textarea) {
      textarea.focus();
      const { selectionStart: start, selectionEnd: end } = textarea;
      const selected = textarea.value.slice(start, end);
      insertIntoTextarea(before + selected + after, selected ? 0 : after.length);
      return;
    }
    ensureCaret();
    const selection = window.getSelection();
    if (selection && selection.rangeCount && !selection.isCollapsed) {
      const holder = document.createElement('div');
      holder.appendChild(selection.getRangeAt(0).cloneContents());
      document.execCommand('insertHTML', false, before + holder.innerHTML + after);
    } else {
      document.execCommand('insertText', false, before + after);
      for (let i = 0; i < after.length; i++) selection?.modify('move', 'backward', 'character');
    }
    emitFromRich();
  }

  export async function insertFiles(files: File[]): Promise<void> {
    for (const file of files) {
      try {
        const name = await onupload(file);
        const isImage = file.type.startsWith('image/');
        const isSound = file.type.startsWith('audio/') || file.type.startsWith('video/') || AUDIO_EXTS.test(name);
        if (!isImage && !isSound) {
          toast(`Uploaded ${name}, but only images and audio can be inserted.`);
          continue;
        }
        if (showHtml) {
          insertIntoTextarea(isImage ? `<img src="${escapeAttr(name)}">` : `[sound:${name}]`);
          continue;
        }
        ensureCaret();
        if (isImage) {
          const src = mediaBase + encodeURIComponent(name);
          document.execCommand('insertHTML', false, `<img src="${escapeAttr(src)}" data-src="${escapeAttr(name)}">`);
        } else {
          document.execCommand('insertText', false, `[sound:${name}]`);
        }
        emitFromRich();
      } catch (err) {
        toast(err instanceof Error ? err.message : String(err), 'error');
      }
    }
  }

  function onpaste(event: ClipboardEvent): void {
    const data = event.clipboardData;
    if (!data) return;
    const files = Array.from(data.files);
    if (files.length) {
      event.preventDefault();
      insertFiles(files);
      return;
    }
    // Paste as plain text: formatting from web pages and documents rarely belongs on a card.
    event.preventDefault();
    document.execCommand('insertText', false, data.getData('text/plain'));
  }

  function ondrop(event: DragEvent): void {
    const files = Array.from(event.dataTransfer?.files ?? []);
    if (!files.length) return;
    event.preventDefault();
    insertFiles(files);
  }

  function onkeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'KeyX') {
      event.preventDefault();
      toggleHtml();
    }
  }
</script>

<div class="field-wrap">
  <div class="field-head">
    <label class="field-label" for={id}>
      {label}
      {#if sticky}<span class="pill" title="Kept after adding (sticky field)">kept</span>{/if}
    </label>
    <button
      type="button"
      class="html-toggle"
      class:active={showHtml}
      onmousedown={(e) => e.preventDefault()}
      onclick={toggleHtml}
      title={locked ? 'Contains scripts or embedded content, so it is shown as HTML' : 'Edit HTML (Ctrl+Shift+X)'}
      aria-pressed={showHtml}
    >
      &lt;/&gt;
    </button>
  </div>

  {#if showHtml}
    <textarea
      bind:this={textarea}
      {id}
      class="field html"
      bind:value
      rows={Math.min(12, Math.max(3, value.split('\n').length + 1))}
      spellcheck="false"
      autocapitalize="off"
      onfocus={() => onfocus?.()}
      {onkeydown}
    ></textarea>
    {#if locked}
      <p class="locked-note">Shown as HTML because it contains scripts or embedded content.</p>
    {/if}
  {:else}
    <div
      bind:this={el}
      {id}
      class="field"
      contenteditable="true"
      role="textbox"
      tabindex="0"
      aria-multiline="true"
      aria-label={label}
      spellcheck="true"
      oninput={emitFromRich}
      {onpaste}
      {ondrop}
      ondragover={(e) => e.preventDefault()}
      onfocus={() => onfocus?.()}
      {onkeydown}
    ></div>
  {/if}
</div>

<style>
  .field-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .field-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .pill {
    padding: 1px 6px;
    border-radius: 999px;
    background: var(--surface-3);
    font-size: 0.72rem;
    font-weight: 500;
  }
  .html-toggle {
    height: 24px;
    padding: 0 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: none;
    color: var(--faint);
    font: inherit;
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    cursor: pointer;
  }
  .html-toggle:hover {
    color: var(--muted);
    background: var(--surface-2);
  }
  .html-toggle.active {
    border-color: var(--accent-border);
    background: var(--accent-soft);
    color: var(--accent);
  }
  .field {
    min-height: 2.8em;
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    line-height: 1.5;
    overflow-wrap: anywhere;
    outline: none;
  }
  .field:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .field.html {
    width: 100%;
    resize: vertical;
    font: inherit;
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.875rem;
  }
  .field :global(img) {
    max-width: 100%;
    max-height: 240px;
    vertical-align: middle;
  }
  .locked-note {
    margin: 0;
    color: var(--muted);
    font-size: 0.8rem;
  }
</style>
