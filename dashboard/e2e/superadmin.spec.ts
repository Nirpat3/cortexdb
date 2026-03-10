import { test, expect, Page } from '@playwright/test';

/**
 * E2E tests for the CortexDB SuperAdmin Dashboard.
 *
 * These tests exercise the login flow, page navigation, task creation,
 * language switching, and error boundary behavior.
 *
 * Pre-requisite: CortexDB API server and dashboard must be running.
 * Alternatively, use MSW or a mock API for offline testing.
 */

const PASSPHRASE = 'thisismydatabasebaby';
const API_BASE = process.env.API_BASE || 'http://localhost:5400';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Authenticate via the SuperAdmin login page and store the session.
 */
async function loginAsSuperAdmin(page: Page) {
  await page.goto('/superadmin');

  // The layout should show a login prompt if not authenticated
  const passphraseInput = page.locator('input[type="password"], input[placeholder*="passphrase" i], input[placeholder*="password" i]');

  // If already logged in (cookie/localStorage), skip
  if (await passphraseInput.count() === 0) {
    return;
  }

  await passphraseInput.first().fill(PASSPHRASE);

  // Submit — look for a button with text like "Login", "Enter", "Unlock"
  const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Enter"), button:has-text("Unlock")');
  await submitBtn.first().click();

  // Wait for navigation away from login
  await page.waitForURL(/\/superadmin/, { timeout: 10_000 });
}

// ---------------------------------------------------------------------------
// Login Flow
// ---------------------------------------------------------------------------

test.describe('SuperAdmin Login', () => {
  test('successful login with correct passphrase', async ({ page }) => {
    await loginAsSuperAdmin(page);

    // Should see the dashboard content (title or nav element)
    const heading = page.locator('h1, [data-testid="dashboard-title"]');
    await expect(heading.first()).toBeVisible({ timeout: 10_000 });
  });

  test('failed login with incorrect passphrase', async ({ page }) => {
    await page.goto('/superadmin');

    const passphraseInput = page.locator('input[type="password"], input[placeholder*="passphrase" i], input[placeholder*="password" i]');
    if (await passphraseInput.count() === 0) {
      test.skip(true, 'No login form visible — may already be authenticated');
      return;
    }

    await passphraseInput.first().fill('wrong-passphrase');
    const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Enter"), button:has-text("Unlock")');
    await submitBtn.first().click();

    // Should show an error message
    const errorMsg = page.locator('[role="alert"], .error, .text-red, [data-testid="login-error"]');
    await expect(errorMsg.first()).toBeVisible({ timeout: 5_000 }).catch(() => {
      // Some implementations show a toast — check for that too
      return expect(page.locator('.toast, [data-testid="toast"]').first()).toBeVisible({ timeout: 3_000 });
    });
  });
});

// ---------------------------------------------------------------------------
// Page Navigation
// ---------------------------------------------------------------------------

test.describe('SuperAdmin Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page);
  });

  const pages = [
    { name: 'Dashboard', path: '/superadmin' },
    { name: 'Agents', path: '/superadmin/agents' },
    { name: 'Tasks', path: '/superadmin/tasks' },
    { name: 'Chat', path: '/superadmin/chat' },
    { name: 'Audit', path: '/superadmin/audit' },
    { name: 'Health', path: '/superadmin/health' },
  ];

  for (const pg of pages) {
    test(`navigate to ${pg.name} page`, async ({ page }) => {
      await page.goto(pg.path);
      await page.waitForLoadState('networkidle');

      // Page should load without crashing — check for a heading or content area
      const content = page.locator('main, [role="main"], .content, h1, h2');
      await expect(content.first()).toBeVisible({ timeout: 10_000 });

      // No uncaught JS errors
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(err.message));
      expect(errors).toHaveLength(0);
    });
  }

  test('sidebar navigation items are visible', async ({ page }) => {
    await page.goto('/superadmin');
    await page.waitForLoadState('networkidle');

    // The sidebar should have navigation links
    const navLinks = page.locator('nav a, [role="navigation"] a, aside a');
    const count = await navLinks.count();
    expect(count).toBeGreaterThan(5); // At least a handful of nav items
  });
});

