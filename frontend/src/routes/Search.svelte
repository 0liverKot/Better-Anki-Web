<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../components/Icon.svelte';
  import NoteEdit from '../components/NoteEdit.svelte';
  import NotePreview from '../components/NotePreview.svelte';
  import { api, errorMessage } from '../lib/api';
  import { onSynced } from '../lib/sync.svelte';
  import { toast } from '../lib/toast.svelte';
  import type { DeckName, NoteDetail, SearchNote, SearchResult } from '../lib/types';

  const PAGE = 50;
  const initial = new URLSearchParams(location.hash.split('?')[1] ?? '');

  let query = $state(initial.get('q') ?? '');
  let deckId = $state<number | ''>(initial.get('deck') ? Number(initial.get('deck')) : '');
  let decks = $state<DeckName[]>([]);
  let total = $state(0);
  let notes = $state<SearchNote[]>([]);
  let usedPlainText = $state(false);
  let loading = $state(true);
  let loadingMore = $state(false);
  let error = $state<string | null>(null);
  let openId = $state<number | null>(null);
  let detail = $state<NoteDetail | null>(null);
  let editingId = $state<number | null>(null);
  let input: HTMLInputElement | undefined = $state();
  let seq = 0;

  onMount(() => {
    input?.focus();
    api<DeckName[]>('/api/decks/names')
      .then((list) => (decks = list))
      .catch(() => {});
    return onSynced(() => run(query, deckId));
  });

  // Search as you type (debounced). Reading query/deckId here makes the effect track them.
  $effect(() => {
    const q = query;
    const d = deckId;
    const timer = setTimeout(() => run(q, d), q ? 250 : 0);
    return () => clearTimeout(timer);
  });

  function params(q: string, d: number | '', offset = 0): string {
    const p = new URLSearchParams({ q, limit: String(PAGE), offset: String(offset) });
    if (d) p.set('deck_id', String(d));
    return p.toString();
  }

  async function run(q: string, d: number | ''): Promise<void> {
    const mine = ++seq;
    // Keep the search in the URL (without adding history entries) so reload/back work.
    const url = new URLSearchParams();
    if (q) url.set('q', q);
    if (d) url.set('deck', String(d));
    const suffix = url.toString();
    history.replaceState(null, '', `#/search${suffix ? `?${suffix}` : ''}`);

    loading = true;
    error = null;
    try {
      const res = await api<SearchResult>(`/api/search?${params(q, d)}`);
      if (mine !== seq) return;
      total = res.total;
      notes = res.notes;
      usedPlainText = !!res.syntax_note;
      openId = null;
      detail = null;
      editingId = null;
    } catch (err) {
      if (mine === seq) error = errorMessage(err);
    } finally {
      if (mine === seq) loading = false;
    }
  }

  async function loadMore(): Promise<void> {
    loadingMore = true;
    try {
      const res = await api<SearchResult>(`/api/search?${params(query, deckId, notes.length)}`);
      const seen = new Set(notes.map((n) => n.id));
      notes = [...notes, ...res.notes.filter((n) => !seen.has(n.id))];
      total = res.total;
    } catch (err) {
      toast(errorMessage(err), 'error');
    } finally {
      loadingMore = false;
    }
  }

  async function toggle(note: SearchNote): Promise<void> {
    if (openId === note.id) {
      if (editingId === note.id && !confirm('Discard your changes to this note?')) return;
      openId = null;
      detail = null;
      editingId = null;
      return;
    }
    if (editingId !== null && !confirm('Discard your changes to the note you were editing?')) return;
    openId = note.id;
    detail = null;
    editingId = null;
    await loadDetail(note.id);
  }

  async function loadDetail(id: number): Promise<void> {
    try {
      const res = await api<NoteDetail>(`/api/notes/${id}`);
      if (openId === id) detail = res;
    } catch (err) {
      toast(errorMessage(err), 'error');
      if (openId === id) openId = null;
    }
  }

  async function saved(note: SearchNote, result: { cards_moved: number }): Promise<void> {
    editingId = null;
    toast(result.cards_moved ? `Saved, and moved ${result.cards_moved} card${result.cards_moved === 1 ? '' : 's'}` : 'Saved');
    detail = null;
    await loadDetail(note.id);
    // Show the new content in the result row too (it stays in the list even if it no
    // longer matches the search, so it doesn't jump away while you're looking at it).
    if (detail) {
      const fresh = detail as NoteDetail;
      const index = notes.findIndex((n) => n.id === note.id);
      if (index >= 0) {
        notes[index] = {
          ...notes[index],
          fields: fresh.note.fields,
          tags: fresh.note.tags,
          decks: [...new Set(fresh.cards.map((c) => c.deck))].sort(),
        };
      }
    }
  }

  // Highlighting the words that matched
  const terms = $derived.by(() => {
    const found: string[] = [];
    for (const m of query.matchAll(/"([^"]+)"|(\S+)/g)) {
      const token = m[1] ?? m[2];
      if (!m[1] && (token.includes(':') || token.startsWith('-') || /^(and|or)$/i.test(token))) continue;
      const clean = token.replace(/[*_\\()"]/g, '').trim();
      if (clean) found.push(clean.toLowerCase());
    }
    return [...new Set(found)].sort((a, b) => b.length - a.length);
  });

  const termRe = $derived(
    terms.length
      ? new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
      : null,
  );

  /** "{{c1::Paris::capital}}" -> "Paris", so cloze notes read naturally in the list. */
  function clozeText(text: string): string {
    return text.replace(/\{\{c\d+::(.*?)(?:::[^}]*)?\}\}/g, '$1');
  }

  function segments(text: string): { text: string; hit: boolean }[] {
    if (!termRe || !text) return [{ text, hit: false }];
    return text
      .split(termRe)
      .map((part, i) => ({ text: part, hit: i % 2 === 1 }))
      .filter((s) => s.text);
  }
