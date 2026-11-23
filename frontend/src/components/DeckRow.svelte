<script lang="ts">
  import Icon from './Icon.svelte';
  import DeckRow from './DeckRow.svelte';
  import type { DeckNode } from '../lib/types';

  interface Props {
    deck: DeckNode;
    depth?: number;
    ontoggle: (deck: DeckNode) => void;
  }
  let { deck, depth = 0, ontoggle }: Props = $props();
</script>

<li>
  <div class="row" style="--depth: {depth}">
    {#if deck.children.length}
      <button
        class="toggle"
        onclick={() => ontoggle(deck)}
        aria-label={deck.collapsed ? `Expand ${deck.name}` : `Collapse ${deck.name}`}
        aria-expanded={!deck.collapsed}
      >
        <Icon name={deck.collapsed ? 'chevronRight' : 'chevronDown'} size={16} />
      </button>
    {:else}
      <span class="toggle-space"></span>
    {/if}
    <a class="name" class:filtered={deck.filtered} href="#/review/{deck.id}">{deck.name}</a>
    <span class="num new" class:zero={!deck.new}>{deck.new}</span>
    <span class="num learn" class:zero={!deck.learn}>{deck.learn}</span>
    <span class="num due" class:zero={!deck.review}>{deck.review}</span>
  </div>
  {#if deck.children.length && !deck.collapsed}
    <ul>
      {#each deck.children as child (child.id)}
        <DeckRow deck={child} depth={depth + 1} {ontoggle} />
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
    grid-template-columns: 28px 1fr var(--num-col) var(--num-col) var(--num-col);
    align-items: center;
    padding: 0 16px 0 calc(8px + var(--depth) * 18px);
    border-top: 1px solid var(--border);
    min-height: 48px;
  }
  .row:hover {
    background: var(--surface-2);
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
</style>
