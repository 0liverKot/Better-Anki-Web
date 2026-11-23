<script lang="ts">
  /** Loads an existing note into the shared NoteEditor and saves it back. */
  import { onMount } from 'svelte';
  import NoteEditor, { type NoteValues } from './NoteEditor.svelte';
  import { api, errorMessage } from '../lib/api';
  import type { DeckName, NoteEditData } from '../lib/types';

  interface Props {
    noteId: number;
    decks: DeckName[];
    onsaved: (result: { cards_moved: number }) => void;
    oncancel: () => void;
  }
  let { noteId, decks, onsaved, oncancel }: Props = $props();

  let data = $state<NoteEditData | null>(null);
  let allTags = $state<string[]>([]);
  let error = $state<string | null>(null);
  let editor: ReturnType<typeof NoteEditor> | undefined = $state();

  onMount(async () => {
    try {
      const [note, tags] = await Promise.all([
        api<NoteEditData>(`/api/notes/${noteId}/edit`),
        api<string[]>('/api/tags'),
      ]);
      allTags = tags;
      data = note;
      queueMicrotask(() => editor?.focus());
    } catch (err) {
      error = errorMessage(err);
    }
  });

  const mixedDeckLabel = $derived(
    data && data.deck_id === null ? `Keep in current decks (${data.deck_names.join(', ')})` : undefined,
  );

  async function save(values: NoteValues, force: boolean): Promise<void> {
    if (!data) return;
    const res = await api<{ cards_moved: number }>(`/api/notes/${noteId}`, {
      method: 'PUT',
      body: {
        fields: values.fields,
        tags: values.tags,
        deck_id: values.deckId,
        version: data.version,
        force,
      },
    });
    onsaved(res);
  }
</script>

<div class="edit">
  {#if error}
    <p class="error-text">{error}</p>
    <button class="btn small" onclick={oncancel}>Close</button>
  {:else if !data}
    <p class="muted">Loading editor…</p>
  {:else}
    <NoteEditor
      bind:this={editor}
      mode="edit"
      notetypes={[data.notetype]}
      {decks}
      {allTags}
      mediaBase={new URL(data.media_base, location.origin).href}
      initial={{ notetypeId: data.notetype.id, deckId: data.deck_id, fields: data.fields, tags: data.tags }}
      {mixedDeckLabel}
      submitLabel="Save"
      busyLabel="Saving…"
      onsubmit={save}
      {oncancel}
    />
  {/if}
</div>

<style>
  .edit {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px 16px 16px;
    border-top: 1px dashed var(--border);
    background: var(--surface-2);
  }
  .edit p {
    margin: 0;
  }
</style>
