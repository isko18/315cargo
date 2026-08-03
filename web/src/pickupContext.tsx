import { createContext, useContext, useEffect, useState } from 'react';
import { get } from './api';

export type PickupPoint = {
  id: number;
  title: string;
  address: string;
  phone: string;
  work_schedule: string;
  is_active: boolean;
};

type Ctx = {
  points: PickupPoint[];
  activeId: number | null;
  setActiveId: (id: number | null) => void;
  reload: () => void;
};

const PickupCtx = createContext<Ctx>({
  points: [],
  activeId: null,
  setActiveId: () => {},
  reload: () => {},
});

const KEY = 'pvz';

export function PickupProvider({ children }: { children: React.ReactNode }) {
  const [points, setPoints] = useState<PickupPoint[]>([]);
  const [activeId, setActive] = useState<number | null>(() => {
    const raw = localStorage.getItem(KEY);
    return raw ? Number(raw) : null;
  });

  function setActiveId(id: number | null) {
    setActive(id);
    if (id == null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(id));
  }

  function reload() {
    get<any>('/api/manage/pickup-points/')
      .then((d) => {
        const list = (d?.results ?? d) as PickupPoint[];
        setPoints(list);
        // Сбросить выбор, если ПВЗ больше нет.
        setActive((cur) => (cur && !list.some((p) => p.id === cur) ? null : cur));
      })
      .catch(() => setPoints([]));
  }

  useEffect(() => {
    reload();
  }, []);

  return (
    <PickupCtx.Provider value={{ points, activeId, setActiveId, reload }}>
      {children}
    </PickupCtx.Provider>
  );
}

export function usePickup() {
  return useContext(PickupCtx);
}
