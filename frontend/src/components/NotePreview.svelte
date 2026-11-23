<script lang="ts">
  import CardFrame from './CardFrame.svelte';
  import type { FrameOptions } from '../lib/cardFrame';
  import type { NoteDetail, PreviewCard } from '../lib/types';

  let { detail, onedit }: { detail: NoteDetail; onedit?: () => void } = $props();

  let cardIndex = $state(0);
  let side = $state<'q' | 'a'>('q');
  const night = matchMedia('(prefers-color-scheme: dark)').matches;

  const card = $derived(detail.cards[cardIndex] ?? detail.cards[0]);
  const options = $derived.by((): FrameOptions | null => {
    if (!card) return null;
    return {
      html: side === 'q' ? card.question : card.answer,
      css: card.css,
      ord: card.ord,
      mediaBase: new URL(detail.media_base, location.origin).href,
      av: card.av,
      side,
      autoplay: false,
      replayQuestion: card.replay_question,
      night,
    };
  });

  function plural(n: number, word: string): string {
    return `${n} ${word}${n === 1 ? '' : 's'}`;
  }

  function describe(c: PreviewCard): string {
    if (c.state === 'new') return 'New';
    if (c.state === 'learning') return 'Learning';
    const parts: string[] = [];
    if (c.state === 'suspended') parts.push('Suspended');
    if (c.state === 'buried') parts.push('Buried');
    if (c.due_in_days !== null) {
      const d = c.due_in_days;
      parts.push(d === 0 ? 'Due today' : d > 0 ? `Due in ${plural(d, 'day')}` : `Overdue by ${plural(-d, 'day')}`);
    }
    if (c.interval_days) parts.push(`interval ${plural(c.interval_days, 'day')}`);
    return parts.join(', ') || c.state;
  }
</script>

<div class="preview">
  {#if detail.cards.length > 1}
    <div class="tabs" role="tablist" aria-label="Cards of this note">
      {#each detail.cards as c, i (c.id)}
        <button
          role="tab"
          aria-selected={i === cardIndex}
          class:active={i === cardIndex}
          onclick={() => {
            cardIndex = i;
            side = 'q';
          }}
        >
          {c.name}
        </button>
      {/each}
    </div>
  {/if}

  <div class="frame">
    {#if options}
      <CardFrame {options} onkey={() => {}} ontyped={() => {}} onsubmit={() => {}} />
    {:else}
      <p class="muted empty">This note has no cards.</p>
    {/if}
  </div>

  {#if card}
    <div class="bar">
      <div class="segmented" role="group" aria-label="Side">
        <button class:active={side === 'q'} onclick={() => (side = 'q')}>Question</button>
        <button class:active={side === 'a'} onclick={() => (side = 'a')}>Answer</button>
      </div>
      {#if onedit}
        <button class="btn small edit-btn" onclick={onedit} title="Edit this note">Edit</button>
      {/if}
      <div class="info">
        <span>{card.deck}</span>
        <span class="dot">·</span>
        <span>{describe(card)}</span>
        {#if card.reviews}
          <span class="dot">·</span>
          <span>{plural(card.reviews, 'review')}{card.lapses ? `, ${plural(card.lapses, 'lapse')}` : ''}</span>
        {/if}
      </div>
    </div>
  {/if}

  <details class="fields">
    <summary>Fields{detail.note.tags.length ? ' and tags' : ''}</summary>
    <dl>
      {#each detail.note.fields as field (field.name)}
        <dt>{field.name}</dt>
        <dd>{field.text || '—'}</dd>
      {/each}
      {#if detail.note.tags.length}
        <dt>Tags</dt>
        <dd class="tags">
          {#each detail.note.tags as tag (tag)}<span class="tag">{tag}</span>{/each}
        </dd>
      {/if}
    </dl>
  </details>
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px 16px;
    border-top: 1px dashed var(--border);
    background: var(--surface-2);
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .tabs button,
  .segmented button {
    height: 30px;
    padding: 0 12px;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--muted);
    font: inherit;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
  }
  .tabs button {
    border-radius: 999px;
  }
  .tabs button.active,
  .segmented button.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }
  .frame {
    height: min(46vh, 360px);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--surface);
  }
  .empty {
    padding: 16px;
    margin: 0;
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 14px;
  }
  .segmented {
    display: inline-flex;
  }
  .segmented button:first-child {
    border-radius: 8px 0 0 8px;
  }
  .segmented button:last-child {
    margin-left: -1px;
    border-radius: 0 8px 8px 0;
  }
  .edit-btn {
    order: 3;
    margin-left: auto;
  }
  .info {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    color: var(--muted);
    font-size: 0.85rem;
  }
  .dot {
    color: var(--faint);
  }
  .fields summary {
    color: var(--muted);
    font-size: 0.85rem;
    cursor: pointer;
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 14px;
    margin: 10px 0 0;
    font-size: 0.9rem;
  }
  dt {
    color: var(--muted);
    font-weight: 600;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    padding: 1px 8px;
    border-radius: 999px;
    background: var(--surface-3);
    font-size: 0.8rem;
  }
  @media (max-width: 520px) {
    dl {
      grid-template-columns: 1fr;
      gap: 2px;
    }
    dd {
      margin-bottom: 6px;
    }
  }
</style>
