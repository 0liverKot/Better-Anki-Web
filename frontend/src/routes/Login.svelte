<script lang="ts">
  import { api, errorMessage } from '../lib/api';
  import { session } from '../lib/session.svelte';

  let password = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      await api('/api/auth/login', { body: { password } });
      session.authenticated = true;
    } catch (err) {
      error = errorMessage(err);
      password = '';
    } finally {
      busy = false;
    }
  }
</script>

<main class="wrap">
  <form class="card" onsubmit={submit}>
    <img src="/favicon.svg" alt="" width="48" height="48" />
    <h1>Better Anki</h1>
    <p class="muted">Enter your app password to continue.</p>
    <!-- svelte-ignore a11y_autofocus -->
    <input
      type="password"
      bind:value={password}
      placeholder="Password"
      autocomplete="current-password"
      aria-label="Password"
      required
      autofocus
    />
    {#if error}<p class="error-text">{error}</p>{/if}
    <button class="btn primary" type="submit" disabled={busy || !password}>
      {busy ? 'Signing in…' : 'Sign in'}
    </button>
  </form>
</main>

<style>
  .wrap {
    display: grid;
    place-items: center;
    min-height: 100vh;
    min-height: 100dvh;
    padding: 16px;
  }
  .card {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    width: 100%;
    max-width: 360px;
    padding: 28px 24px;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: var(--surface);
    box-shadow: var(--shadow);
    text-align: center;
  }
  img {
    align-self: center;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
  }
  p {
    margin: 0 0 4px;
  }
</style>