</script>

{#snippet highlighted(text: string)}
  {#each segments(text) as seg, i (i)}{#if seg.hit}<mark>{seg.text}</mark>{:else}{seg.text}{/if}{/each}
{/snippet}

<section class="page">
  <h1>Search</h1>

  <div class="searchbar">
    <label class="input-wrap">
      <Icon name="search" />
      <input
        bind:this={input}
        bind:value={query}
        type="search"
        placeholder="Search words on the front or back…"
        aria-label="Search cards"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
      />
    </label>
    <select bind:value={deckId} aria-label="Deck">
      <option value="">All decks</option>
      {#each decks as deck (deck.id)}
        <option value={deck.id}>{deck.name}</option>
      {/each}
    </select>
  </div>

  <p class="hint muted">
    Anki search works too: <code>"exact phrase"</code>, <code>-exclude</code>, <code>front:word</code>,
    <code>tag:name</code>, <code>is:due</code>.
  </p>

  {#if usedPlainText}
    <p class="note">That isn't valid Anki search syntax, so it was searched for as exact text.</p>
  {/if}

  <div class="panel">
    <div class="summary">
      {#if error}
        <span class="error-text">{error}</span>
      {:else if loading && !notes.length}
        <span class="muted">Searching…</span>
      {:else}
        <span class="muted">{total} {total === 1 ? 'note' : 'notes'}{query || deckId ? ' found' : ''}</span>
        {#if loading}<span class="muted">· updating…</span>{/if}
      {/if}
    </div>

    {#if notes.length}
      <ul class="results">
        {#each notes as note (note.id)}
          {@const front = clozeText(note.fields[0]?.text ?? '')}
          {@const back = note.fields.slice(1).map((f) => clozeText(f.text)).filter(Boolean).join(' · ')}
          <li class:open={openId === note.id}>
            <button class="result" onclick={() => toggle(note)} aria-expanded={openId === note.id}>
              <span class="texts">
                <span class="front">{#if front}{@render highlighted(front)}{:else}<em class="muted">(empty)</em>{/if}</span>
                {#if back}<span class="back">{@render highlighted(back)}</span>{/if}
              </span>
              <span class="meta">
                <span class="deck">{note.decks.join(', ')}</span>
                <span class="kind">{note.notetype}{note.card_count > 1 ? ` · ${note.card_count} cards` : ''}</span>
              </span>
              <span class="chev"><Icon name={openId === note.id ? 'chevronDown' : 'chevronRight'} size={16} /></span>
            </button>
            {#if openId === note.id}
              {#if editingId === note.id}
                <NoteEdit
                  noteId={note.id}
                  {decks}
                  onsaved={(result) => saved(note, result)}
                  oncancel={() => (editingId = null)}
                />
              {:else if detail}
                <NotePreview {detail} onedit={detail.note.editable ? () => (editingId = note.id) : undefined} />
              {:else}
                <p class="loading muted">Loading preview…</p>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
      {#if notes.length < total}
        <div class="more">
          <button class="btn" onclick={loadMore} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : `Show more (${total - notes.length} left)`}
          </button>
        </div>
      {/if}
    {:else if !loading && !error}
      <p class="empty muted">No cards match{query ? ` "${query}"` : ''}.</p>
    {/if}
  </div>
</section>

<style>
  .page {
    max-width: 860px;
    margin: 0 auto;
    padding: 20px 16px 64px;
  }
  h1 {
    margin: 0 0 16px;
    font-size: 1.25rem;
  }
  .searchbar {
    display: grid;
    grid-template-columns: 1fr minmax(160px, 240px);
    gap: 10px;
  }
  .input-wrap {
    position: relative;
    display: flex;
    align-items: center;
    color: var(--muted);
  }
  .input-wrap :global(svg) {
    position: absolute;
    left: 12px;
    pointer-events: none;
  }
  .input-wrap input {
    width: 100%;
    min-height: 44px;
    padding: 8px 12px 8px 38px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    font: inherit;
  }
  .hint {
    margin: 10px 2px 14px;
    font-size: 0.85rem;
    line-height: 1.6;
  }
  code {
    padding: 1px 5px;
    border-radius: 5px;
    background: var(--surface-3);
    color: var(--text);
    font-size: 0.8rem;
  }
  .note {
    margin: 0 0 12px;
    padding: 8px 12px;
    border: 1px solid var(--warn-border);
    border-radius: var(--radius);
    background: var(--warn-soft);
    font-size: 0.9rem;
  }
  .panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    overflow: hidden;
  }
  .summary {
    display: flex;
    gap: 6px;
    padding: 10px 16px;
    font-size: 0.875rem;
  }
  .results {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .results li {
    border-top: 1px solid var(--border);
  }
  .result {
    display: grid;
    grid-template-columns: 1fr auto 20px;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 12px 12px 12px 16px;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .result:hover,
  .open .result {
    background: var(--surface-2);
  }
  .texts {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .front,
  .back {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .front {
    font-weight: 500;
  }
  .back {
    color: var(--muted);
    font-size: 0.9rem;
  }
  mark {
    padding: 0 1px;
    border-radius: 3px;
    background: var(--mark, #ffe58f);
    color: inherit;
  }
  @media (prefers-color-scheme: dark) {
    mark {
      background: #5c4a12;
    }
  }
  .meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    max-width: 240px;
    min-width: 0;
    font-size: 0.8rem;
    text-align: right;
  }
  .deck {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
  }
  .kind {
    color: var(--muted);
  }
  .chev {
    color: var(--muted);
  }
  .loading,
  .empty {
    margin: 0;
    padding: 16px;
  }
  .empty {
    border-top: 1px solid var(--border);
  }
  .more {
    display: flex;
    justify-content: center;
    padding: 12px;
    border-top: 1px solid var(--border);
  }
  @media (max-width: 560px) {
    .searchbar {
      grid-template-columns: 1fr;
    }
    .result {
      grid-template-columns: 1fr 20px;
    }
    .meta {
      grid-column: 1;
      grid-row: 2;
      flex-direction: row;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 2px 8px;
      max-width: none;
      text-align: left;
    }
    .deck {
      white-space: normal;
      overflow-wrap: anywhere;
    }
  }
</style>
