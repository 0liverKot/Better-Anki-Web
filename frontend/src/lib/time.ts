/** "just now", "5 min ago", "3 h ago", "2 days ago" for a Unix timestamp in seconds. */
export function timeAgo(seconds: number): string {
  const diff = Math.max(0, Date.now() / 1000 - seconds);
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  const days = Math.round(diff / 86400);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}
