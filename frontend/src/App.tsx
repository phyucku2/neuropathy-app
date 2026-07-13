import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { Loading } from './components/StatusMessages';
import { AddDataPage } from './features/add/AddDataPage';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { CheckInPage } from './features/checkin/CheckInPage';
import { PanelPage } from './features/clinic/PanelPage';
import { PatientDetailPage } from './features/clinic/PatientDetailPage';
import { HomePage } from './features/home/HomePage';
import { SettingsPage } from './features/settings/SettingsPage';
import { TrendsPage } from './features/trends/TrendsPage';

function RequireAuth() {
  const { status } = useAuth();
  if (status === 'restoring') {
    return <Loading label="Loading your account…" />;
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

/**
 * Role-aware area guards: /auth/me's role decides which area a signed-in user
 * lands in. A clinician on a patient route goes to the panel; anyone else on a
 * clinician route goes to the patient home — each rule targets the OTHER
 * area's home, so the pair can never redirect in a loop.
 */
function PatientArea() {
  const { user } = useAuth();
  if (user === null) {
    return <Loading label="Loading your account…" />;
  }
  return user.role === 'clinician' ? <Navigate to="/clinic" replace /> : <Outlet />;
}

function ClinicianArea() {
  const { user } = useAuth();
  if (user === null) {
    return <Loading label="Loading your account…" />;
  }
  return user.role === 'clinician' ? <Outlet /> : <Navigate to="/" replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<PatientArea />}>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="trends" element={<TrendsPage />} />
            <Route path="check-in" element={<CheckInPage />} />
            <Route path="add" element={<AddDataPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
        <Route path="clinic" element={<ClinicianArea />}>
          <Route element={<AppShell variant="clinician" />}>
            <Route index element={<PanelPage />} />
            <Route path="patients/:patientId" element={<PatientDetailPage />} />
            <Route path="*" element={<Navigate to="/clinic" replace />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
