import { describe, expect, it } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('соединяет ячейки запятой и строки CRLF', () => {
    expect(toCsv([['a', 'b'], ['c', 'd']])).toBe('a,b\r\nc,d');
  });

  it('экранирует запятые, кавычки и переносы', () => {
    expect(toCsv([['a,b', 'say "hi"', 'line\nbreak']])).toBe('"a,b","say ""hi""","line\nbreak"');
  });

  it('пустые значения превращает в пустую строку', () => {
    expect(toCsv([[null, undefined, 0]])).toBe(',,0');
  });
});
