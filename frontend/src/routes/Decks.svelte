<script lang="ts">
  import { onMount, tick } from 'svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import DeckRow, { type DeckActions } from '../components/DeckRow.svelte';
  import Icon from '../components/Icon.svelte';
  import { api, errorMessage } from '../lib/api';
  import { DeckDrag } from '../lib/deckDrag.svelte';
  import { createDeck, deckInfo, deleteDeck, moveDeck, renameDeck } from '../lib/decks';
  import { onSynced, sync } from '../lib/sync.svelte';
  import { toast } from '../lib/toast.svelte';
  import type { DeckInfo, DeckNode } from '../lib/types';

  let decks = $state<DeckNode[] | null>(null);
  let error = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      decks = (await api<{ decks: DeckNode[] }>('/api/decks')).decks;
      error = null;
    } catch (err) {
      error = errorMessage(err);
    }
  }

  onMount(() => {
    load();
    const off = onSynced(load);
    return () => {
      off();
      deckDrag.destroy();
    };
  });

  async function toggle(deck: DeckNode): Promise<void> {
    deck.collapsed = !deck.collapsed;
    try {
      await api(`/api/decks/${deck.id}/collapse`, { body: { collapsed: deck.collapsed } });
    } catch (err) {
      deck.collapsed = !deck.collapsed;
      toast(errorMessage(err), 'error');
    }
  }

  // Creating a deck

  let creating = $state(false);
  let newName = $state('');
  let createError = $state<string | null>(null);
  let createBusy = $state(false);
  let highlightId = $state<number | null>(null);
  let nameInput: HTMLInputElement | undefined = $state();

  async function openCreate(): Promise<void> {
    creating = true;
    createError = null;
    await tick();
    nameInput?.focus();
  }

  function closeCreate(): void {
    creating = false;
    newName = '';
    createError = null;
  }

  async function submitCreate(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (createBusy) return;
    createBusy = true;
    createError = null;
    try {
      const { deck, existed } = await createDeck(newName);
      if (existed) {
        createError = `A deck called "${deck.name}" already exists.`;
        return;
      }
      await load(); // (the server expands the parents of a new subdeck)
      toast(`Created deck "${deck.name}"`);
      closeCreate();
      flash(deck.id);
    } catch (err) {
      createError = errorMessage(err);
    } finally {
      createBusy = false;
    }
  }

  async function flash(id: number): Promise<void> {
    highlightId = null; // (restarts the animation if it's the same row again)
    await tick();
    highlightId = id;
    setTimeout(() => {
      if (highlightId === id) highlightId = null;
    }, 2500);
  }

  // Renaming (inline, in the deck's row)

  let renamingId = $state<number | null>(null);

  async function rename(deck: DeckNode, name: string): Promise<string | null> {
    if (name.trim() === deck.full_name) {
      renamingId = null;
      return null;
    }
    try {
      const renamed = await renameDeck(deck.id, name);
      await load(); // (the server expands the new parents of a moved deck)
      renamingId = null;
      toast(`Renamed to "${renamed.name}"`);
      flash(deck.id);
      return null;
    } catch (err) {
      return errorMessage(err);
    }
  }

  // Deleting (after confirming)

  let deleting = $state<DeckNode | null>(null);
  let deleteInfo = $state<DeckInfo | null>(null);
  let deleteError = $state<string | null>(null);
  let deleteBusy = $state(false);

  async function askDelete(deck: DeckNode): Promise<void> {
    deleting = deck;
    deleteInfo = null;
    deleteError = null;
    try {
      const info = await deckInfo(deck.id);
      if (deleting === deck) deleteInfo = info;
    } catch (err) {
      if (deleting === deck) deleteError = errorMessage(err);
    }
  }

  function closeDelete(): void {
    if (deleteBusy) return;
    deleting = null;
  }

  async function confirmDelete(): Promise<void> {
    if (!deleting || !deleteInfo || deleteBusy) return;
    const deck = deleting;
    deleteBusy = true;
    try {
      const result = await deleteDeck(deck.id);
      deleteBusy = false;
      deleting = null;
      const cards = result.cards_deleted;
      toast(`Deleted "${result.name}"` + (cards ? ` and ${plural(cards, 'card')}` : ''));
      await load();
      // (it may have been renaming the deleted deck or one of its subdecks)
      if (renamingId !== null && !findDeck(decks ?? [], renamingId)) renamingId = null;
    } catch (err) {
      deleteBusy = false;
      deleteError = errorMessage(err);
    }
  }

  function findDeck(list: DeckNode[], id: number): DeckNode | null {
    for (const deck of list) {
      if (deck.id === id) return deck;
      const found = findDeck(deck.children, id);
      if (found) return found;
    }
    return null;
  }

  function plural(n: number, word: string): string {
    return `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`;
  }

  // Moving a deck by dragging it onto another one (or onto the header: top level)

  function parentName(deck: DeckNode): string | null {
    const cut = deck.full_name.lastIndexOf('::');
    return cut < 0 ? null : deck.full_name.slice(0, cut);
  }

  function canDrop(source: DeckNode, target: number | 'root'): boolean {
    if (target === 'root') return parentName(source) !== null;
    const deck = findDeck(decks ?? [], target);
    if (!deck || deck.id === source.id || deck.filtered) return false; // filtered decks can't have subdecks
    const into = deck.full_name.toLowerCase();
    const from = source.full_name.toLowerCase();
    if (into.startsWith(from + '::')) return false; // one of its own subdecks
    return parentName(source)?.toLowerCase() !== into; // (already in it)
  }

  async function drop(source: DeckNode, target: number | 'root'): Promise<void> {
    const parent = target === 'root' ? null : findDeck(decks ?? [], target);
    try {
      await moveDeck(source.id, parent?.id ?? null);
      await load(); // (the server expands the deck it was moved into)
      toast(parent ? `Moved "${source.name}" into "${parent.full_name}"` : `Moved "${source.name}" to the top level`);
      flash(source.id);
    } catch (err) {
      toast(errorMessage(err), 'error', 4000);
    }
  }

  const deckDrag = new DeckDrag({ find: (id) => findDeck(decks ?? [], id), canDrop, ondrop: drop });
  const rootDroppable = $derived(deckDrag.source !== null && parentName(deckDrag.source) !== null);
  const dropLabel = $derived.by(() => {
    const target = deckDrag.target;
    if (target === 'root') return 'Move to the top level';
    if (target === null) return null;
    return `Move into "${findDeck(decks ?? [], target)?.name ?? ''}"`;
  });

  const actions: DeckActions = {
    toggle,
    startRename: (deck) => (renamingId = deck.id),
    cancelRename: () => (renamingId = null),
    rename,
    remove: askDelete,
  };

  const status = $derived(sync.status);
  const totals = $derived(
    (decks ?? []).reduce(
      (sum, d) => ({ new: sum.new + d.new, learn: sum.learn + d.learn, review: sum.review + d.review }),
      { new: 0, learn: 0, review: 0 },
    ),
  );
