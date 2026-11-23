<script lang="ts" module>
  const AUDIO_EXTS = /\.(mp3|ogg|oga|wav|m4a|aac|flac|opus|webm|mp4|mov)$/i;

  function escapeAttr(value: string): string {
    return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  /** Editor HTML -> what Anki stores: image srcs back to bare media filenames. */
  export function toStorage(html: string): string {
    const template = document.createElement('template');
    template.innerHTML = html;
    template.content.querySelectorAll('img[data-src]').forEach((img) => {
      img.setAttribute('src', img.getAttribute('data-src') ?? '');
      img.removeAttribute('data-src');
    });
    const out = template.innerHTML.trim();
    // An emptied contenteditable often leaves a lone <br> behind.
    return /^(<br\s*\/?>|\s|&nbsp;)*$/i.test(out) ? '' : out;
  }

  export function plainText(html: string): string {
    const template = document.createElement('template');
    template.innerHTML = html;
    return (template.content.textContent ?? '').trim();
  }
</script>

<script lang="ts">
  import { toast } from '../lib/toast.svelte';

  interface Props {
    id: string;
    label: string;
    value: string;
    mediaBase: string;
    sticky?: boolean;
    onfocus?: () => void;
    onupload: (file: File) => Promise<string>;
  }

  let { id, label, value = $bindable(''), mediaBase, sticky = false, onfocus, onupload }: Props = $props();
  let el: HTMLDivElement | undefined = $state();

  export function focus(): void {
    el?.focus();
  }

  /** Make sure the caret is inside this editor before inserting. */
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

  export async function insertFiles(files: File[]): Promise<void> {
    for (const file of files) {
      try {
        const name = await onupload(file);
        ensureCaret();
        if (file.type.startsWith('image/')) {
          const src = mediaBase + encodeURIComponent(name);
          document.execCommand('insertHTML', false, `<img src="${escapeAttr(src)}" data-src="${escapeAttr(name)}">`);
        } else if (file.type.startsWith('audio/') || file.type.startsWith('video/') || AUDIO_EXTS.test(name)) {
          document.execCommand('insertText', false, `[sound:${name}]`);
        } else {
          toast(`Uploaded ${name}, but only images and audio can be inserted.`);
        }
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
</script>

<div class="field-wrap">
  <label class="field-label" for={id}>
    {label}
    {#if sticky}<span class="pin" title="Kept after adding (sticky field)">kept</span>{/if}
  </label>
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
    bind:innerHTML={value}
    {onpaste}
    {ondrop}
    ondragover={(e) => e.preventDefault()}
    onfocus={() => onfocus?.()}
  ></div>
</div>

<style>
  .field-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .pin {
    padding: 1px 6px;
    border-radius: 999px;
    background: var(--surface-3);
    font-size: 0.72rem;
    font-weight: 500;
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
  .field :global(img) {
    max-width: 100%;
    max-height: 240px;
    vertical-align: middle;
  }
</style>
