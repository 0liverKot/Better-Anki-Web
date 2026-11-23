export interface Toast {
  id: number;
  message: string;
  kind: 'info' | 'error';
}

export const toasts = $state<Toast[]>([]);
let nextId = 1;

export function toast(message: string, kind: Toast['kind'] = 'info', ms = 2600): void {
  const id = nextId++;
  toasts.push({ id, message, kind });
  setTimeout(() => {
    const index = toasts.findIndex((t) => t.id === id);
    if (index >= 0) toasts.splice(index, 1);
  }, ms);
}
