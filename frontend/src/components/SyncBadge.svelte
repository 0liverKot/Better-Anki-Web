<script lang="ts">
  import Icon, { type IconName } from './Icon.svelte';
  import { errorMessage } from '../lib/api';
  import { go } from '../lib/router.svelte';
  import { sync, syncNow } from '../lib/sync.svelte';
  import { timeAgo } from '../lib/time';
  import { toast } from '../lib/toast.svelte';

  interface View {
    label: string;
    icon: IconName;
    tone: 'muted' | 'ok' | 'accent' | 'warn' | 'error';
    spin?: boolean;
    action: 'sync' | 'settings' | 'none';
  }

  const view = $derived.by((): View => {
    const s = sync.status;
    if (!s) return { label: 'Sync', icon: 'sync', tone: 'muted', action: 'none' };
    if (s.state === 'syncing') return { label: 'Syncing', icon: 'sync', tone: 'muted', spin: true, action: 'none' };
    if (!s.logged_in && s.state !== 'auth_required') {
      return { label: 'Connect', icon: 'cloudOff', tone: 'warn', action: 'settings' };
    }
    if (s.state === 'auth_required') return { label: 'Log in', icon: 'alert', tone: 'warn', action: 'settings' };
    if (s.state === 'full_sync_required') return { label: 'Action needed', icon: 'alert', tone: 'warn', action: 'settings' };
    if (s.state === 'error') return { label: 'Retry sync', icon: 'alert', tone: 'error', action: 'sync' };
    if (s.media_syncing) return { label: 'Media', icon: 'sync', tone: 'muted', spin: true, action: 'none' };
    if (s.local_changes) return { label: 'Sync', icon: 'sync', tone: 'accent', action: 'sync' };
    return { label: 'Synced', icon: 'check', tone: 'ok', action: 'sync' };
  });

  const title = $derived.by(() => {
    const s = sync.status;
    if (!s) return '';
    if (s.state === 'error' && s.last_error) return `Last sync failed: ${s.last_error}`;
    if (s.last_sync_at) return `Last synced ${timeAgo(s.last_sync_at)}. Click to sync now.`;
    return s.logged_in ? 'Click to sync now' : 'Connect AnkiWeb in Settings';
  });

  async function onclick(): Promise<void> {
    if (view.action === 'settings') go('/settings');
    else if (view.action === 'sync') {
      try {
        await syncNow();
      } catch (err) {
        toast(errorMessage(err), 'error');
      }
    }
  }
</script>

<button class="badge {view.tone}" {onclick} {title} disabled={view.action === 'none'}>
  <Icon name={view.icon} size={16} spin={view.spin} />
  <span class="label">{view.label}</span>
</button>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 34px;
    padding: 0 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface);
    color: var(--muted);
    font: inherit;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
  }
  .badge:disabled {
    cursor: default;
  }
  .badge:hover:not(:disabled) {
    background: var(--surface-2);
  }
  .ok {
    color: var(--ok);
  }
  .accent {
    color: var(--accent);
    border-color: var(--accent-border);
  }
  .warn {
    color: var(--warn);
    border-color: var(--warn-border);
  }
  .error {
    color: var(--danger);
    border-color: var(--danger-border);
  }
  @media (max-width: 420px) {
    .label {
      display: none;
    }
    .badge {
      width: 34px;
      padding: 0;
      justify-content: center;
    }
  }
</style>
