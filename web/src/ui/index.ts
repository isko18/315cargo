export { default as Button } from './Button';
export type { ButtonProps } from './Button';
export { Card, CardHeader, CardBody } from './Card';
export { Field, Input, Select, Checkbox } from './Field';
export type { InputProps, SelectProps } from './Field';
export { default as Badge } from './Badge';
export { default as Alert } from './Alert';
export { default as EmptyState } from './EmptyState';
export { Stat, StatGrid } from './Stat';
export { default as PageHeader } from './PageHeader';
export { default as Skeleton } from './Skeleton';
export { default as Segmented } from './Segmented';
export type { SegmentedOption } from './Segmented';
export { default as DataTable } from './DataTable';
export type { Column } from './DataTable';
export { default as Modal } from './Modal';

import type { ApiError } from '../api';

/** Разворачивает DRF-ошибки ({field: [msg]}) в читаемую строку. */
export function formError(e: unknown): string {
  const ae = e as ApiError;
  if (ae?.data && typeof ae.data === 'object') {
    return Object.entries(ae.data)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
      .join('; ');
  }
  return ae?.message ?? 'Ошибка';
}
