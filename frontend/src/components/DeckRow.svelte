<script lang="ts" module>
  import type { DeckNode } from '../lib/types';

  export interface DeckActions {
    toggle: (deck: DeckNode) => void;
    startRename: (deck: DeckNode) => void;
    cancelRename: () => void;
    /** Resolves to an error message to show, or null once renamed. */
    rename: (deck: DeckNode, name: string) => Promise<string | null>;
    remove: (deck: DeckNode) => void;
  }
</script>

<script lang="ts">
  import { tick, untrack } from 'svelte';
  import Icon from './Icon.svelte';
  import DeckRow from './DeckRow.svelte';

  interface Props {
    deck: DeckNode;
    depth?: number;
    actions: DeckActions;
    /** The deck whose name is being edited, if any. */
    renamingId?: number | null;
    /** Briefly highlighted (e.g. a deck that was just created). */
    highlightId?: number | null;
    /** The deck being dragged, and the deck it would be dropped into. */
    dragSourceId?: number | null;
    dropTargetId?: number | null;
  }
  let {
    deck,
    depth = 0,
    actions,
    renamingId = null,
    highlightId = null,
    dragSourceId = null,
    dropTargetId = null,
  }: Props = $props();

  const renaming = $derived(deck.id === renamingId);
  let draft = $state('');
  let renameError = $state<string | null>(null);
  let saving = $state(false);
  let input: HTMLInputElement | undefined = $state();

  $effect(() => {
    // Untracked: a background refresh of the deck list mustn't reset what's being typed.
    if (renaming) untrack(startEditing);
  });

  async function startEditing(): Promise<void> {
    // The full name, so the deck can also be moved, e.g. "Verbs" -> "Spanish::Verbs".
    draft = deck.full_name;
    renameError = null;
    await tick();
    if (!input) return;
    input.focus();
    // Select just the last part, so typing renames it without moving it.
    const cut = draft.lastIndexOf('::');
    input.setSelectionRange(cut >= 0 ? cut + 2 : 0, draft.length);
  }

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (saving) return;
    saving = true;
    renameError = await actions.rename(deck, draft);
    saving = false;
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      actions.cancelRename();
    }
  }
</script>