</script>

<section class="page">
  {#if status && !status.logged_in}
    <a class="banner" href="#/settings">
      <Icon name="cloudOff" />
      <span>
        <strong>Connect your AnkiWeb account</strong> to bring in your decks and keep them in sync
        with your other devices.
      </span>
      <Icon name="chevronRight" />
    </a>
  {:else if status?.state === 'full_sync_required'}
    <a class="banner warn" href="#/settings">
      <Icon name="alert" />
      <span><strong>Sync needs your decision.</strong> Pick which copy of your collection to keep.</span>
      <Icon name="chevronRight" />
    </a>
  {:else if status?.state === 'auth_required'}
    <a class="banner warn" href="#/settings">
      <Icon name="alert" />
      <span><strong>AnkiWeb asked you to log in again.</strong> Syncing is paused until you do.</span>
      <Icon name="chevronRight" />
    </a>
  {/if}

  <div class="panel">
    <div class="head" data-drop-root class:root-zone={rootDroppable} class:drop-target={deckDrag.target === 'root'}>
      {#if rootDroppable}
        <span class="root-hint">Drop here to make it a top-level deck</span>
      {:else}
        <h1>Decks</h1>
        <span class="num-head new" title="New cards">New</span>
        <span class="num-head learn" title="Learning">Learn</span>
        <span class="num-head due" title="Due for review">Due</span>
        <span></span>
      {/if}
    </div>
    {#if error}
      <p class="empty">{error} <button class="link" onclick={load}>Retry</button></p>
    {:else if !decks}
      <p class="empty muted">Loading…</p>
    {:else if decks.length === 0}
      <p class="empty muted">No decks yet.</p>
    {:else}
      <ul onpointerdown={deckDrag.pointerdown}>
        {#each decks as deck (deck.id)}
          <DeckRow
            {deck}
            {actions}
            {renamingId}
            {highlightId}
            dragSourceId={deckDrag.source?.id ?? null}
            dropTargetId={typeof deckDrag.target === 'number' ? deckDrag.target : null}
          />
        {/each}
      </ul>
      <div class="total">
        <span>Total due today</span>
        <span class="num new">{totals.new}</span>
        <span class="num learn">{totals.learn}</span>
        <span class="num due">{totals.review}</span>
        <span></span>
      </div>
    {/if}
    {#if decks}
      <div class="create">
        {#if creating}
          <form class="create-form" onsubmit={submitCreate}>
            <label class="create-label" for="new-deck-name">New deck</label>
            <div class="create-row">
              <input
                bind:this={nameInput}
                id="new-deck-name"
                type="text"
                bind:value={newName}
                placeholder="Deck name"
                autocomplete="off"
                onkeydown={(e) => e.key === 'Escape' && closeCreate()}
              />
              <button class="btn primary" type="submit" disabled={createBusy || !newName.trim()}>
                {createBusy ? 'Creating…' : 'Create'}
              </button>
              <button class="btn" type="button" onclick={closeCreate}>Cancel</button>
            </div>
            {#if createError}
              <p class="error-text">{createError}</p>
            {:else}
              <p class="hint muted">To make a subdeck, use <code>Parent::Child</code>, e.g. <code>Spanish::Verbs</code>.</p>
            {/if}
          </form>
        {:else}
          <button class="btn small" onclick={openCreate}>
            <Icon name="plus" size={16} /> Create deck
          </button>
          {#if decks.length}
            <p class="drag-tip muted">
              <span class="tip-mouse">Tip: drag a deck onto another to make it a subdeck.</span>
              <span class="tip-touch">Tip: press and hold a deck, then drag it onto another to make it a subdeck.</span>
            </p>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
</section>

{#if deckDrag.source}
  <div class="drag-ghost" class:touch={deckDrag.touch} style="left: {deckDrag.x}px; top: {deckDrag.y}px" aria-hidden="true">
    <strong>{deckDrag.source.name}</strong>
    {#if dropLabel}<span>{dropLabel}</span>{/if}
  </div>
{/if}

<ConfirmDialog
  open={deleting !== null}
  title={deleting ? `Delete "${deleting.full_name}"?` : ''}
  confirmLabel={deleteBusy ? 'Deleting…' : 'Delete deck'}
  danger
  disabled={!deleteInfo || deleteBusy}
  onconfirm={confirmDelete}
  oncancel={closeDelete}
>
  {#if deleteInfo?.filtered}
    <p>
      It's a filtered deck, so no cards are deleted: its {plural(deleteInfo.cards, 'card')}
      {deleteInfo.cards === 1 ? 'goes' : 'go'} back to {deleteInfo.cards === 1 ? 'its' : 'their'} original
      {deleteInfo.cards === 1 ? 'deck' : 'decks'}.
    </p>
  {:else if deleteInfo}
    {@const subdecks = plural(deleteInfo.subdecks, 'subdeck')}
    {@const cards = plural(deleteInfo.cards, 'card')}
    {@const their = deleteInfo.cards === 1 ? 'its' : 'their'}
    <p>
      {#if deleteInfo.subdecks && deleteInfo.cards}
        This deletes the deck, its <strong>{subdecks}</strong> and <strong>{cards}</strong>, including {their} review history.
      {:else if deleteInfo.cards}
        This deletes the deck and its <strong>{cards}</strong>, including {their} review history.
      {:else if deleteInfo.subdecks}
        This deletes the deck and its <strong>{subdecks}</strong>. There are no cards in them.
      {:else}
        This deletes the deck. There are no cards in it.
      {/if}
    </p>
    <p class="muted">It's also deleted on your other devices when they next sync.</p>
  {:else if !deleteError}
    <p class="muted">Checking what's in this deck…</p>
  {/if}
  {#if deleteError}
    <p class="error-text">{deleteError}</p>
  {/if}
</ConfirmDialog>

<style>
  .page {
    --num-col: 3.6em;
    --action-size: 32px;
    --actions-col: calc(var(--action-size) * 2 + 10px);
    --row-pad-right: 8px;
    max-width: 760px;
    margin: 0 auto;
    padding: 20px 16px 48px;
  }
  .banner {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    padding: 14px 16px;
    border: 1px solid var(--accent-border);
    border-radius: var(--radius);
    background: var(--accent-soft);
    color: var(--text);
    text-decoration: none;
    line-height: 1.4;
  }
  .banner > span {
    flex: 1;
  }
  .banner.warn {
    border-color: var(--warn-border);
    background: var(--warn-soft);
  }
  .panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    overflow: hidden;
  }
  .head,
  .total {
    display: grid;
    grid-template-columns: 1fr var(--num-col) var(--num-col) var(--num-col) var(--actions-col);
    align-items: center;
    padding: 0 var(--row-pad-right) 0 16px;
  }
  .head {
    min-height: 52px; /* same height when it turns into the drop zone */
    padding-top: 14px;
    padding-bottom: 10px;
  }
  .head.root-zone {
    padding-top: 6px;
    padding-bottom: 6px;
  }
  .root-hint {
    grid-column: 1 / -1;
    display: grid;
    place-items: center;
    min-height: 40px;
    margin-right: 8px;
    border: 2px dashed var(--border-strong);
    border-radius: 8px;
    color: var(--muted);
    font-size: 0.9rem;
    font-weight: 600;
  }
  .head.drop-target .root-hint {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }
  .drag-ghost {
    position: fixed;
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: 2px;
    max-width: 260px;
    padding: 7px 12px;
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    background: var(--surface);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    font-size: 0.9rem;
    pointer-events: none;
    transform: translate(14px, 14px);
    overflow-wrap: anywhere;
  }
  .drag-ghost.touch {
    /* above the finger, so it isn't hidden under it */
    transform: translate(-50%, calc(-100% - 28px));
  }
  .drag-ghost span {
    color: var(--accent);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .drag-tip {
    margin: 0;
    font-size: 0.85rem;
  }
  .tip-touch {
    display: none;
  }
  @media (pointer: coarse) {
    .tip-mouse {
      display: none;
    }
    .tip-touch {
      display: inline;
    }
  }
  h1 {
    margin: 0;
    font-size: 1.25rem;
  }
  .num-head {
    text-align: right;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .total {
    padding-top: 12px;
    padding-bottom: 12px;
    border-top: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--muted);
    font-size: 0.9rem;
  }
  .total .num {
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .empty {
    margin: 0;
    padding: 24px 16px;
    border-top: 1px solid var(--border);
  }
  .create {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 14px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
  }
  .create-form {
    flex: 1;
  }
  .create-form {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .create-label {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .create-row {
    display: flex;
    gap: 8px;
  }
  .create-row input {
    flex: 1;
    min-width: 0;
  }
  .hint {
    margin: 0;
    font-size: 0.85rem;
  }
  .hint code {
    padding: 1px 5px;
    border-radius: 5px;
    background: var(--surface-3);
    color: var(--text);
    font-size: 0.8rem;
  }
  @media (max-width: 480px) {
    .page {
      --num-col: 2.9em;
      --action-size: 30px;
      --actions-col: calc(var(--action-size) * 2 + 6px);
      --row-pad-right: 4px;
    }
    .num-head {
      font-size: 0.72rem;
      letter-spacing: 0;
    }
    .create-row {
      flex-wrap: wrap;
    }
    .create-row input {
      flex-basis: 100%;
    }
    .create-row .btn {
      flex: 1;
    }
  }
  @media (max-width: 360px) {
    .page {
      --num-col: 2.4em;
      --action-size: 28px;
      --actions-col: calc(var(--action-size) * 2 + 4px);
      --indent: 12px;
    }
    .num-head {
      font-size: 0.64rem;
    }
  }
  .new {
    color: var(--new);
  }
  .learn {
    color: var(--learn);
  }
  .due {
    color: var(--review);
  }
</style>
