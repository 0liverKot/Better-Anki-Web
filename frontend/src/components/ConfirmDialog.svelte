<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    open: boolean;
    title: string;
    confirmLabel: string;
    /** Red confirm button, for things that can't be undone. */
    danger?: boolean;
    /** Confirm is disabled (e.g. while details are loading or the action runs). */
    disabled?: boolean;
    onconfirm: () => void;
    oncancel: () => void;
    children: Snippet;
  }
  let { open, title, confirmLabel, danger = false, disabled = false, onconfirm, oncancel, children }: Props =
    $props();

  let dialog: HTMLDialogElement | undefined = $state();
  let cancelButton: HTMLButtonElement | undefined = $state();

  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      // Start on Cancel so a stray Enter doesn't confirm something destructive.
      cancelButton?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  function onDialogCancel(event: Event): void {
    // Esc: let the parent decide (it closes the dialog by setting `open`).
    event.preventDefault();
    oncancel();
  }

  function onBackdropClick(event: MouseEvent): void {
    // Clicks on the backdrop land on the <dialog> itself, outside its content box.
    if (event.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    const inside = event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
    if (!inside) oncancel();
  }
</script>

<dialog bind:this={dialog} aria-labelledby="confirm-title" oncancel={onDialogCancel} onclick={onBackdropClick}>
  <h2 id="confirm-title">{title}</h2>
  <div class="body">{@render children()}</div>
  <div class="actions">
    <button class="btn" bind:this={cancelButton} onclick={oncancel}>Cancel</button>
    <button class="btn" class:danger class:primary={!danger} {disabled} onclick={onconfirm}>{confirmLabel}</button>
  </div>
</dialog>

<style>
  dialog {
    width: min(440px, calc(100vw - 32px));
    padding: 20px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 18px 50px rgba(0, 0, 0, 0.25);
  }
  dialog::backdrop {
    background: rgba(10, 14, 22, 0.5);
  }
  h2 {
    margin: 0 0 10px;
    font-size: 1.1rem;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }
  .body {
    line-height: 1.5;
  }
  .body :global(p) {
    margin: 0 0 10px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 18px;
  }
  @media (max-width: 480px) {
    .actions .btn {
      flex: 1;
    }
  }
</style>
