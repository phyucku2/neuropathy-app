import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { Loading } from './components/StatusMessages';
import { AddDataPage } from './features/add/AddDataPage';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { CheckInPage } from './features/checkin/CheckInPage';
import { HomePage } from './features/home/HomePage';
import { SettingsPage } from './features/settings/SettingsPage';
import { TrendsPage } from './features/trends/TrendsPage';

function RequireAuth({ children }: { children: JSX.Element }) {
  const { status } = useAuth();
  if (status === 'restoring') {
    return <Loading label="Loading your account…" />;
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="trends" element={<TrendsPage />} />
        <Route path="check-in" element={<CheckInPage />} />
        <Route path="add" element={<AddDataPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
