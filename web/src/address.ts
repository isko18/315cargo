/**
 * Сборка строки адреса для вставки в PDD (智能填写).
 *
 * Зеркалит DeliveryAddress.one_line на бэкенде — одна точка правды на фронте,
 * чтобы предпросмотр на «Адресе доставки» и в карточке карго не разъезжались.
 * Порядок: ФИО, телефон, 省市区, детальный адрес, код карго, код клиента, индекс.
 */

export type AddressParts = {
  recipient_name?: string | null;
  phone?: string | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  detail_address?: string | null;
  postal_code?: string | null;
};

const clean = (v?: string | null) => (v ?? '').trim();

/** 省市区 слитно — так ожидает распознавание PDD. */
export function regionLine(a: AddressParts): string {
  return [a.province, a.city, a.district].map(clean).filter(Boolean).join('');
}

/**
 * @param recipient ФИО получателя карго; пусто — берётся общее из адреса,
 *                  а если и его нет — код клиента (как на бэкенде).
 */
export function buildAddressLine(
  a: AddressParts,
  opts: { recipient?: string | null; cargoCode?: string | null; clientCode?: string | null } = {},
): string {
  const clientCode = clean(opts.clientCode);
  const recipient = clean(opts.recipient) || clean(a.recipient_name) || clientCode;
  return [
    recipient,
    clean(a.phone),
    regionLine(a),
    clean(a.detail_address),
    clean(opts.cargoCode),
    // Без дубля: если ФИО нигде не задано, получателем стал сам код клиента.
    clientCode === recipient ? '' : clientCode,
    clean(a.postal_code),
  ]
    .filter(Boolean)
    .join(' ');
}
