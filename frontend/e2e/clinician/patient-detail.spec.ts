import { expect, signedInApp, test } from '../support/fixtures';
import { CLINICIAN_ME, CLINIC_OBSERVATIONS, PANEL_PATIENT_ID } from '../support/mock-api';

const DETAIL_URL = `/clinic/patients/${PANEL_PATIENT_ID}`;

test.describe('Clinician Patient detail', () => {
  test('Trajectory tab shows the shared hero, the non-diagnostic note, deterministic-only', async ({
    page,
  }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto(DETAIL_URL);

    await expect(page.getByRole('heading', { name: 'Pat Example' })).toBeVisible();
    const hero = page.getByRole('region', { name: '30-day trend for Pat Example' });
    await expect(hero.getByText('Improving')).toBeVisible();
    // The non-diagnostic disclaimer is present.
    await expect(
      page.getByText('Trends support clinical judgment; they are not a diagnosis.'),
    ).toBeVisible();
    // Deterministic only — the clinician view is never AI-narrated (ADR-0012).
    await expect(page.getByText('AI-written summary')).toHaveCount(0);
  });

  test('Trend table shows cross-source rows including "not judged"', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME, clinicObservations: CLINIC_OBSERVATIONS });
    await page.goto(DETAIL_URL);

    await page.getByRole('button', { name: 'Trend table' }).click();
    await expect(page.getByRole('heading', { name: 'What the data shows' })).toBeVisible();

    const table = page.getByRole('table');
    await expect(table.getByRole('columnheader', { name: 'Judged' })).toBeVisible();
    // The single-reading HbA1c row is "not judged" (never a fabricated "stable").
    const hba1cRow = table.locator('tr', { hasText: 'Hemoglobin A1c' });
    await expect(hba1cRow.getByText('not judged')).toBeVisible();
    await expect(hba1cRow.getByText('single reading')).toBeVisible();
  });

  test('Observations tab paginates', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME, clinicObservations: CLINIC_OBSERVATIONS });
    await page.goto(DETAIL_URL);

    await page.getByRole('button', { name: 'Observations' }).click();
    await expect(page.getByRole('heading', { name: 'Observations' })).toBeVisible();

    // 25 synthetic records, 20 per page.
    await expect(page.getByText(`Showing 1–20 of ${CLINIC_OBSERVATIONS.length}`)).toBeVisible();
    const older = page.getByRole('button', { name: 'Older' });
    await expect(older).toBeEnabled();
    await older.click();
    await expect(
      page.getByText(`Showing 21–${CLINIC_OBSERVATIONS.length} of ${CLINIC_OBSERVATIONS.length}`),
    ).toBeVisible();
  });

  test('Features tab: share_with_clinic is read-only, clinic-managed key has a switch', async ({
    page,
  }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto(DETAIL_URL);

    await page.getByRole('button', { name: 'Features' }).click();
    await expect(page.getByRole('heading', { name: 'Monitoring for this patient' })).toBeVisible();

    // ADR-0020 §3(b): the patient-held share_with_clinic key renders READ-ONLY —
    // "Controlled by the patient", NO switch, NO renewal control.
    const shareRow = page.locator('.src', { hasText: 'Share data with my clinic' });
    await expect(shareRow.getByText('Controlled by the patient — read-only here.')).toBeVisible();
    await expect(shareRow.getByRole('switch')).toHaveCount(0);
    await expect(page.getByLabel('Renewal date for Share data with my clinic')).toHaveCount(0);

    // A clinic-managed key DOES get the switch (clinician authority).
    const biomechSwitch = page.getByRole('switch', { name: 'BioMech report upload' });
    await expect(biomechSwitch).toBeVisible();
    await expect(page.getByLabel('Renewal date for BioMech report upload')).toBeVisible();
  });

  test('shows the neutral "Patient not found" screen for an unknown id', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto('/clinic/patients/00000000-0000-4000-8000-000000000000');

    await expect(page.getByRole('heading', { name: 'Patient not found' })).toBeVisible();
    await expect(page.getByText('There is no patient record at this address.')).toBeVisible();
    // Neutral — never says "no access" (would re-introduce the existence signal).
    await expect(page.getByText(/no access|not authorized|forbidden/i)).toHaveCount(0);
  });
});
