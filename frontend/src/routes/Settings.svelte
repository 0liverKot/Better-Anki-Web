<script lang="ts">
  import Icon from '../components/Icon.svelte';
  import { api, errorMessage } from '../lib/api';
  import { session } from '../lib/session.svelte';
  import { refreshSyncStatus, setSyncStatus, stopSync, sync, syncNow } from '../lib/sync.svelte';
  import { timeAgo } from '../lib/time';
  import { toast } from '../lib/toast.svelte';
  import type { SyncStatus } from '../lib/types';

  let username = $state('');
  let password = $state('');
  let endpoint = $state('');
  let showAdvanced = $state(false);
  let busy = $state(false);
  let formError = $state<string | null>(null);

  const status = $derived(sync.status);
  const serverName = $derived(status?.endpoint ? status.endpoint : 'AnkiWeb');

  $effect(() => {
    // Prefill after AnkiWeb rejected the saved login.
    if (status?.username && !username) username = status.username;
  });

  async function login(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    formError = null;
    try {
      setSyncStatus(
        await api<SyncStatus>('/api/sync/login', {
          body: { username, password, endpoint: endpoint.trim() || null },
        }),
      );
      password = '';
      toast('Connected. Syncing your collection…');
    } catch (err) {
      formError = errorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function logoutSync(): Promise<void> {
    if (!confirm(`Disconnect from ${serverName}? Your cards stay on this server, but stop syncing.`)) return;
    setSyncStatus(await api<SyncStatus>('/api/sync/logout', { method: 'POST' }));
  }

  async function fullSync(direction: 'upload' | 'download'): Promise<void> {
    const message =
      direction === 'download'
        ? `Replace this server's copy with the one on ${serverName}? Changes made here since the last sync will be lost.`
        : `Replace the copy on ${serverName} with this server's copy? Changes made on other devices since the last sync will be lost, and they will need to download it again.`;
    if (!confirm(message)) return;
    busy = true;
    try {
      setSyncStatus(await api<SyncStatus>('/api/sync/full', { body: { direction } }));
      if (sync.status?.state === 'idle') toast('Full sync finished.');
    } catch (err) {
      toast(errorMessage(err), 'error');
    } finally {
      busy = false;
    }
  }

  async function syncClicked(): Promise<void> {
    try {
      await syncNow();
    } catch (err) {
      toast(errorMessage(err), 'error');
    }
  }

  async function logoutApp(): Promise<void> {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    stopSync();
    session.authenticated = false;
  }
</script>

<section class="page">
  <h1>Settings</h1>

  <div class="panel">
    <h2>Sync</h2>
    {#if !status}
      <p class="muted">Loading…</p>
    {:else if status.logged_in}
      <div class="kv">
        <span class="muted">Connected to</span>
        <span><strong>{serverName}</strong> as {status.username}</span>
        <span class="muted">Last sync</span>
        <span>
          {#if status.state === 'syncing'}
            Syncing now…
          {:else if status.last_sync_at}
            {timeAgo(status.last_sync_at)}
          {:else}
            Not yet
          {/if}
        </span>
        {#if status.media_syncing}
          <span class="muted">Media</span>
          <span>Syncing images and audio…</span>
        {/if}
      </div>

      {#if status.state === 'full_sync_required'}
        <div class="callout warn">
          <div class="callout-title"><Icon name="alert" /> A one-way sync is needed</div>
          <p>
            {#if status.full_sync?.suggested === 'upload'}
              {serverName} has no cards yet, but this server does. Upload this server's collection to
              {serverName} to start syncing.
            {:else}
              This server's collection and the one on {serverName} can't be merged. This usually
              happens when cards were added here before connecting, or after a note type was edited.
              Pick the copy to keep. If you mostly study on your phone or desktop, choose
              <strong>Download</strong>.
            {/if}
          </p>
          <div class="row">
            <button class="btn" class:primary={status.full_sync?.suggested !== 'upload'} disabled={busy} onclick={() => fullSync('download')}>
              Download from {serverName}
            </button>
            <button class="btn" class:primary={status.full_sync?.suggested === 'upload'} disabled={busy} onclick={() => fullSync('upload')}>
              Upload to {serverName}
            </button>
          </div>
        </div>
      {/if}

      {#if status.state === 'error' && status.last_error}
        <div class="callout error"><Icon name="alert" /> <span>Last sync failed: {status.last_error}</span></div>
      {/if}
      {#if status.media_error}
        <div class="callout error"><Icon name="alert" /> <span>Media sync failed: {status.media_error}</span></div>
      {/if}
      {#if status.server_message}
        <div class="callout"><span>Message from {serverName}: {status.server_message}</span></div>
      {/if}

      <div class="row">
        <button class="btn primary" onclick={syncClicked} disabled={status.state === 'syncing' || status.state === 'full_sync_required'}>
          <Icon name="sync" size={16} spin={status.state === 'syncing'} /> Sync now
        </button>
        <button class="btn" onclick={logoutSync}>Disconnect</button>
      </div>
      <p class="note muted">
        This server syncs on its own: within a minute of your last change, when you leave the page,
        and every 10 minutes to pick up changes from your other devices.
      </p>
    {:else}
      {#if status.state === 'auth_required'}
        <div class="callout warn">
          <Icon name="alert" />
          <span>{status.last_error ?? 'Your login expired.'} Log in again to resume syncing.</span>
        </div>
      {:else}
        <p>
          Connect your AnkiWeb account to download your collection here and keep it in sync with Anki
          on your phone and computer.
        </p>
      {/if}
      <form class="form" onsubmit={login}>
        <label>
          <span>{showAdvanced ? 'Username' : 'AnkiWeb email'}</span>
          <input
            type="text"
            inputmode="email"
            bind:value={username}
            autocomplete="username"
            autocapitalize="off"
            spellcheck="false"
            required
          />
        </label>
        <label>
          <span>AnkiWeb password</span>
          <input type="password" bind:value={password} autocomplete="current-password" required />
        </label>
        {#if showAdvanced}
          <label>
            <span>Self-hosted sync server (leave blank for AnkiWeb)</span>
            <input type="url" bind:value={endpoint} placeholder="https://sync.example.com/" />
          </label>
        {/if}
        {#if formError}<p class="error-text">{formError}</p>{/if}
        <div class="row">
          <button class="btn primary" type="submit" disabled={busy}>{busy ? 'Connecting…' : 'Connect'}</button>
          <button class="link" type="button" onclick={() => (showAdvanced = !showAdvanced)}>
            {showAdvanced ? 'Hide' : 'Use a self-hosted sync server'}
          </button>
        </div>
        <p class="note muted">
          Your password is only used once to get a sync key from AnkiWeb, and it isn't stored. The
          first sync downloads your whole collection, which can take a while if you have lots of
          media.
        </p>
      </form>
    {/if}
  </div>

  <div class="panel">
    <h2>Keyboard shortcuts</h2>
    <div class="kv shortcuts">
      <span><kbd>Space</kbd> / <kbd>Enter</kbd></span><span>Show answer, then answer Good</span>
      <span><kbd>1</kbd>–<kbd>4</kbd></span><span>Again, Hard, Good, Easy</span>
      <span><kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Z</kbd></span><span>Undo</span>
      <span><kbd>R</kbd></span><span>Replay audio</span>
      <span><kbd>Esc</kbd></span><span>Back to decks</span>
      <span><kbd>Ctrl</kbd>+<kbd>Enter</kbd></span><span>Add card</span>
      <span><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>C</kbd></span><span>Cloze deletion (add <kbd>Alt</kbd> to reuse the number)</span>
    </div>
  </div>

  <div class="panel">
    <h2>This app</h2>
    <div class="row">
      <button class="btn" onclick={logoutApp}><Icon name="logout" size={16} /> Log out</button>
      <button class="btn" onclick={refreshSyncStatus}>Refresh status</button>
    </div>
  </div>
</section>

<style>
  .page {
    max-width: 760px;
    margin: 0 auto;
    padding: 20px 16px 64px;
  }
  h1 {
    margin: 0 0 16px;
    font-size: 1.25rem;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-bottom: 16px;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }
  h2 {
    margin: 0;
    font-size: 1rem;
  }
  p {
    margin: 0;
    line-height: 1.5;
  }
  .kv {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 8px 16px;
    align-items: baseline;
  }
  .shortcuts {
    font-size: 0.925rem;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .note {
    font-size: 0.875rem;
  }
  .form {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-width: 420px;
  }
  .form label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted);
  }
  .callout {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-2);
  }
  .callout.warn {
    border-color: var(--warn-border);
    background: var(--warn-soft);
  }
  .callout.error {
    flex-direction: row;
    align-items: center;
    border-color: var(--danger-border);
    background: var(--danger-soft);
  }
  .callout-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }
  kbd {
    display: inline-block;
    min-width: 1.4em;
    padding: 1px 6px;
    border: 1px solid var(--border-strong);
    border-bottom-width: 2px;
    border-radius: 5px;
    background: var(--surface-2);
    font-family: inherit;
    font-size: 0.8rem;
    text-align: center;
  }
  @media (max-width: 520px) {
    .kv {
      grid-template-columns: 1fr;
      gap: 2px;
    }
    .kv > span:nth-child(even) {
      margin-bottom: 8px;
    }
  }
</style>
