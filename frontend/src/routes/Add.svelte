<script lang="ts">
  import { onMount, tick } from 'svelte';
  import FieldEditor, { plainText, toStorage } from '../components/FieldEditor.svelte';
  import Icon from '../components/Icon.svelte';
  import { api, ApiError, errorMessage } from '../lib/api';
  import { toast } from '../lib/toast.svelte';
  import type { DeckName, Notetype } from '../lib/types';

  let notetypes = $state<Notetype[]>([]);
  let decks = $state<DeckName[]>([]);
  let allTags = $state<string[]>([]);
  let mediaBase = $state('');
  let notetypeId = $state<number | null>(null);
  let deckId = $state<number | null>(null);
  let fields = $state<string[]>([]);
  let tags = $state('');
  let busy = $state(false);
  let loadError = $state<string | null>(null);
  let warning = $state<string | null>(null);
  let activeField = $state(0);
  let tagsFocused = $state(false);
  let history = $state<{ id: number; text: string; cards: number }[]>([]);
  let editors: (ReturnType<typeof FieldEditor> | undefined)[] = $state([]);
  let fileInput: HTMLInputElement | undefined = $state();

  const notetype = $derived(notetypes.find((n) => n.id === notetypeId) ?? null);

  onMount(async () => {
    try {
      const [types, deckList, defaults, tagList] = await Promise.all([
        api<Notetype[]>('/api/notetypes'),
        api<DeckName[]>('/api/decks/names'),
        api<{ notetype_id: number; deck_id: number; media_base: string }>('/api/add/defaults'),
        api<string[]>('/api/tags'),
      ]);
      notetypes = types;
      decks = deckList;
      allTags = tagList;
      mediaBase = new URL(defaults.media_base, location.origin).href;
      const startType = types.find((t) => t.id === defaults.notetype_id) ?? types[0];
      notetypeId = startType?.id ?? null;
      fields = startType ? startType.fields.map(() => '') : [];
      deckId = deckList.some((d) => d.id === defaults.deck_id) ? defaults.deck_id : (deckList[0]?.id ?? null);
      await tick();
      editors[0]?.focus();
    } catch (err) {
      loadError = errorMessage(err);
    }
  });

  async function changeNotetype(id: number): Promise<void> {
    const previous = notetype;
    const previousFields = fields;
    const next = notetypes.find((n) => n.id === id);
    if (!next) return;
    notetypeId = id;
    // Carry content over to fields with the same name.
    fields = next.fields.map((f) => {
      const index = previous?.fields.findIndex((p) => p.name === f.name) ?? -1;
      return index >= 0 ? previousFields[index] : '';
    });
    warning = null;
    try {
      const res = await api<{ deck_id: number | null }>(`/api/notetypes/${id}/default-deck`);
      if (res.deck_id && decks.some((d) => d.id === res.deck_id)) deckId = res.deck_id;
    } catch {
      // Keep the current deck.
    }
  }

  async function upload(file: File): Promise<string> {
    const form = new FormData();
    const name = file.name && file.name !== 'image.png' ? file.name : `paste-${Date.now()}.${file.type.split('/')[1] || 'png'}`;
    form.append('file', file, name);
    const res = await api<{ filename: string }>('/api/media', { form });
    return res.filename;
  }

  async function add(force = false): Promise<void> {
    if (busy || !notetype || deckId === null) return;
    busy = true;
    warning = null;
    try {
      const res = await api<{ note_id: number; card_count: number }>('/api/notes', {
        body: { notetype_id: notetype.id, deck_id: deckId, fields: fields.map(toStorage), tags, force },
      });
      history = [{ id: res.note_id, text: plainText(fields[0]) || '(no text)', cards: res.card_count }, ...history].slice(0, 8);
      for (const tag of tags.split(/\s+/)) {
        if (tag && !allTags.includes(tag)) allTags = [...allTags, tag];
      }
      toast(res.card_count === 1 ? 'Added 1 card' : `Added ${res.card_count} cards`);
      fields = fields.map((value, i) => (notetype?.fields[i]?.sticky ? value : ''));
      await tick();
      editors[0]?.focus();
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

  // Formatting

  function format(command: string): void {
    editors[activeField]?.focus();
    document.execCommand(command);
  }

  function cloze(sameNumber: boolean): void {
    editors[activeField]?.focus();
    const numbers = [...fields.join(' ').matchAll(/\{\{c(\d+)::/g)].map((m) => Number(m[1]));
    const highest = numbers.length ? Math.max(...numbers) : 0;
    const n = sameNumber ? Math.max(1, highest) : highest + 1;
    const selection = window.getSelection();
    if (selection && selection.rangeCount && !selection.isCollapsed) {
      const holder = document.createElement('div');
      holder.appendChild(selection.getRangeAt(0).cloneContents());
      document.execCommand('insertHTML', false, `{{c${n}::${holder.innerHTML}}}`);
    } else {
      document.execCommand('insertText', false, `{{c${n}::}}`);
      selection?.modify('move', 'backward', 'character');
      selection?.modify('move', 'backward', 'character');
    }
  }

  function pickImage(): void {
    fileInput?.click();
  }

  async function onFilesChosen(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    if (files.length) await editors[activeField]?.insertFiles(files);
  }

  function onKeydown(event: KeyboardEvent): void {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key === 'Enter') {
      event.preventDefault();
      add();
    } else if (mod && event.shiftKey && event.code === 'KeyC' && notetype?.is_cloze) {
      event.preventDefault();
      cloze(event.altKey);
    }
  }

  // Tags

  const tagSuggestions = $derived.by(() => {
    if (!tagsFocused) return [];
    const parts = tags.split(/\s+/);
    const last = parts[parts.length - 1]?.toLowerCase() ?? '';
    if (!last) return [];
    const used = new Set(parts.slice(0, -1));
    return allTags
      .filter((t) => t.toLowerCase().includes(last) && t.toLowerCase() !== last && !used.has(t))
      .slice(0, 6);
  });

  function acceptTag(tag: string): void {
    const parts = tags.split(/\s+/);
    parts[parts.length - 1] = tag;
    tags = parts.join(' ') + ' ';
  }

  function onTagKeydown(event: KeyboardEvent): void {
    if (event.key === 'Tab' && tagSuggestions.length && !event.shiftKey) {
      event.preventDefault();
      acceptTag(tagSuggestions[0]);
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<section class="page">
  <h1>Add cards</h1>

  {#if loadError}
    <p class="error-text">{loadError}</p>
  {:else if !notetype}
    <p class="muted">Loading…</p>
  {:else}
    <div class="panel">
      <div class="pickers">
        <label class="picker">
          <span>Type</span>
          <select value={notetypeId} onchange={(e) => changeNotetype(Number(e.currentTarget.value))}>
            {#each notetypes as nt (nt.id)}
              <option value={nt.id}>{nt.name}</option>
            {/each}
          </select>
        </label>
        <label class="picker">
          <span>Deck</span>
          <select bind:value={deckId}>
            {#each decks as deck (deck.id)}
              <option value={deck.id}>{deck.name}</option>
            {/each}
          </select>
        </label>
      </div>

      <div class="toolbar" role="toolbar" aria-label="Formatting">
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('bold')} title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('italic')} title="Italic (Ctrl+I)"><i>I</i></button>
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('underline')} title="Underline (Ctrl+U)"><u>U</u></button>
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('superscript')} title="Superscript"><span>x<sup>2</sup></span></button>
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('subscript')} title="Subscript"><span>x<sub>2</sub></span></button>
        <button type="button" onmousedown={(e) => e.preventDefault()} onclick={() => format('removeFormat')} title="Clear formatting"><span>T<sub>×</sub></span></button>
        <span class="sep"></span>
        {#if notetype.is_cloze}
          <button type="button" class="wide" onmousedown={(e) => e.preventDefault()} onclick={() => cloze(false)} title="Cloze deletion (Ctrl+Shift+C; add Alt to reuse the number)">[…] Cloze</button>
        {/if}
        <button type="button" class="wide" onmousedown={(e) => e.preventDefault()} onclick={pickImage} title="Insert image or audio (you can also paste or drop files)">
          <Icon name="image" size={16} /> Media
        </button>
        <input bind:this={fileInput} type="file" accept="image/*,audio/*" multiple hidden onchange={onFilesChosen} />
      </div>

      <div class="fields">
        {#each notetype.fields as field, i (`${notetype.id}:${i}`)}
          <FieldEditor
            bind:this={editors[i]}
            id="field-{i}"
            label={field.name}
            sticky={field.sticky}
            bind:value={fields[i]}
            {mediaBase}
            onupload={upload}
            onfocus={() => (activeField = i)}
          />
        {/each}

        <div class="tags">
          <label class="field-label" for="tags">Tags</label>
          <input
            id="tags"
            type="text"
            bind:value={tags}
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
                <button type="button" class="chip" onmousedown={(e) => e.preventDefault()} onclick={() => acceptTag(tag)}>{tag}</button>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      {#if warning}
        <div class="warning" role="alert">
          <Icon name="alert" />
          <span>{warning}</span>
          <button class="btn small" onclick={() => add(true)}>Add anyway</button>
        </div>
      {/if}

      <div class="actions">
        <span class="hint muted">Ctrl+Enter to add</span>
        <button class="btn primary" onclick={() => add()} disabled={busy || deckId === null}>
          {busy ? 'Adding…' : 'Add'}
        </button>
      </div>
    </div>

    {#if history.length}
      <div class="history">
        <h2>Added just now</h2>
        <ul>
          {#each history as item (item.id)}
            <li>
              <span class="history-text">{item.text}</span>
              <span class="muted">{item.cards} card{item.cards === 1 ? '' : 's'}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/if}
</section>

<style>
  .page {
    max-width: 760px;
    margin: 0 auto;
    padding: 20px 16px 64px;
  }
  h1 {
    margin: 0 0 16px;
    font-size: 1.25rem;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
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
    gap: 12px;
  }
  .hint {
    font-size: 0.85rem;
  }
  .history {
    margin-top: 24px;
  }
  .history h2 {
    margin: 0 0 8px;
    font-size: 0.95rem;
    color: var(--muted);
  }
  .history ul {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }
  .history li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    font-size: 0.925rem;
  }
  .history li:first-child {
    border-top: 0;
  }
  .history-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
