<script lang="ts" module>
  /** A note's editable content. Fields are raw HTML, as Anki stores them. */
  export interface NoteValues {
    notetypeId: number;
    deckId: number | null;
    fields: string[];
    tags: string;
  }
</script>

<script lang="ts">
  /**
   * The one note editor, used both for adding cards and for editing existing notes, so
   * editing features (toolbar, media, cloze, tags, HTML view, ...) work the same in both.
   * The parent decides what saving means through `onsubmit`, which should throw the
   * ApiError from the server on failure; 409 responses with a `warning` are shown with a
   * "… anyway" button that resubmits with force=true.
   */
  import { tick } from 'svelte';
  import FieldEditor from './FieldEditor.svelte';
  import Icon from './Icon.svelte';
  import { api, ApiError, errorMessage } from '../lib/api';
  import { toast } from '../lib/toast.svelte';
  import type { DeckName, Notetype } from '../lib/types';

  interface Props {
    mode: 'add' | 'edit';
    notetypes: Notetype[];
    decks: DeckName[];
    allTags: string[];
    mediaBase: string;
    initial: NoteValues;
    submitLabel: string;
    busyLabel: string;
    /** Edit mode: the note's cards are in several decks; offer to leave them there. */
    mixedDeckLabel?: string;
    onsubmit: (values: NoteValues, force: boolean) => Promise<void>;
    oncancel?: () => void;
  }

  let {
    mode,
    notetypes,
    decks,
    allTags,
    mediaBase,
    initial,
    submitLabel,
    busyLabel,
    mixedDeckLabel,
    onsubmit,
    oncancel,
  }: Props = $props();

  // The editor owns its working copy; `initial` only seeds it.
  const seed = (): NoteValues => ({ ...initial, fields: [...initial.fields] });
  let values = $state<NoteValues>(seed());
  let busy = $state(false);
  let warning = $state<string | null>(null);
  let activeField = $state(0);
  let tagsFocused = $state(false);
  let editors: (ReturnType<typeof FieldEditor> | undefined)[] = $state([]);
  let fileInput: HTMLInputElement | undefined = $state();

  const notetype = $derived(notetypes.find((n) => n.id === values.notetypeId) ?? notetypes[0]);
  const fieldIdPrefix = `f${Math.random().toString(36).slice(2, 8)}`;

  export function focus(): void {
    editors[0]?.focus();
  }

  /** After adding: clear the fields (except sticky ones) for the next card. */
  export async function reset(): Promise<void> {
    values.fields = values.fields.map((value, i) => (notetype?.fields[i]?.sticky ? value : ''));
    warning = null;
    await tick();
    focus();
  }

  async function changeNotetype(id: number): Promise<void> {
    const previous = notetype;
    const previousFields = values.fields;
    const next = notetypes.find((n) => n.id === id);
    if (!next) return;
    // Carry content over to fields with the same name.
    values.fields = next.fields.map((f) => {
      const index = previous?.fields.findIndex((p) => p.name === f.name) ?? -1;
      return index >= 0 ? previousFields[index] : '';
    });
    values.notetypeId = id;
    warning = null;
    try {
      const res = await api<{ deck_id: number | null }>(`/api/notetypes/${id}/default-deck`);
      if (res.deck_id && decks.some((d) => d.id === res.deck_id)) values.deckId = res.deck_id;
    } catch {
      // Keep the current deck.
    }
  }

  async function upload(file: File): Promise<string> {
    const form = new FormData();
    const generic = !file.name || file.name === 'image.png';
    const name = generic ? `paste-${Date.now()}.${file.type.split('/')[1] || 'png'}` : file.name;
    form.append('file', file, name);
    return (await api<{ filename: string }>('/api/media', { form })).filename;
  }

  async function submit(force = false): Promise<void> {
    if (busy || (mode === 'add' && values.deckId === null)) return;
    busy = true;
    warning = null;
    try {
      await onsubmit({ ...values, fields: [...values.fields] }, force);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.data?.warning) {
        warning = err.message;
      } else {
        toast(errorMessage(err), 'error');
      }
    } finally {
      busy = false;
    }
  }

  // Toolbar

  function format(command: string): void {
    editors[activeField]?.format(command);
  }

  // Like Anki: inline, block, and chemistry (inline with \ce{...}). Stored as \(...\) / \[...\].
  const MATHJAX = {
    inline: { block: false, prefix: '', suffix: '' },
    block: { block: true, prefix: '', suffix: '' },
    chemistry: { block: false, prefix: '\\ce{', suffix: '}' },
  } as const;

  function mathjax(kind: keyof typeof MATHJAX): void {
    const { block, prefix, suffix } = MATHJAX[kind];
    editors[activeField]?.insertMath(block, prefix, suffix);
  }

  function cloze(sameNumber: boolean): void {
    const numbers = [...values.fields.join(' ').matchAll(/\{\{c(\d+)::/g)].map((m) => Number(m[1]));
    const highest = numbers.length ? Math.max(...numbers) : 0;
    const n = sameNumber ? Math.max(1, highest) : highest + 1;
    editors[activeField]?.wrap(`{{c${n}::`, '}}');
  }

  async function onFilesChosen(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    if (files.length) await editors[activeField]?.insertFiles(files);
  }

  // Keyboard shortcuts, matching Anki desktop's editor:
  //   Ctrl+, / Ctrl+.              bullet / numbered list
  //   Ctrl+Shift+, / Ctrl+Shift+.  outdent / indent (inside lists)
  //   Ctrl+M, M / E / C            MathJax inline / block / chemistry
  //   Ctrl+Shift+C (+Alt)          cloze (same number)
  //   Ctrl+Enter                   add / save
  // Ctrl+M starts a chord: the next key picks the kind, and any other key cancels it.
  let chord = $state<'mathjax' | null>(null);
  const MODIFIER_KEYS = new Set(['Control', 'Meta', 'Shift', 'Alt', 'AltGraph']);

  function onKeydown(event: KeyboardEvent): void {
    const mod = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    const inField = !!(event.target as HTMLElement | null)?.closest?.('.field');

    if (chord) {
      if (MODIFIER_KEYS.has(event.key)) return; // still waiting for the second key
      chord = null;
      const kind = ({ m: 'inline', e: 'block', c: 'chemistry' } as const)[key as 'm' | 'e' | 'c'];
      if (kind && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        mathjax(kind);
        return;
      }
      // Anything else cancels the chord and behaves normally.
    }

    if (mod && event.key === 'Enter') {
      event.preventDefault();
      submit();
    } else if (event.key === 'Escape' && oncancel) {
      event.preventDefault();
      oncancel();
    } else if (!inField || !mod) {
      return;
    } else if (key === 'm' && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      chord = 'mathjax';
    } else if (event.code === 'Comma' || event.code === 'Period') {
      event.preventDefault();
      const field = editors[activeField];
      if (event.shiftKey) field?.indent(event.code === 'Comma');
      else field?.format(event.code === 'Comma' ? 'insertUnorderedList' : 'insertOrderedList');
    } else if (event.shiftKey && event.code === 'KeyC' && notetype?.is_cloze) {
      event.preventDefault();
      cloze(event.altKey);
    }
  }

  // Tags

  const tagSuggestions = $derived.by(() => {
    if (!tagsFocused) return [];
    const parts = values.tags.split(/\s+/);
    const last = parts[parts.length - 1]?.toLowerCase() ?? '';
    if (!last) return [];
    const used = new Set(parts.slice(0, -1));
    return allTags
      .filter((t) => t.toLowerCase().includes(last) && t.toLowerCase() !== last && !used.has(t))
      .slice(0, 6);
  });

  function acceptTag(tag: string): void {
    const parts = values.tags.split(/\s+/);
    parts[parts.length - 1] = tag;
    values.tags = parts.join(' ') + ' ';
  }

  function onTagKeydown(event: KeyboardEvent): void {
    if (event.key === 'Tab' && tagSuggestions.length && !event.shiftKey) {
      event.preventDefault();
      acceptTag(tagSuggestions[0]);
    }
  }

  const noFocusSteal = (e: MouseEvent) => e.preventDefault();
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="editor" onkeydown={onKeydown}>
  <div class="pickers">
    <label class="picker">
      <span>Type</span>
      {#if mode === 'add'}
        <select value={values.notetypeId} onchange={(e) => changeNotetype(Number(e.currentTarget.value))}>
          {#each notetypes as nt (nt.id)}
            <option value={nt.id}>{nt.name}</option>
          {/each}
        </select>
      {:else}
        <!-- Changing an existing note's type isn't supported (it needs a full sync). -->
        <input type="text" value={notetype?.name ?? ''} disabled />
      {/if}
    </label>
    <label class="picker">
      <span>Deck</span>
      <select bind:value={values.deckId}>
        {#if mixedDeckLabel}
          <option value={null}>{mixedDeckLabel}</option>
        {/if}
        {#each decks as deck (deck.id)}
          <option value={deck.id}>{deck.name}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="toolbar" role="toolbar" aria-label="Formatting">
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('bold')} title="Bold (Ctrl+B)"><b>B</b></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('italic')} title="Italic (Ctrl+I)"><i>I</i></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('underline')} title="Underline (Ctrl+U)"><u>U</u></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('superscript')} title="Superscript"><span>x<sup>2</sup></span></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('subscript')} title="Subscript"><span>x<sub>2</sub></span></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('removeFormat')} title="Clear formatting"><span>T<sub>×</sub></span></button>
    <span class="sep"></span>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('insertUnorderedList')} title="Bullet list (Ctrl+,)" aria-label="Bullet list"><Icon name="list" size={17} /></button>
    <button type="button" onmousedown={noFocusSteal} onclick={() => format('insertOrderedList')} title="Numbered list (Ctrl+.)" aria-label="Numbered list"><Icon name="listOrdered" size={17} /></button>
    <span class="sep"></span>
    <button type="button" class="math" onmousedown={noFocusSteal} onclick={() => mathjax('inline')} title="MathJax inline (Ctrl+M, M)" aria-label="MathJax inline">\(&#8202;\)</button>
    <button type="button" class="math" onmousedown={noFocusSteal} onclick={() => mathjax('block')} title="MathJax block (Ctrl+M, E)" aria-label="MathJax block">\[&#8202;\]</button>
    <span class="sep"></span>
    {#if notetype?.is_cloze}
      <button type="button" class="wide" onmousedown={noFocusSteal} onclick={() => cloze(false)} title="Cloze deletion (Ctrl+Shift+C; add Alt to reuse the number)">[…] Cloze</button>
    {/if}
    <button type="button" class="wide" onmousedown={noFocusSteal} onclick={() => fileInput?.click()} title="Insert image or audio (you can also paste or drop files)">
      <Icon name="image" size={16} /> Media
    </button>
    <input bind:this={fileInput} type="file" accept="image/*,audio/*" multiple hidden onchange={onFilesChosen} />
    {#if chord}
      <span class="chord-hint" role="status">
        MathJax: <kbd>M</kbd> inline · <kbd>E</kbd> block · <kbd>C</kbd> chemistry
      </span>
    {/if}
  </div>

  <div class="fields">
    {#if notetype}
      {#each notetype.fields as field, i (`${notetype.id}:${i}`)}
        <FieldEditor
          bind:this={editors[i]}
          id="{fieldIdPrefix}-{i}"
          label={field.name}
          sticky={mode === 'add' && field.sticky}
          bind:value={values.fields[i]}
          {mediaBase}
          onupload={upload}
          onfocus={() => (activeField = i)}
        />
      {/each}
    {/if}

    <div class="tags">
      <label class="field-label" for="{fieldIdPrefix}-tags">Tags</label>
      <input
        id="{fieldIdPrefix}-tags"
        class="tags-input"
        type="text"
        bind:value={values.tags}
        placeholder="space separated, e.g. spanish verbs"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        onfocus={() => (tagsFocused = true)}
        onblur={() => setTimeout(() => (tagsFocused = false), 150)}
        onkeydown={onTagKeydown}
      />
      {#if tagSuggestions.length}
        <div class="suggestions">
          {#each tagSuggestions as tag (tag)}
            <button type="button" class="chip" onmousedown={noFocusSteal} onclick={() => acceptTag(tag)}>{tag}</button>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  {#if warning}
    <div class="warning" role="alert">
      <Icon name="alert" />
      <span>{warning}</span>
      <button class="btn small" onclick={() => submit(true)}>{submitLabel} anyway</button>
    </div>
  {/if}

  <div class="actions">
    <span class="hint muted">Ctrl+Enter to {submitLabel.toLowerCase()}{oncancel ? ', Esc to cancel' : ''}</span>
    {#if oncancel}
      <button class="btn" type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {/if}
    <button class="btn primary" type="button" onclick={() => submit()} disabled={busy || (mode === 'add' && values.deckId === null)}>
      {busy ? busyLabel : submitLabel}
    </button>
  </div>
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .pickers {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .picker {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .picker input:disabled {
    color: var(--muted);
    background: var(--surface-2);
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
    padding: 4px;
    border-radius: var(--radius);
    background: var(--surface-2);
  }
  .toolbar button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-width: 34px;
    height: 34px;
    padding: 0 8px;
    border: 0;
    border-radius: 7px;
    background: none;
    color: var(--text);
    font: inherit;
    font-size: 0.925rem;
    cursor: pointer;
  }
  .toolbar button:hover {
    background: var(--surface-3);
  }
  .toolbar .wide {
    font-size: 0.875rem;
    font-weight: 500;
  }
  .toolbar .math {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.8rem;
    letter-spacing: -0.02em;
  }
  .chord-hint {
    margin-left: auto;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .chord-hint kbd {
    padding: 0 5px;
    border: 1px solid var(--accent-border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.75rem;
  }
  .sep {
    width: 1px;
    height: 20px;
    margin: 0 4px;
    background: var(--border-strong);
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .tags {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-label {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    padding: 4px 10px;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .warning {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 1px solid var(--warn-border);
    border-radius: var(--radius);
    background: var(--warn-soft);
    color: var(--text);
  }
  .warning span {
    flex: 1;
  }
  .actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
  }
  .hint {
    margin-right: auto;
    font-size: 0.85rem;
  }
  @media (max-width: 520px) {
    .pickers {
      grid-template-columns: 1fr;
    }
    .hint {
      display: none;
    }
  }
</style>
