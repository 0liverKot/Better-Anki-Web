<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { plainText } from '../components/FieldEditor.svelte';
  import NoteEditor, { type NoteValues } from '../components/NoteEditor.svelte';
  import { api, errorMessage } from '../lib/api';
  import { toast } from '../lib/toast.svelte';
  import type { DeckName, Notetype } from '../lib/types';

  interface Loaded {
    notetypes: Notetype[];
    decks: DeckName[];
    mediaBase: string;
    initial: NoteValues;
  }

  let loaded = $state<Loaded | null>(null);
  let allTags = $state<string[]>([]);
  let loadError = $state<string | null>(null);
  let history = $state<{ id: number; text: string; cards: number }[]>([]);
  let editor: ReturnType<typeof NoteEditor> | undefined = $state();

  onMount(async () => {
    try {
      const [notetypes, decks, defaults, tags] = await Promise.all([
        api<Notetype[]>('/api/notetypes'),
        api<DeckName[]>('/api/decks/names'),
        api<{ notetype_id: number; deck_id: number; media_base: string }>('/api/add/defaults'),
        api<string[]>('/api/tags'),
      ]);
      const start = notetypes.find((t) => t.id === defaults.notetype_id) ?? notetypes[0];
      allTags = tags;
      loaded = {
        notetypes,
        decks,
        mediaBase: new URL(defaults.media_base, location.origin).href,
        initial: {
          notetypeId: start.id,
          deckId: decks.some((d) => d.id === defaults.deck_id) ? defaults.deck_id : (decks[0]?.id ?? null),
          fields: start.fields.map(() => ''),
          tags: '',
        },
      };
      await tick();
      editor?.focus();
    } catch (err) {
      loadError = errorMessage(err);
    }
  });

  async function add(values: NoteValues, force: boolean): Promise<void> {
    const res = await api<{ note_id: number; card_count: number }>('/api/notes', {
      body: {
        notetype_id: values.notetypeId,
        deck_id: values.deckId,
        fields: values.fields,
        tags: values.tags,
        force,
      },
    });
    history = [{ id: res.note_id, text: plainText(values.fields[0]) || '(no text)', cards: res.card_count }, ...history].slice(0, 8);
    const newTags = values.tags.split(/\s+/).filter((t) => t && !allTags.includes(t));
    if (newTags.length) allTags = [...allTags, ...newTags];
    toast(res.card_count === 1 ? 'Added 1 card' : `Added ${res.card_count} cards`);
    await editor?.reset();
  }
</script>

<section class="page">
  <h1>Add cards</h1>

  {#if loadError}
    <p class="error-text">{loadError}</p>
  {:else if !loaded}
    <p class="muted">Loading…</p>
  {:else}
    <div class="panel">
      <NoteEditor
        bind:this={editor}
        mode="add"
        notetypes={loaded.notetypes}
        decks={loaded.decks}
        {allTags}
        mediaBase={loaded.mediaBase}
        initial={loaded.initial}
        submitLabel="Add"
        busyLabel="Adding…"
        onsubmit={add}
      />
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
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
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
</style>
