<script lang="ts">
  import { onMount } from 'svelte';
  import DeckRow from '../components/DeckRow.svelte';
  import Icon from '../components/Icon.svelte';
  import { api, errorMessage } from '../lib/api';
  import { onSynced, sync } from '../lib/sync.svelte';
  import { toast } from '../lib/toast.svelte';
  import type { DeckNode } from '../lib/types';

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
    return onSynced(load);
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
    <div class="head">
      <h1>Decks</h1>
      <span class="num-head new" title="New cards">New</span>
      <span class="num-head learn" title="Learning">Learn</span>
      <span class="num-head due" title="Due for review">Due</span>
    </div>
    {#if error}
      <p class="empty">{error} <button class="link" onclick={load}>Retry</button></p>
    {:else if !decks}
      <p class="empty muted">Loading…</p>
    {:else if decks.length === 0}
      <p class="empty muted">No decks yet.</p>
    {:else}
      <ul>
        {#each decks as deck (deck.id)}
          <DeckRow {deck} ontoggle={toggle} />
        {/each}
      </ul>
      <div class="total">
        <span>Total due today</span>
        <span class="num new">{totals.new}</span>
        <span class="num learn">{totals.learn}</span>
        <span class="num due">{totals.review}</span>
      </div>
    {/if}
  </div>
</section>

<style>
  .page {
    --num-col: 3.6em;
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
    grid-template-columns: 1fr var(--num-col) var(--num-col) var(--num-col);
    align-items: center;
    padding: 0 16px 0 16px;
  }
  .head {
    padding-top: 14px;
    padding-bottom: 10px;
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