<li class:dragging={deck.id === dragSourceId}>
  <div
    class="row"
    class:highlight={deck.id === highlightId}
    class:renaming
    class:drop-target={deck.id === dropTargetId}
    data-deck-id={deck.id}
    style="--depth: {depth}"
  >
    {#if deck.children.length}
      <button
        class="toggle"
        onclick={() => actions.toggle(deck)}
        aria-label={deck.collapsed ? `Expand ${deck.name}` : `Collapse ${deck.name}`}
        aria-expanded={!deck.collapsed}
      >
        <Icon name={deck.collapsed ? 'chevronRight' : 'chevronDown'} size={16} />
      </button>
    {:else}
      <span class="toggle-space"></span>
    {/if}

    {#if renaming}
      <form class="rename" onsubmit={submit}>
        <div class="rename-row">
          <input
            bind:this={input}
            type="text"
            bind:value={draft}
            aria-label="New name for {deck.full_name}"
            autocomplete="off"
            onkeydown={onKeydown}
          />
          <button class="icon-btn save" type="submit" disabled={saving || !draft.trim()} aria-label="Save name" title="Save (Enter)">
            <Icon name="check" />
          </button>
          <button class="icon-btn" type="button" onclick={actions.cancelRename} aria-label="Cancel renaming" title="Cancel (Esc)">
            <Icon name="x" />
          </button>
        </div>
        {#if renameError}
          <p class="error-text">{renameError}</p>
        {:else}
          <p class="hint muted">To move it into another deck, use <code>Parent::{deck.name}</code>.</p>
        {/if}
      </form>
    {:else}
      <!-- (draggable=false: rows are dragged with pointer events, not as links) -->
      <a class="name" class:filtered={deck.filtered} href="#/review/{deck.id}" draggable="false">{deck.name}</a>
      <span class="num new" class:zero={!deck.new}>{deck.new}</span>
      <span class="num learn" class:zero={!deck.learn}>{deck.learn}</span>
      <span class="num due" class:zero={!deck.review}>{deck.review}</span>
      <span class="actions">
        <button
          class="icon-btn"
          onclick={() => actions.startRename(deck)}
          aria-label="Rename {deck.full_name}"
          title="Rename"
        >
          <Icon name="pencil" size={16} />
        </button>
        <button
          class="icon-btn delete"
          onclick={() => actions.remove(deck)}
          aria-label="Delete {deck.full_name}"
          title="Delete"
        >
          <Icon name="trash" size={16} />
        </button>
      </span>
    {/if}
  </div>
  {#if deck.children.length && !deck.collapsed}
    <ul>
      {#each deck.children as child (child.id)}
        <DeckRow deck={child} depth={depth + 1} {actions} {renamingId} {highlightId} {dragSourceId} {dropTargetId} />
      {/each}
    </ul>
  {/if}
</li>

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: grid;
    grid-template-columns: 28px 1fr var(--num-col) var(--num-col) var(--num-col) var(--actions-col);
    align-items: center;
    padding: 0 var(--row-pad-right) 0 calc(8px + var(--depth) * var(--indent, 18px));
    border-top: 1px solid var(--border);
    min-height: 48px;
  }
  .row:hover:not(.renaming) {
    background: var(--surface-2);
  }
  .row {
    /* Rows can be dragged (pointer events): no text selection, and no link
       preview or menu on a long press. */
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }
  @media (hover: hover) {
    .row:not(.renaming) {
      cursor: grab;
    }
  }
  :global(body.deck-dragging) .row:hover:not(.drop-target) {
    background: none; /* only rows it can be dropped into light up */
  }
  .dragging {
    opacity: 0.45;
  }
  .row.drop-target,
  .row.drop-target:hover {
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 2px var(--accent);
  }
  .row.renaming {
    align-items: start;
  }
  .row.renaming > .toggle,
  .row.renaming > .toggle-space {
    margin-top: 12px; /* level with the name input */
  }
  .row.highlight {
    animation: flash 2.5s ease-out;
  }
  @keyframes flash {
    0%,
    40% {
      background: var(--accent-soft);
    }
    100% {
      background: transparent;
    }
  }
  .toggle {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: 0;
    border-radius: 6px;
    background: none;
    color: var(--muted);
    cursor: pointer;
  }
  .toggle:hover {
    background: var(--surface-3);
    color: var(--text);
  }
  .name {
    min-width: 0;
    padding: 13px 8px 13px 2px;
    color: var(--text);
    text-decoration: none;
    font-weight: 500;
    overflow-wrap: anywhere;
  }
  .name:hover {
    color: var(--accent);
  }
  .name.filtered {
    color: var(--accent);
  }
  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }
  .num.zero {
    color: var(--faint);
    font-weight: 400;
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
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 2px;
  }
  .actions .icon-btn {
    width: var(--action-size);
    height: var(--action-size);
  }
  .actions .delete:hover {
    background: var(--danger-soft);
    color: var(--danger);
  }

  /* Renaming: the form takes the place of the name, counts and actions. */
  .rename {
    grid-column: 2 / -1;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 7px 0 9px 2px;
  }
  .rename-row {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .rename-row input {
    flex: 1;
    min-width: 0;
    min-height: 36px;
    padding: 6px 10px;
  }
  .rename-row .save {
    color: var(--accent);
  }
  .rename .error-text,
  .hint {
    margin: 0;
    font-size: 0.85rem;
    overflow-wrap: anywhere;
  }
  .hint code {
    padding: 1px 5px;
    border-radius: 5px;
    background: var(--surface-3);
    color: var(--text);
    font-size: 0.8rem;
  }
</style>
