import { lazy, Suspense, useReducer } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Loading } from './components/StatusMessages';
// First-run welcome (ADR-0044): a static import (not lazy) so the very first screen a new
// patient sees never flashes a Suspense fallback while a chunk loads.
import { OnboardingWizard } from './features/onboarding/OnboardingWizard';
import { isOnboardingComplete } from './features/onboarding/onboardingState';
// OfflineCheckInSync stays a static import (ADR-0030): it renders nothing, is always
// mounted in the patient area, and isn't a route — code-splitting it would add a chunk
// round-trip for no payload benefit.
import { OfflineCheckInSync } from './features/checkin/OfflineCheckInSync';
import { useNativeShell } from './native/useNativeShell';
import { useCaregiverPush } from './native/useCaregiverPush';

// Route-level code-splitting (ADR-0032): each major screen is its own chunk, loaded on
// demand behind the <Suspense> boundary below, so the initial download is the shell +
// the landing route only — not every screen. The page components are named exports, so
// each import is mapped to a `default` for React.lazy. The Suspense fallback reuses the
// existing Loading component (a plain role="status" line) so a lazy chunk resolving mid
// navigation renders cleanly with ZERO console errors (the E2E gate, ADR-0022).
const LoginPage = lazy(() =>
  import('./features/auth/LoginPage').then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('./features/auth/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const AboutPage = lazy(() =>
  import('./features/about/AboutPage').then((m) => ({ default: m.AboutPage })),
);
const PrivacyPage = lazy(() =>
  import('./features/about/PrivacyPage').then((m) => ({ default: m.PrivacyPage })),
);
const HomePage = lazy(() =>
  import('./features/home/HomePage').then((m) => ({ default: m.HomePage })),
);
const TrendsPage = lazy(() =>
  import('./features/trends/TrendsPage').then((m) => ({ default: m.TrendsPage })),
);
const LearnPage = lazy(() =>
  import('./features/learn/LearnPage').then((m) => ({ default: m.LearnPage })),
);
const CheckInPage = lazy(() =>
  import('./features/checkin/CheckInPage').then((m) => ({ default: m.CheckInPage })),
);
const AddDataPage = lazy(() =>
  import('./features/add/AddDataPage').then((m) => ({ default: m.AddDataPage })),
);
const MedsPage = lazy(() =>
  import('./features/meds/MedsPage').then((m) => ({ default: m.MedsPage })),
);
const EventsPage = lazy(() =>
  import('./features/events/EventsPage').then((m) => ({ default: m.EventsPage })),
);
const FoodLogPage = lazy(() =>
  import('./features/food/FoodLogPage').then((m) => ({ default: m.FoodLogPage })),
);
const SettingsPage = lazy(() =>
  import('./features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);
const RecordsPage = lazy(() =>
  import('./features/records/RecordsPage').then((m) => ({ default: m.RecordsPage })),
);
const HandoutPage = lazy(() =>
  import('./features/handout/HandoutPage').then((m) => ({ default: m.HandoutPage })),
);
const EmrCallbackPage = lazy(() =>
  import('./features/emr/EmrCallbackPage').then((m) => ({ default: m.EmrCallbackPage })),
);
const PanelPage = lazy(() =>
  import('./features/clinic/PanelPage').then((m) => ({ default: m.PanelPage })),
);
const PatientDetailPage = lazy(() =>
  import('./features/clinic/PatientDetailPage').then((m) => ({ default: m.PatientDetailPage })),
);
const ClinicianSettingsPage = lazy(() =>
  import('./features/clinic/ClinicianSettingsPage').then((m) => ({
    default: m.ClinicianSettingsPage,
  })),
);
const CaregiverJoinPage = lazy(() =>
  import('./features/caregiver/CaregiverJoinPage').then((m) => ({
    default: m.CaregiverJoinPage,
  })),
);
const CaregiverHomePage = lazy(() =>
  import('./features/caregiver/CaregiverHomePage').then((m) => ({
    default: m.CaregiverHomePage,
  })),
);
const CaregiverSummaryPage = lazy(() =>
  import('./features/caregiver/CaregiverSummaryPage').then((m) => ({
    default: m.CaregiverSummaryPage,
  })),
);
const CaregiverAlertsPage = lazy(() =>
  import('./features/caregiver/CaregiverAlertsPage').then((m) => ({
    default: m.CaregiverAlertsPage,
  })),
);

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
 * lands in. A clinician on a patient route goes to the panel, a caregiver goes
 * to the caregiver home (ADR-0047); anyone else on a clinician or caregiver
 * route goes to the patient home — each rule targets ANOTHER area's home, so
 * the guards can never redirect in a loop.
 */
function PatientArea() {
  const { user } = useAuth();
  // Lets the onboarding gate re-render once the wizard finishes (the flag is now persisted).
  const [, onOnboardingComplete] = useReducer((n: number) => n + 1, 0);
  if (user === null) {
    return <Loading label="Loading your account…" />;
  }
  if (user.role === 'clinician') {
    return <Navigate to="/clinic" replace />;
  }
  if (user.role === 'caregiver') {
    return <Navigate to="/caregiver" replace />;
  }
  // First-run welcome (ADR-0044): a new patient sees the wizard once, full-screen (no tab
  // bar), before the app. Persisted per user_id in localStorage — a returning patient skips
  // straight through. Fails toward SHOWING the welcome if the flag can't be read.
  if (!isOnboardingComplete(user.user_id)) {
    return <OnboardingWizard userId={user.user_id} onComplete={onOnboardingComplete} />;
  }
  return (
    <>
      {/* Offline check-in sync triggers (ADR-0030): boot flush + 'online' events,
          patient sessions only. Renders nothing. */}
      <OfflineCheckInSync />
      <Outlet />
    </>
  );
}

function ClinicianArea() {
  const { user } = useAuth();
  if (user === null) {
    return <Loading label="Loading your account…" />;
  }
  return user.role === 'clinician' ? <Outlet /> : <Navigate to="/" replace />;
}

function CaregiverArea() {
  const { user } = useAuth();
  // Native-only caregiver push registration (ADR-0047 B2): a signed-in caregiver on a
  // native platform registers the device with FCM here; no-op on web and for non-caregivers.
  // Called unconditionally (hook rules) — the gating lives inside the hook.
  useCaregiverPush();
  if (user === null) {
    return <Loading label="Loading your account…" />;
  }
  return user.role === 'caregiver' ? <Outlet /> : <Navigate to="/" replace />;
}

export function App() {
  // Native-only shell wiring (status bar, splash, hardware back). No-op on web (ADR-0025).
  useNativeShell();
  return (
    // The ErrorBoundary sits ABOVE the Suspense (ADR-0032): Suspense only handles a lazy
    // chunk's PENDING state, not a REJECTED import (flaky network, or a post-deploy
    // stale-chunk 404 when a client holds an old index.html). A rejection throws past
    // Suspense, so without this boundary the whole app white-screens. The fallback offers a
    // reload, which re-fetches index.html and the current chunk names.
    <ErrorBoundary>
      <Suspense fallback={<Loading />}>
        <Routes>
          {/* Auth-less routes: a store reviewer and a logged-out patient must reach these,
            so /about and /privacy sit OUTSIDE RequireAuth alongside /login (ADR-0032). */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          {/* Caregiver registration (ADR-0047): auth-less like /register — a NEW caregiver
              creates their account WITH the patient's invite code. A static path, so it
              outranks the authenticated /caregiver area's catch-all below. */}
          <Route path="/caregiver/join" element={<CaregiverJoinPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<PatientArea />}>
              <Route element={<AppShell />}>
                <Route index element={<HomePage />} />
                <Route path="trends" element={<TrendsPage />} />
                {/* Learn — the non-diagnostic education index (ADR-0037), a patient-area
                    route alongside trends/add/settings. Placeholder content only. */}
                <Route path="learn" element={<LearnPage />} />
                <Route path="check-in" element={<CheckInPage />} />
                <Route path="add" element={<AddDataPage />} />
                {/* Patient-entered capture (ADR-0045 P2): the medication change-log and the
                    between-visit notes/events surfaces, reached from cards on Add data. */}
                <Route path="meds" element={<MedsPage />} />
                <Route path="events" element={<EventsPage />} />
                {/* Food & nutrition log (ADR-0042) — reached from a card on Add data. */}
                <Route path="food" element={<FoodLogPage />} />
                <Route path="settings" element={<SettingsPage />} />
                {/* Your Records (read-only, display-only) — reached from a card on the
                    Sources surface, NOT a bottom-nav tab (ADR-0039: five is the max). */}
                <Route path="records" element={<RecordsPage />} />
                {/* Visit-Ready Summary (ADR-0045): the patient-held print/PDF handout, reached
                    from a Sources card (not a sixth nav tab — five is the accessible max). */}
                <Route path="handout" element={<HandoutPage />} />
                {/* The SMART redirect relay (ADR-0028): the EMR sends the patient's browser
                to /emr/callback?code=..&state=..; this authenticated route forwards
                them to the bearer-only backend callback. On native, the App-Links /
                custom-scheme handler (nativeShell appUrlOpen) routes here too. */}
                <Route path="emr/callback" element={<EmrCallbackPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Route>
            <Route path="clinic" element={<ClinicianArea />}>
              <Route element={<AppShell variant="clinician" />}>
                <Route index element={<PanelPage />} />
                <Route path="patients/:patientId" element={<PatientDetailPage />} />
                {/* Clinician account settings (§1B C6): two-step verification enrollment.
                    Clinician area only — the patient settings surface is untouched. */}
                <Route path="settings" element={<ClinicianSettingsPage />} />
                <Route path="*" element={<Navigate to="/clinic" replace />} />
              </Route>
            </Route>
            {/* Caregiver area (ADR-0047): gated like /clinic; the caregiver AppShell
                variant renders the persistent 911 banner on every screen. */}
            <Route path="caregiver" element={<CaregiverArea />}>
              <Route element={<AppShell variant="caregiver" />}>
                <Route index element={<CaregiverHomePage />} />
                {/* Alerts feed (ADR-0047 B1): the caregiver area has no tab bar, so it is
                    reached from a card on the caregiver home. */}
                <Route path="alerts" element={<CaregiverAlertsPage />} />
                <Route path="patients/:patientId/summary" element={<CaregiverSummaryPage />} />
                <Route path="*" element={<Navigate to="/caregiver" replace />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
