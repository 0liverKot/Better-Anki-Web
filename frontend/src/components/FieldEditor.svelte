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

  // MathJax, as Anki stores it: \(inline\) and \[block\]. In the editor each one becomes
  // an uneditable box showing the rendered formula (like Anki's <anki-mathjax>).
  const MATH_RE = /\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)/g;
  const MATH_CLASS = 'baw-mathjax';

  /** The TeX inside \(...\) as stored in the field (HTML-encoded, maybe with <br>s). */
  function rawToTex(raw: string): string {
    return parse(raw.replace(/<br\s*\/?>/gi, '\n')).textContent ?? '';
  }

  function escapeText(value: string): string {
    return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function mathSpanHtml(tex: string, block: boolean, raw?: string): string {
    const rawAttr = raw === undefined ? '' : ` data-raw="${escapeAttr(raw)}"`;
    return (
      `<span class="${MATH_CLASS}" contenteditable="false" data-block="${block}" ` +
      `data-tex="${escapeAttr(tex)}"${rawAttr}></span>`
    );
  }

  /** Stored HTML -> editor HTML: MathJax into boxes, media filenames to server URLs. */
  function toDisplay(html: string, mediaBase: string): string {
    html = html.replace(MATH_RE, (_m, blockRaw?: string, inlineRaw?: string) => {
      const raw = blockRaw ?? inlineRaw ?? '';
      return mathSpanHtml(rawToTex(raw), blockRaw !== undefined, raw);
    });
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

  /** Editor HTML -> stored HTML: maths boxes back to \(...\), media back to filenames. */
  function toStorage(html: string): string {
    const fragment = parse(html);
    fragment.querySelectorAll(`.${MATH_CLASS}`).forEach((span) => {
      const tex = span.getAttribute('data-tex') ?? '';
      const raw = span.getAttribute('data-raw');
      const [open, close] = span.getAttribute('data-block') === 'true' ? ['\\[', '\\]'] : ['\\(', '\\)'];
      // Unchanged formulas keep their exact original HTML.
      const inner = raw !== null && rawToTex(raw) === tex ? raw : escapeText(tex);
      span.replaceWith(parse(open + inner + close));
    });
    fragment.querySelectorAll('img[data-src]').forEach((img) => {
      img.setAttribute('src', img.getAttribute('data-src') ?? '');
      img.removeAttribute('data-src');
    });
    const holder = document.createElement('div');
    holder.appendChild(fragment);
    const out = holder.innerHTML
      .trim()
      // Drop the caret line the editor adds after a block formula at the end of a field.
      .replace(/(\\\])<br\s*\/?>$/i, '$1')
      // Chrome types spaces next to the formula boxes as &nbsp;; store plain spaces.
      .replace(/&nbsp;(?=\\[([])/g, ' ')
      .replace(/(\\[)\]])&nbsp;/g, '$1 ');
    // An emptied contenteditable often leaves a lone <br> behind.
    return /^(<br\s*\/?>|\s|&nbsp;)*$/i.test(out) ? '' : out;
  }

  export function plainText(html: string): string {
    return (parse(html).textContent ?? '').trim();
  }

  /** True if the editor shows \( or \[ as plain text that should become a maths box. */
  function hasUndecoratedMath(el: HTMLElement): boolean {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let text = '';
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!(node.parentElement?.closest(`.${MATH_CLASS}`))) text += node.textContent;
    }
    return /\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/.test(text);
  }
</script>

