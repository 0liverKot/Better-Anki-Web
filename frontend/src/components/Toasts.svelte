<script lang="ts">
  import { toasts } from '../lib/toast.svelte';
</script>

<div class="toasts" aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast" class:error={t.kind === 'error'} role={t.kind === 'error' ? 'alert' : 'status'}>
      {t.message}
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    left: 50%;
    bottom: calc(88px + env(safe-area-inset-bottom));
    z-index: 100;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    width: min(92vw, 480px);
    transform: translateX(-50%);
    pointer-events: none;
  }
  .toast {
    padding: 10px 16px;
    border-radius: 10px;
    background: var(--toast-bg);
    color: var(--toast-text);
    box-shadow: var(--shadow);
    font-size: 0.925rem;
    text-align: center;
  }
  .toast.error {
    background: var(--danger);
    color: #fff;
  }
</style>
