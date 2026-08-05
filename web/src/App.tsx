import { Navigate, Route, Routes } from 'react-router-dom';
import { getToken, allowedTabs, canAccessTab } from './api';
import { TAB_ROUTE } from './tabs';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import ScanPage from './pages/ScanPage';
import IssuePage from './pages/IssuePage';
import WarehousePage from './pages/WarehousePage';
import ChinaPage from './pages/ChinaPage';
import StaffPage from './pages/StaffPage';
import PickupPointsPage from './pages/PickupPointsPage';
import CargoSettingsPage from './pages/CargoSettingsPage';
import ClientsPage from './pages/ClientsPage';
import DeliveryPage from './pages/DeliveryPage';
import DeliveryTariffPage from './pages/DeliveryTariffPage';
import AnalyticsPage from './pages/AnalyticsPage';
import OverviewPage from './pages/OverviewPage';
import ProfilePage from './pages/ProfilePage';
import DeliveryAddressPage from './pages/DeliveryAddressPage';
import CargoDetailPage from './pages/CargoDetailPage';

function RequireAuth({ children }: { children: JSX.Element }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

/** Первый доступный пользователю маршрут (для landing и редиректов). */
function homeRoute(): string {
  const first = allowedTabs()[0];
  return (first && TAB_ROUTE[first]) || '/scan';
}

/** Пускает на вкладку только при наличии права; иначе — на домашнюю. */
function TabGuard({ tab, children }: { tab: string; children: JSX.Element }) {
  return canAccessTab(tab) ? children : <Navigate to={homeRoute()} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/scan" element={<TabGuard tab="scan"><ScanPage /></TabGuard>} />
        <Route path="/issue" element={<TabGuard tab="issue"><IssuePage /></TabGuard>} />
        <Route path="/warehouse" element={<TabGuard tab="warehouse"><WarehousePage /></TabGuard>} />
        <Route path="/china" element={<TabGuard tab="china"><ChinaPage /></TabGuard>} />
        <Route path="/clients" element={<TabGuard tab="clients"><ClientsPage /></TabGuard>} />
        <Route path="/delivery" element={<TabGuard tab="delivery"><DeliveryPage /></TabGuard>} />
        <Route path="/staff" element={<TabGuard tab="staff"><StaffPage /></TabGuard>} />
        <Route path="/pickup-points" element={<TabGuard tab="pickup"><PickupPointsPage /></TabGuard>} />
        <Route path="/cargo-settings" element={<TabGuard tab="tariff"><CargoSettingsPage /></TabGuard>} />
        {/* Старый адрес страницы тарифа — на случай сохранённых ссылок. */}
        <Route path="/tariff" element={<Navigate to="/cargo-settings" replace />} />
        <Route path="/delivery-tariff" element={<TabGuard tab="delivery_tariff"><DeliveryTariffPage /></TabGuard>} />
        <Route path="/analytics" element={<TabGuard tab="analytics"><AnalyticsPage /></TabGuard>} />
        <Route path="/overview" element={<TabGuard tab="overview"><OverviewPage /></TabGuard>} />
        <Route path="/cargo/:id" element={<TabGuard tab="overview"><CargoDetailPage /></TabGuard>} />
        <Route path="/delivery-address" element={<TabGuard tab="delivery_address"><DeliveryAddressPage /></TabGuard>} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/" element={<Navigate to={homeRoute()} replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
