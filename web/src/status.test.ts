import { describe, expect, it } from 'vitest';
import { FINAL, statusMeta } from './status';

describe('statusMeta', () => {
  it('возвращает подпись и тон для известного статуса', () => {
    expect(statusMeta('issued')).toEqual({ label: 'Выдан клиенту', tone: 'green' });
    expect(statusMeta('at_pickup_point').tone).toBe('violet');
  });

  it('для неизвестного статуса — серый тон и сам ключ', () => {
    expect(statusMeta('weird')).toEqual({ label: 'weird', tone: 'gray' });
  });
});

describe('FINAL', () => {
  it('содержит выданные и отменённые', () => {
    expect(FINAL.has('issued')).toBe(true);
    expect(FINAL.has('cancelled')).toBe(true);
    expect(FINAL.has('at_pickup_point')).toBe(false);
  });
});
