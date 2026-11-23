<script lang="ts">
  import { onMount } from 'svelte';
  import CardFrame, { type KeyInfo } from '../components/CardFrame.svelte';
  import Icon from '../components/Icon.svelte';
  import { api, ApiError, errorMessage } from '../lib/api';
  import type { FrameOptions } from '../lib/cardFrame';
  import { go } from '../lib/router.svelte';
  import { toast } from '../lib/toast.svelte';
  import type { NextPayload } from '../lib/types';

  let { deckId }: { deckId: number } = $props();

  let data = $state<NextPayload | null>(null);
  let side = $state<'q' | 'a'>('q');
  let answerHtml = $state<string | null>(null);
  let busy = $state(false);
  let loadError = $state<string | null>(null);
  let frame: ReturnType<typeof CardFrame> | undefined = $state();
  let typed = '';
  let shownAt = 0;

  const dark = matchMedia('(prefers-color-scheme: dark)');
  let night = $state(dark.matches);

  const RATINGS = [
    { label: 'Again', cls: 'again' },
    { label: 'Hard', cls: 'hard' },
    { label: 'Good', cls: 'good' },
    { label: 'Easy', cls: 'easy' },
  ];

  const card = $derived(data?.card ?? null);
  const frameOptions = $derived.by((): FrameOptions | null => {
    if (!data || !card) return null;
    return {
      html: side === 'q' ? card.question : (answerHtml ?? ''),
      css: card.css,
      ord: card.ord,
      mediaBase: new URL(data.media_base, location.origin).href,
      av: card.av,
      side,
      autoplay: card.autoplay,
      replayQuestion: card.replay_question,
      night,
    };
  });

  function present(next: NextPayload): void {
    data = next;
    side = 'q';
    answerHtml = next.card?.answer ?? null;
    typed = '';
    shownAt = performance.now();
  }

  async function load(): Promise<void> {
    loadError = null;
    try {
      present(await api<NextPayload>(`/api/review/${deckId}/next`));
    } catch (err) {
      loadError = errorMessage(err);
    }
  }

  onMount(() => {
    load();
    const onScheme = (e: MediaQueryListEvent) => (night = e.matches);
    dark.addEventListener('change', onScheme);
    return () => dark.removeEventListener('change', onScheme);
  });

  async function showAnswer(): Promise<void> {
    if (!card || side !== 'q' || busy) return;
    if (card.type_answer) {
      busy = true;
      try {
        const res = await api<{ answer: string }>('/api/review/type-answer', {
          body: { card_id: card.id, typed },
        });
        answerHtml = res.answer;
      } catch (err) {
        toast(errorMessage(err), 'error');
        return;
      } finally {
        busy = false;
      }
    }
    side = 'a';
  }

  async function answer(rating: number): Promise<void> {
    if (!card || side !== 'a' || busy) return;
    busy = true;
    const elapsed = Math.round(performance.now() - shownAt);
    try {
      present(
        await api<NextPayload>('/api/review/answer', {
          body: { deck_id: deckId, card_id: card.id, rating, time_taken_ms: elapsed },
        }),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast('Cards changed after a sync, so here is the next one.');
        await load();
      } else {
        toast(errorMessage(err), 'error');
      }
    } finally {
      busy = false;
    }
  }

  async function undo(): Promise<void> {
    if (!data?.undo || busy) return;
    busy = true;
    try {
      const next = await api<NextPayload>('/api/review/undo', { body: { deck_id: deckId } });
      present(next);
      if (next.undone) toast(`Undid: ${next.undone}`);
    } catch (err) {
      toast(errorMessage(err), 'error');
    } finally {
      busy = false;
    }
  }

  function handleKey(k: KeyInfo): void {
    if (k.ctrlKey || k.metaKey) {
      if (k.key.toLowerCase() === 'z') undo();
      return;
    }
    if (k.altKey) return;
    switch (k.key) {
      case ' ':
      case 'Enter':
        if (side === 'q') showAnswer();
        else answer(3);
        break;
      case '1':
      case '2':
      case '3':
      case '4':
        if (side === 'a') answer(Number(k.key));
        break;
      case 'z':
        undo();
        break;
      case 'r':
      case 'R':
      case 'F5':
        frame?.replay();
        break;
      case 'Escape':
        go('/');
        break;
    }
  }

  function onWindowKey(e: KeyboardEvent): void {
    const target = e.target as HTMLElement | null;
    if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) {
      return;
    }
    const handled = [' ', 'Enter', '1', '2', '3', '4', 'z', 'r', 'R', 'F5', 'Escape'];
    if (handled.includes(e.key) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z')) {
      // Stops a focused button from also "clicking" on Space/Enter.
      e.preventDefault();
    }
    handleKey(e);
  }
</script>

<svelte:window onkeydown={onWindowKey} />

