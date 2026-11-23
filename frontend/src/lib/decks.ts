import { api, ApiError } from './api';
import type { DeckName } from './types';

/**
 * Create a deck ("Parent::Child" makes a subdeck). If a deck with that name already
 * exists (names are case-insensitive), returns it with `existed: true` instead.
 */
export async function createDeck(name: string): Promise<{ deck: DeckName; existed: boolean }> {
  try {
    return { deck: await api<DeckName>('/api/decks', { body: { name } }), existed: false };
  } catch (err) {
    if (err instanceof ApiError && err.status === 409 && err.data?.id) {
      return { deck: { id: err.data.id, name: err.data.name }, existed: true };
    }
    throw err;
  }
}
