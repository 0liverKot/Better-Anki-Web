export interface DeckNode {
  id: number;
  name: string;
  new: number;
  learn: number;
  review: number;
  collapsed: boolean;
  filtered: boolean;
  children: DeckNode[];
}

export interface AvTag {
  kind: 'audio' | 'video' | 'tts' | 'unknown';
  file?: string;
  text?: string;
  lang?: string;
  speed?: number;
}

export interface ReviewCard {
  id: number;
  note_id: number;
  ord: number;
  queue: 'new' | 'learning' | 'review';
  deck_name: string;
  question: string;
  answer: string | null;
  type_answer: boolean;
  css: string;
  av: { q: AvTag[]; a: AvTag[] };
  autoplay: boolean;
  replay_question: boolean;
  buttons: string[];
  flag: number;
}

export interface NextPayload {
  deck: { id: number; name: string };
  counts: { new: number; learning: number; review: number };
  media_base: string;
  undo: string | null;
  undone?: string;
  card: ReviewCard | null;
}

export interface Notetype {
  id: number;
  name: string;
  is_cloze: boolean;
  fields: { name: string; sticky: boolean }[];
}

export interface DeckName {
  id: number;
  name: string;
}

export type SyncState =
  | 'logged_out'
  | 'idle'
  | 'syncing'
  | 'error'
  | 'full_sync_required'
  | 'auth_required';

export interface SyncStatus {
  logged_in: boolean;
  username: string | null;
  endpoint: string | null;
  state: SyncState;
  last_sync_at: number | null;
  last_error: string | null;
  server_message: string | null;
  full_sync: { suggested: 'upload' | 'download' | null } | null;
  media_syncing: boolean;
  media_error: string | null;
  local_changes: boolean;
}
