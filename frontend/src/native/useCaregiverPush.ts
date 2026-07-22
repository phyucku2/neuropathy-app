/**
 * React entry point for caregiver push registration (ADR-0047 Phase B2). For a signed-in
 * CAREGIVER on a native platform it registers the device with FCM once (permission →
 * register → POST token) and detaches + deregisters on unmount (leaving the caregiver
 * area, e.g. logout or a role change).
 *
 * NO-OP on web and for non-caregivers: the effect returns early when the platform is not
 * native or the user is not a caregiver, and `registerCaregiverPush` itself gates on the
 * platform too — so the browser build and the Playwright/unit suites are UNAFFECTED. Safe
 * to call unconditionally from the caregiver-area layout.
 */

import { useEffect } from 'react';
import { useAuth } from '../auth/AuthContext';
import { isNativePlatform } from '../auth/platform';
import { deregisterCaregiverPush, registerCaregiverPush } from './caregiverPush';

export function useCaregiverPush(): void {
  const { user } = useAuth();
  const isCaregiver = user?.role === 'caregiver';
  useEffect(() => {
    // Web and non-caregivers: nothing to do. The native gate keeps the plugin and the
    // network entirely out of the web build.
    if (!isCaregiver || !isNativePlatform()) {
      return;
    }
    void registerCaregiverPush();
    return () => {
      // Best-effort deregister on leaving the caregiver area. Fire-and-forget: unmount
      // cleanup cannot await, and a failed DELETE is swallowed inside deregister.
      void deregisterCaregiverPush();
    };
  }, [isCaregiver]);
}
