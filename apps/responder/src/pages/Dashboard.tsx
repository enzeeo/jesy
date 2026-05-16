import { useEffect, useMemo } from 'react';
import { Navigate } from 'react-router-dom';

import FiltersPanel from '../components/FiltersPanel';
import IncidentQueue from '../components/IncidentQueue';
import IncidentSheet from '../components/IncidentSheet';
import MapView from '../components/MapView';
import ResourceRoster from '../components/ResourceRoster';
import RouteDrawer from '../components/RouteDrawer';
import StatsBar from '../components/StatsBar';
import { getDataAdapter } from '../lib/data';
import { useDashboardStore } from '../lib/store';

function hasAuth(): boolean {
  try {
    return localStorage.getItem('responder-auth') === '1';
  } catch {
    return false;
  }
}

export default function Dashboard() {
  const adapter = useMemo(() => getDataAdapter(), []);
  const hydrate = useDashboardStore((s) => s.hydrate);
  const applyEvent = useDashboardStore((s) => s.applyEvent);

  useEffect(() => {
    let cancelled = false;
    void adapter.loadInitialState().then((state) => {
      if (cancelled) return;
      hydrate(state);
    });
    const unsubscribe = adapter.subscribe((event) => {
      applyEvent(event);
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [adapter, hydrate, applyEvent]);

  if (!hasAuth()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen w-screen flex-col bg-zinc-950 text-zinc-100">
      <StatsBar adapter={adapter} />
      <div className="flex flex-1 overflow-hidden">
        <FiltersPanel />
        <main className="relative flex flex-1 flex-col overflow-hidden">
          <div className="relative flex-1 overflow-hidden">
            <MapView />
            <ResourceRoster />
            <IncidentSheet adapter={adapter} />
          </div>
          <RouteDrawer adapter={adapter} />
        </main>
        <IncidentQueue />
      </div>
    </div>
  );
}
