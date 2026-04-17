/**
 * Phase MC — dedup helpers for the Mission Critical tab.
 *
 * Two concerns:
 *   1. Root-cause collapse: if the backend marked `root_cause` on a
 *      tile, the UI hides the dependent tile from the main grid and
 *      lists it inside the root's "Affected by" section instead.
 *   2. Algorithms group collapse: when all `group === 'algorithms'`
 *      tiles are healthy (state WORKING), we render a single green
 *      summary row "Algorithms: all 5 healthy" rather than five quiet
 *      tiles.
 */

import { McTile } from './mc-types';

export interface DedupedGrid {
  /** Top-level tiles the main grid renders (one per slot). */
  tiles: McTile[];
  /** Map of root tile id → dependent tiles collapsed under it. */
  dependents: Record<string, McTile[]>;
  /** When the algorithms group is all healthy, this is the summary
   *  placeholder that replaces the 5 individual tiles. Null otherwise
   *  (tiles render normally). */
  algorithmsSummary: McTile | null;
}

export function applyDedup(input: McTile[]): DedupedGrid {
  const byId = new Map(input.map((t) => [t.id, t]));
  const dependents: Record<string, McTile[]> = {};

  // 1. Root-cause collapse.
  const visible: McTile[] = [];
  for (const tile of input) {
    if (tile.root_cause && byId.has(tile.root_cause)) {
      const rootList = dependents[tile.root_cause] ?? [];
      rootList.push(tile);
      dependents[tile.root_cause] = rootList;
      continue;
    }
    visible.push(tile);
  }

  // 2. Algorithms group collapse — only if every algorithms tile is
  //    still in the visible set AND all WORKING.
  const algoTiles = visible.filter((t) => t.group === 'algorithms');
  let algorithmsSummary: McTile | null = null;
  let finalTiles = visible;
  if (algoTiles.length > 0 && algoTiles.every((t) => t.state === 'WORKING')) {
    algorithmsSummary = {
      id: 'algorithms_group',
      name: 'Algorithms',
      state: 'WORKING',
      plain_english: `All ${algoTiles.length} algorithm runtimes healthy.`,
      last_action_at: null,
      progress: null,
      actions: [],
      group: 'algorithms',
      root_cause: null,
    };
    finalTiles = visible.filter((t) => t.group !== 'algorithms');
  }

  return { tiles: finalTiles, dependents, algorithmsSummary };
}
