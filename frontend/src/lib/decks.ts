import { api, ApiError } from './api';
import type { DeckInfo, DeckName } from './types';

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

/** Rename a deck; "Parent::Child" moves it (with its subdecks) under Parent. */
export function renameDeck(id: number, name: string): Promise<DeckName> {
  return api<DeckName>(`/api/decks/${id}`, { method: 'PUT', body: { name } });
}

/** Make a deck (with its subdecks) a subdeck of another deck, or top-level with null. */
export function moveDeck(id: number, parentId: number | null): Promise<DeckName & { changed: boolean }> {
  return api(`/api/decks/${id}/move`, { body: { parent_id: parentId } });
}

export function deckInfo(id: number): Promise<DeckInfo> {
  return api<DeckInfo>(`/api/decks/${id}`);
}

/** Delete a deck with its subdecks and cards (a filtered deck's cards go back home). */
export function deleteDeck(id: number): Promise<{ name: string; cards_deleted: number }> {
  return api(`/api/decks/${id}`, { method: 'DELETE' });
}