<div class="review">
  <header class="bar">
    <button class="icon-btn" onclick={() => go('/')} aria-label="Back to decks" title="Decks (Esc)">
      <Icon name="back" />
    </button>
    <div class="title" title={card?.deck_name ?? data?.deck.name}>
      {card?.deck_name ?? data?.deck.name ?? ''}
    </div>
    {#if data}
      <div class="counts" aria-label="Cards left">
        <span class="count new" class:current={card?.queue === 'new'} title="New">{data.counts.new}</span>
        <span class="count learn" class:current={card?.queue === 'learning'} title="Learning">
          {data.counts.learning}
        </span>
        <span class="count due" class:current={card?.queue === 'review'} title="To review">
          {data.counts.review}
        </span>
      </div>
    {/if}
    {#if card && (card.av.q.length || card.av.a.length)}
      <button class="icon-btn" onclick={() => frame?.replay()} aria-label="Replay audio" title="Replay audio (R)">
        <Icon name="volume" />
      </button>
    {/if}
    <button
      class="icon-btn"
      onclick={undo}
      disabled={!data?.undo || busy}
      aria-label="Undo"
      title={data?.undo ? `Undo ${data.undo} (Z)` : 'Nothing to undo'}
    >
      <Icon name="undo" />
    </button>
  </header>

  <main class="stage">
    {#if loadError}
      <div class="message">
        <p>{loadError}</p>
        <button class="btn" onclick={load}>Try again</button>
      </div>
    {:else if !data}
      <div class="message muted">Loading…</div>
    {:else if !card || !frameOptions}
      <div class="message">
        <div class="done-mark"><Icon name="check" size={28} /></div>
        <h2>All done for now</h2>
        <p class="muted">You've finished the cards due in this deck.</p>
        <div class="row">
          <button class="btn primary" onclick={() => go('/')}>Back to decks</button>
          {#if data.undo}
            <button class="btn" onclick={undo}>Undo last answer</button>
          {/if}
        </div>
      </div>
    {:else}
      <CardFrame
        bind:this={frame}
        options={frameOptions}
        focusTyping={card.type_answer && side === 'q'}
        onkey={handleKey}
        ontyped={(value) => (typed = value)}
        onsubmit={(value) => {
          typed = value;
          showAnswer();
        }}
      />
    {/if}
  </main>

  {#if card}
    <footer class="answer-bar">
      {#if side === 'q'}
        <button class="show" onclick={showAnswer} disabled={busy}>Show answer</button>
      {:else}
        <div class="ratings">
          {#each RATINGS as rating, i (rating.label)}
            <button class="rate {rating.cls}" onclick={() => answer(i + 1)} disabled={busy} title="{rating.label} ({i + 1})">
              <span class="ivl">{card.buttons[i]}</span>
              <span class="label">{rating.label}</span>
            </button>
          {/each}
        </div>
      {/if}
    </footer>
  {/if}
</div>

<style>
  .review {
    position: fixed;
    inset: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    padding-top: max(8px, env(safe-area-inset-top));
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .title {
    flex: 1;
    min-width: 0;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .counts {
    display: flex;
    gap: 10px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    margin-right: 4px;
  }
  .count {
    padding-bottom: 1px;
    border-bottom: 2px solid transparent;
  }
  .count.current {
    border-bottom-color: currentColor;
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
  .stage {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  .message {
    max-width: 420px;
    margin: 12vh auto 0;
    padding: 0 16px;
    text-align: center;
  }
  .message h2 {
    margin: 12px 0 4px;
    font-size: 1.3rem;
  }
  .done-mark {
    display: inline-grid;
    place-items: center;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--ok-soft);
    color: var(--ok);
  }
  .row {
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
    margin-top: 20px;
  }
  .answer-bar {
    padding: 10px 12px;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    background: var(--surface);
  }
  .show,
  .ratings {
    max-width: 560px;
    margin: 0 auto;
  }
  .show {
    display: block;
    width: 100%;
    min-height: 52px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-weight: 600;
    font-size: 1.05rem;
    cursor: pointer;
  }
  .show:hover:not(:disabled) {
    background: var(--surface-3);
  }
  .ratings {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }
  .rate {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    min-height: 52px;
    border: 0;
    border-radius: var(--radius);
    color: #fff;
    font: inherit;
    cursor: pointer;
  }
  .rate:disabled {
    opacity: 0.6;
  }
  .rate:hover:not(:disabled) {
    filter: brightness(1.08);
  }
  .ivl {
    font-size: 0.78rem;
    opacity: 0.9;
  }
  .label {
    font-weight: 600;
  }
  .again {
    background: var(--again);
  }
  .hard {
    background: var(--hard);
  }
  .good {
    background: var(--good);
  }
  .easy {
    background: var(--easy);
  }
</style>
