import { api } from './api';
import type { SyncStatus } from './types';

export const sync = $state<{ status: SyncStatus | null }>({ status: null });

const events = new EventTarget();
let timer: ReturnType<typeof setTimeout> | undefined;
let started = false;

/** Run `callback` whenever a sync finishes (so pages can reload their data). */
export function onSynced(callback: () => void): () => void {
  events.addEventListener('synced', callback);
  return () => events.removeEventListener('synced', callback);
}

function update(next: SyncStatus): void {
  const wasSyncing = sync.status?.state === 'syncing';
  sync.status = next;
  if (wasSyncing && next.state !== 'syncing') {
    events.dispatchEvent(new Event('synced'));
  }
  schedule();
}

function schedule(): void {
  if (!started) return;
  clearTimeout(timer);
  const busy = sync.status?.state === 'syncing' || sync.status?.media_syncing;
  timer = setTimeout(refreshSyncStatus, busy ? 1200 : 15000);
}

export async function refreshSyncStatus(): Promise<void> {
  try {
    update(await api<SyncStatus>('/api/sync/status'));
  } catch {
    schedule();
  }
}

/** Start a sync. With maxAge, only if the last one is older than that many seconds. */
export async function syncNow(maxAge?: number): Promise<void> {
  if (!sync.status?.logged_in) return;
  const query = maxAge === undefined ? '' : `?max_age=${maxAge}`;
  update(await api<SyncStatus>(`/api/sync${query}`, { method: 'POST' }));
}

export function setSyncStatus(next: SyncStatus): void {
  update(next);
}

/** Begin polling, sync when the app opens, and push changes when the tab is hidden. */
export function startSync(): void {
  if (started) return;
  started = true;
  refreshSyncStatus().then(() => syncNow(60).catch(() => {}));
}

document.addEventListener('visibilitychange', () => {
  if (!started) return;
  if (document.visibilityState === 'hidden') {
    api('/api/sync/soon', { method: 'POST', keepalive: true }).catch(() => {});
  } else {
    refreshSyncStatus().then(() => syncNow(120).catch(() => {}));
  }
});

export function stopSync(): void {
  started = false;
  clearTimeout(timer);
}