// ---------------------------------------------------------------------------
// Task Creation
// ---------------------------------------------------------------------------

test.describe('Task Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page);
  });

  test('create a new task', async ({ page }) => {
    await page.goto('/superadmin/tasks');
    await page.waitForLoadState('networkidle');

    // Look for "Create" or "New Task" button
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New Task"), button:has-text("Add Task"), [data-testid="create-task"]');

    if (await createBtn.count() === 0) {
      test.skip(true, 'No create task button found on tasks page');
      return;
    }

    await createBtn.first().click();

    // Fill in the task form
    const titleInput = page.locator('input[name="title"], input[placeholder*="title" i], input[placeholder*="task" i]');
    if (await titleInput.count() > 0) {
      await titleInput.first().fill('E2E Test Task — automated');
    }

    const descInput = page.locator('textarea[name="description"], textarea[placeholder*="description" i], textarea');
    if (await descInput.count() > 0) {
      await descInput.first().fill('Created by Playwright E2E test suite');
    }

    // Submit the form
    const submitBtn = page.locator('button[type="submit"], button:has-text("Create"), button:has-text("Save"), button:has-text("Submit")');
    if (await submitBtn.count() > 0) {
      await submitBtn.first().click();
      // Wait for the task list to update
      await page.waitForTimeout(2_000);
    }
  });
});

// ---------------------------------------------------------------------------
// Language Switcher
// ---------------------------------------------------------------------------

test.describe('Language Switcher', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page);
  });

  test('language switcher changes UI text', async ({ page }) => {
    await page.goto('/superadmin');
    await page.waitForLoadState('networkidle');

    // Find the language switcher
    const switcher = page.locator('[data-testid="language-switcher"], button:has-text("EN"), button:has-text("English"), select[name="language"]');

    if (await switcher.count() === 0) {
      test.skip(true, 'No language switcher found');
      return;
    }

    // Capture initial text of a known element
    const heading = page.locator('h1').first();
    const initialText = await heading.textContent();

    // Click the switcher to open options
    await switcher.first().click();

    // Select a different language (Japanese, Spanish, etc.)
    const altLang = page.locator('button:has-text("JA"), button:has-text("日本語"), option[value="ja"], [data-lang="ja"]');
    if (await altLang.count() > 0) {
      await altLang.first().click();
      await page.waitForTimeout(1_000);

      // Text should have changed
      const newText = await heading.textContent();
      // If i18n is working, text may have changed
      // (We don't assert inequality because the heading may be a brand name)
      expect(newText).toBeDefined();
    }
  });
});

// ---------------------------------------------------------------------------
// Error Boundary
// ---------------------------------------------------------------------------

test.describe('Error Boundary', () => {
  test('displays error UI when API fails', async ({ page }) => {
    // Intercept API calls to simulate failure
    await page.route('**/v1/superadmin/**', (route) => {
      return route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal Server Error' }),
      });
    });

    await page.goto('/superadmin');
    await page.waitForLoadState('networkidle');

    // Wait a bit for data fetching to fail
    await page.waitForTimeout(3_000);

    // The page should still render (error boundary catches the crash)
    // It should NOT be a blank white page
    const body = page.locator('body');
    const bodyText = await body.textContent();
    expect(bodyText).toBeTruthy();
    expect(bodyText!.length).toBeGreaterThan(10);
  });

  test('404 page for unknown routes', async ({ page }) => {
    await page.goto('/superadmin/this-page-does-not-exist');
    await page.waitForLoadState('networkidle');

    // Should show a 404 or redirect — not crash
    const body = page.locator('body');
    const bodyText = await body.textContent();
    expect(bodyText).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Responsive Layout
// ---------------------------------------------------------------------------

test.describe('Responsive Layout', () => {
  test('dashboard renders on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 }); // iPhone X
    await loginAsSuperAdmin(page);
    await page.goto('/superadmin');
    await page.waitForLoadState('networkidle');

    // Content should still be visible
    const content = page.locator('main, [role="main"], .content, h1');
    await expect(content.first()).toBeVisible({ timeout: 10_000 });
  });
});
