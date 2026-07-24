/**
 * Opt-in setup: save Playwright storageState for QA sidecar personas.
 *
 *   set -a && source .env.qa && set +a
 *   CURATORX_E2E_QA_ROLES=1 QA_BASE_URL=http://10.10.1.202:8790 \
 *     npx playwright test e2e/auth.setup.ts --config=playwright.qa.config.ts
 *
 * Or with the default config (reuseExistingServer + health already up):
 *   CURATORX_E2E_QA_ROLES=1 E2E_BASE_URL=http://10.10.1.202:8790 \
 *     npx playwright test e2e/auth.setup.ts
 */

import { test as setup } from "@playwright/test";
import {
  rolesEnabled,
  saveGuestTourStorageState,
  saveRoleStorageState,
  type QaRole,
} from "./fixtures/auth-roles";

const roles: QaRole[] = ["owner", "member", "youth", "guest"];

setup.describe("QA role storageState", () => {
  setup.beforeEach(() => {
    setup.skip(!rolesEnabled(), "Set CURATORX_E2E_QA_ROLES=1 against the multi-role QA sidecar");
  });

  for (const role of roles) {
    setup(`save ${role} storageState`, async ({ browser }) => {
      const path = await saveRoleStorageState(browser, role);
      console.log(`Wrote ${path}`);
    });
  }

  setup("save guest-tour (no login) storageState", async ({ browser }) => {
    const path = await saveGuestTourStorageState(browser);
    console.log(`Wrote ${path}`);
  });
});
