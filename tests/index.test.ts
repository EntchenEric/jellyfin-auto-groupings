import { describe, it, expect } from 'vitest';
import { groupMediaItems, JellyfinItem } from '../src/index';

const createItem = (id: string, name: string, year?: number, type: 'Movie' | 'Series' = 'Movie'): JellyfinItem => ({
  Id: id,
  Name: name,
  ProductionYear: year,
  Type: type,
});

describe('groupMediaItems', () => {
  it('groups movies by franchise/collection title', () => {
    const items = [
      createItem('1', 'The Matrix', 1999),
      createItem('2', 'The Matrix Reloaded', 2003),
      createItem('3', 'The Matrix Revolutions', 2003),
      createItem('4', 'Inception', 2010),
    ];

    const result = groupMediaItems(items);

    expect(result.groups).toHaveLength(1);
    expect(result.groups[0].name).toBe('The Matrix Collection');
    expect(result.groups[0].items).toHaveLength(3);
    expect(result.standalone).toHaveLength(1);
    expect(result.standalone[0].Name).toBe('Inception');
  });

  it('handles empty input list', () => {
    const result = groupMediaItems([]);
    expect(result.groups).toEqual([]);
    expect(result.standalone).toEqual([]);
  });

  it('handles custom minGroupSize threshold', () => {
    const items = [
      createItem('1', 'Iron Man', 2008),
      createItem('2', 'Iron Man 2', 2010),
      createItem('3', 'Avatar', 2009),
    ];

    const defaultResult = groupMediaItems(items, { minGroupSize: 3 });
    expect(defaultResult.groups).toHaveLength(0);
    expect(defaultResult.standalone).toHaveLength(3);

    const customResult = groupMediaItems(items, { minGroupSize: 2 });
    expect(customResult.groups).toHaveLength(1);
    expect(customResult.groups[0].name).toBe('Iron Man Collection');
    expect(customResult.groups[0].items).toHaveLength(2);
  });

  it('orders items within groups chronologically by ProductionYear', () => {
    const items = [
      createItem('3', 'Toy Story 3', 2010),
      createItem('1', 'Toy Story', 1995),
      createItem('2', 'Toy Story 2', 1999),
    ];

    const result = groupMediaItems(items, { minGroupSize: 2 });
    expect(result.groups).toHaveLength(1);
    expect(result.groups[0].items.map((i) => i.ProductionYear)).toEqual([1995, 1999, 2010]);
  });

  it('handles items with identical prefixes but different non-sequential names gracefully', () => {
    const items = [
      createItem('1', 'Star Wars: Episode IV', 1977),
      createItem('2', 'Star Wars: Episode V', 1980),
      createItem('3', 'Star Trek: The Motion Picture', 1979),
    ];

    const result = groupMediaItems(items, { minGroupSize: 2 });
    expect(result.groups).toHaveLength(1);
    expect(result.groups[0].name).toBe('Star Wars Collection');
  });
});
