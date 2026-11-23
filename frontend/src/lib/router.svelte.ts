export type Route =
  | { name: 'decks' }
  | { name: 'review'; deckId: number }
  | { name: 'add' }
  | { name: 'search' }
  | { name: 'settings' };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('?')[0].split('/');
  if (parts[0] === 'review' && /^\d+$/.test(parts[1] ?? '')) {
    return { name: 'review', deckId: Number(parts[1]) };
  }
  if (parts[0] === 'add') return { name: 'add' };
  if (parts[0] === 'search') return { name: 'search' };
  if (parts[0] === 'settings') return { name: 'settings' };
  return { name: 'decks' };
}

export const router = $state<{ route: Route }>({ route: parse(location.hash) });

window.addEventListener('hashchange', () => {
  router.route = parse(location.hash);
});

export function go(path: string): void {
  location.hash = path;
}
