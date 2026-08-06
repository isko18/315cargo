import { describe, expect, it } from 'vitest';
import { buildAddressLine, regionLine } from './address';

const WAREHOUSE = {
  recipient_name: 'Общий Запасной',
  phone: '13250150777',
  province: '广东',
  city: '佛山',
  district: '南海',
  detail_address: '里水镇和顺鹤峰1号仓315库',
  postal_code: '528241',
};

describe('buildAddressLine', () => {
  it('собирает строку в порядке, который ждёт PDD', () => {
    expect(
      buildAddressLine(WAREHOUSE, {
        recipient: '张伟',
        cargoCode: 'x69610',
        clientCode: 'X0001',
      }),
    ).toBe('张伟 13250150777 广东佛山南海 里水镇和顺鹤峰1号仓315库 x69610 X0001 528241');
  });

  it('без ФИО карго берёт общее из адреса', () => {
    const line = buildAddressLine(WAREHOUSE, { clientCode: 'X0001' });
    expect(line.startsWith('Общий Запасной ')).toBe(true);
  });

  it('без обоих ФИО получателем становится код клиента и не дублируется', () => {
    const line = buildAddressLine(
      { ...WAREHOUSE, recipient_name: '' },
      { clientCode: 'X0001' },
    );
    expect(line.startsWith('X0001 ')).toBe(true);
    expect(line.match(/X0001/g)).toHaveLength(1);
  });

  it('пропускает пустой код карго', () => {
    const line = buildAddressLine(WAREHOUSE, { recipient: '张伟', clientCode: 'X0001' });
    expect(line).toBe('张伟 13250150777 广东佛山南海 里水镇和顺鹤峰1号仓315库 X0001 528241');
  });

  it('обрезает пробелы и пропускает незаполненные части', () => {
    expect(
      buildAddressLine(
        { phone: ' 13250150777 ', province: '广东', detail_address: '', postal_code: null },
        { recipient: ' 张伟 ', clientCode: 'X0001' },
      ),
    ).toBe('张伟 13250150777 广东 X0001');
  });
});

describe('regionLine', () => {
  it('склеивает 省市区 без пробелов', () => {
    expect(regionLine(WAREHOUSE)).toBe('广东佛山南海');
  });

  it('переживает пустые части', () => {
    expect(regionLine({ province: '广东', city: '', district: null })).toBe('广东');
  });
});