<script lang="ts">
  import { tick } from 'svelte';
  import { renderTex } from '../lib/mathjax';
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
      mathEdit = null;
      el.innerHTML = toDisplay(current, mediaBase);
      lastEmitted = current;
      renderedEl = el;
      renderAllMath();
    }
  });

  // MathJax boxes
  //
  // Each \(...\) / \[...\] shows as a box with the rendered formula. Clicking one opens
  // a small editor under it for the TeX source, with a live preview, like Anki.

  let wrapEl: HTMLDivElement | undefined = $state();
  let mathInput: HTMLTextAreaElement | undefined = $state();
  let mathEdit = $state<{ span: HTMLElement; tex: string; block: boolean; top: number; left: number } | null>(null);
  let renderTimer: ReturnType<typeof setTimeout> | undefined;

  async function renderMath(span: HTMLElement): Promise<void> {
    const tex = span.dataset.tex ?? '';
    const block = span.dataset.block === 'true';
    span.classList.toggle('empty', !tex.trim());
    span.title = tex ? `${tex}\n(click to edit)` : 'Empty formula (click to edit)';
    if (!tex.trim()) {
      span.replaceChildren();
      return;
    }
    const token = String(Math.random());
    span.dataset.renderToken = token;
    try {
      const color = el ? getComputedStyle(el).color : 'black';
      const out = await renderTex(tex, block, color);
      if (span.dataset.renderToken !== token || !out) return;
      // Update the existing image rather than replacing it: Chrome drops the caret when
      // a node right next to it is removed.
      let img = span.firstElementChild instanceof HTMLImageElement ? span.firstElementChild : null;
      if (!img || span.childNodes.length !== 1) {
        img = document.createElement('img');
        img.draggable = false;
        span.replaceChildren(img);
      }
      img.src = out.src;
      img.alt = tex;
      img.style.width = out.width;
      img.style.height = out.height;
      img.style.verticalAlign = out.verticalAlign;
    } catch {
      // MathJax couldn't load (offline?): show the source instead.
      if (span.dataset.renderToken === token) span.textContent = block ? `\\[${tex}\\]` : `\\(${tex}\\)`;
    }
    if (mathEdit?.span === span) positionMathEditor();
  }

  function renderAllMath(): void {
    el?.querySelectorAll<HTMLElement>(`.${MATH_CLASS}`).forEach(renderMath);
  }

  function positionMathEditor(): void {
    if (!mathEdit || !wrapEl) return;
    const box = mathEdit.span.getBoundingClientRect();
    const wrap = wrapEl.getBoundingClientRect();
    const width = Math.min(440, wrap.width);
    mathEdit.top = box.bottom - wrap.top + 6;
    mathEdit.left = Math.max(0, Math.min(box.left - wrap.left, wrap.width - width));
  }

  async function openMathEditor(span: HTMLElement, caret?: number): Promise<void> {
    if (mathEdit && mathEdit.span !== span) closeMathEditor(false);
    span.classList.add('editing');
    mathEdit = { span, tex: span.dataset.tex ?? '', block: span.dataset.block === 'true', top: 0, left: 0 };
    positionMathEditor();
    await tick();
    mathInput?.focus();
    const at = caret ?? mathEdit.tex.length;
    mathInput?.setSelectionRange(at, at);
  }

  /** Close the formula editor; an empty formula is removed. */
  function closeMathEditor(refocus = true): void {
    if (!mathEdit) return;
    const { span } = mathEdit;
    mathEdit = null;
    span.classList.remove('editing');
    // Finish any pending preview render now, so the next formula can't cancel it.
    clearTimeout(renderTimer);
    if ((span.dataset.tex ?? '').trim()) renderMath(span);
    // The caret goes just after the formula. Ranges are live, so if an empty formula is
    // removed this one still points at where it was.
    const range = document.createRange();
    range.setStartAfter(span);
    range.collapse(true);
    if (!(span.dataset.tex ?? '').trim()) {
      span.remove();
    } else if (span.dataset.block === 'true') {
      // A block formula with nothing after it leaves no line for the caret, and Chrome
      // drops the caret on the next layout. Give it an empty line (dropped on save).
      const next = span.nextSibling;
      if (!next || (next.nodeType === Node.TEXT_NODE && !next.textContent)) span.after(document.createElement('br'));
    }
    emitFromRich();
    if (!refocus || !el) return;
    const field = el;
    const placeCaret = () => {
      if (document.activeElement !== field) field.focus();
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    };
    placeCaret();
    // Removing the popover (which had focus) can clear the selection once Svelte updates
    // the page, so place the caret again afterwards.
    tick().then(() => {
      if (document.activeElement === field && !window.getSelection()?.rangeCount) placeCaret();
    });
  }

  function updateMath(changes: { tex?: string; block?: boolean }): void {
    if (!mathEdit) return;
    const { span } = mathEdit;
    if (changes.tex !== undefined) {
      span.dataset.tex = changes.tex;
      mathEdit.tex = changes.tex;
    }
    if (changes.block !== undefined) {
      span.dataset.block = String(changes.block);
      mathEdit.block = changes.block;
    }
    emitFromRich();
    clearTimeout(renderTimer);
    renderTimer = setTimeout(() => renderMath(span), changes.block !== undefined ? 0 : 150);
  }

  function deleteMath(): void {
    if (!mathEdit) return;
    mathEdit.span.dataset.tex = '';
    closeMathEditor();
  }

  function onMathKeydown(event: KeyboardEvent): void {
    // Enter or Esc closes the formula editor (Shift+Enter adds a line), and shouldn't
    // reach the note editor (where Esc would cancel the whole edit).
    if ((event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.metaKey) || event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMathEditor();
    }
  }

  function onMathFocusOut(event: FocusEvent): void {
    const next = event.relatedTarget as Node | null;
    if (next && (event.currentTarget as HTMLElement).contains(next)) return;
    closeMathEditor(false);
  }

  /** Insert a new formula at the caret (the selection becomes its TeX) and open it for editing. */
  export function insertMath(block: boolean, prefix = '', suffix = ''): void {
    if (showHtml) {
      const [open, close] = block ? ['\\[', '\\]'] : ['\\(', '\\)'];
      wrap(open + prefix, suffix + close);
      return;
    }
    if (!el) return;
    ensureCaret();
    const selection = window.getSelection();
    if (!selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    const selected = range.toString();
    const tex = prefix + selected + suffix;
    const span = parse(mathSpanHtml(tex, block)).firstElementChild as HTMLElement;
    range.deleteContents();
    range.insertNode(span);
    renderMath(span);
    emitFromRich();
    openMathEditor(span, prefix.length + selected.length);
  }

  function mathSpanAt(target: EventTarget | null): HTMLElement | null {
    const span = (target as HTMLElement | null)?.closest?.(`.${MATH_CLASS}`) as HTMLElement | null;
    return span && el?.contains(span) ? span : null;
  }

  function onRichMousedown(event: MouseEvent): void {
    // Keep the caret from landing inside the formula box.
    if (mathSpanAt(event.target)) event.preventDefault();
  }

  function onRichClick(event: MouseEvent): void {
    const span = mathSpanAt(event.target);
    if (span) openMathEditor(span);
  }

  function onRichBlur(): void {
    // Formulas typed or pasted as plain text become boxes once you leave the field.
    if (!el || mathEdit || !hasUndecoratedMath(el)) return;
    emitFromRich();
    el.innerHTML = toDisplay(value, mediaBase);
    renderAllMath();
  }

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

  // Chrome moves the caret to the start of the line after these; we put it back.
  const KEEP_CARET = new Set(['insertUnorderedList', 'insertOrderedList', 'indent', 'outdent']);

  /** Caret position as a count of characters from the start of the field. */
  function textOffset(node: Node, offset: number): number {
    const range = document.createRange();
    range.setStart(el!, 0);
    range.setEnd(node, offset);
    return range.toString().length;
  }

  /** The text node and offset at a character position (inverse of textOffset). */
  function textPosition(chars: number): [Text, number] | null {
    const walker = document.createTreeWalker(el!, NodeFilter.SHOW_TEXT);
    let last: Text | null = null;
    for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
      if (chars <= node.length) return [node, chars];
      chars -= node.length;
      last = node;
    }
    return last ? [last, last.length] : null;
  }

  function runCommand(command: string): void {
    const selection = window.getSelection();
    const { anchorNode, focusNode } = selection ?? {};
    // Only when the caret is in text: on an empty line there's no text position to
    // return to, and Chrome already puts the caret in the new list item.
    const saved =
      el && selection && anchorNode instanceof Text && focusNode instanceof Text && el.contains(anchorNode)
        ? [textOffset(anchorNode, selection.anchorOffset), textOffset(focusNode, selection.focusOffset)]
        : null;
    document.execCommand(command);
    // (Only for list commands: resetting the selection after e.g. Bold would cancel
    // the bold "typing mode" for the next characters.)
    if (saved && KEEP_CARET.has(command)) {
      const anchor = textPosition(saved[0]);
      const focusPos = textPosition(saved[1]);
      if (anchor && focusPos) selection!.setBaseAndExtent(anchor[0], anchor[1], focusPos[0], focusPos[1]);
    }
  }

  /** Apply a formatting command (bold, italic, lists, ...) in the rich editor. */
  export function format(command: string): void {
    if (showHtml) return;
    ensureCaret();
    runCommand(command);
    emitFromRich();
  }

  /** Indent or outdent the current list item. Like Anki, this only works inside lists. */
  export function indent(outdent: boolean): void {
    if (showHtml || !el) return;
    ensureCaret();
    const node = window.getSelection()?.anchorNode ?? null;
    const element = node instanceof Element ? node : (node?.parentElement ?? null);
    if (!element || !el.contains(element) || !element.closest('li')) {
      toast('Indenting only works inside lists.');
      return;
    }
    runCommand(outdent ? 'outdent' : 'indent');
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

<div class="field-wrap" bind:this={wrapEl}>
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
      onblur={onRichBlur}
      onmousedown={onRichMousedown}
      onclick={onRichClick}
      {onkeydown}
    ></div>
    {#if mathEdit}
      <div
        class="math-editor"
        style="top: {mathEdit.top}px; left: {mathEdit.left}px"
        role="dialog"
        aria-label="Edit formula"
        onfocusout={onMathFocusOut}
      >
        <textarea
          bind:this={mathInput}
          class="math-source"
          value={mathEdit.tex}
          oninput={(e) => updateMath({ tex: e.currentTarget.value })}
          onkeydown={onMathKeydown}
          rows={Math.min(6, Math.max(2, mathEdit.tex.split('\n').length))}
          spellcheck="false"
          autocapitalize="off"
          placeholder={'TeX, e.g. x^2 or \\frac{a}{b}'}
          aria-label="Formula (TeX)"
        ></textarea>
        <div class="math-actions">
          <div class="segmented" role="group" aria-label="Display">
            <button type="button" class:active={!mathEdit.block} onclick={() => updateMath({ block: false })}>Inline</button>
            <button type="button" class:active={mathEdit.block} onclick={() => updateMath({ block: true })}>Block</button>
          </div>
          <span class="math-hint">Enter to finish</span>
          <button type="button" class="math-btn" onclick={deleteMath}>Delete</button>
          <button type="button" class="math-btn primary" onclick={() => closeMathEditor()}>Done</button>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .field-wrap {
    position: relative;
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
  /* MathJax boxes in the rich editor */
  .field :global(.baw-mathjax) {
    display: inline-block;
    margin: 0 1px;
    padding: 1px 4px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--surface-2);
    line-height: 1;
    vertical-align: middle;
    cursor: pointer;
    user-select: none;
  }
  .field :global(.baw-mathjax:hover) {
    border-color: var(--accent-border);
    background: var(--accent-soft);
  }
  .field :global(.baw-mathjax.editing) {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-ring);
    background: var(--accent-soft);
  }
  .field :global(.baw-mathjax[data-block='true']) {
    display: block;
    margin: 4px 0;
    padding: 6px;
    text-align: center;
  }
  .field :global(.baw-mathjax.empty) {
    min-width: 1.8em;
    min-height: 1.3em;
    border-style: dashed;
  }
  .field :global(.baw-mathjax img) {
    max-width: none;
    max-height: none;
  }
  .math-editor {
    position: absolute;
    z-index: 5;
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(440px, 100%);
    padding: 10px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: var(--shadow);
  }
  .math-source {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.9rem;
    resize: vertical;
  }
  .math-source:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .math-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .segmented {
    display: inline-flex;
  }
  .segmented button,
  .math-btn {
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--muted);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
  }
  .segmented button:first-child {
    border-radius: 7px 0 0 7px;
  }
  .segmented button:last-child {
    margin-left: -1px;
    border-radius: 0 7px 7px 0;
  }
  .segmented button.active {
    position: relative;
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }
  .math-btn {
    border-radius: 7px;
  }
  .math-btn.primary {
    border-color: var(--accent);
    background: var(--accent);
    color: #fff;
  }
  .math-hint {
    margin-left: auto;
    color: var(--faint);
    font-size: 0.75rem;
  }
  .locked-note {
    margin: 0;
    color: var(--muted);
    font-size: 0.8rem;
  }
</style>
