# Task 5: Responsive storefront shell

## Result

Implemented a centered responsive customer storefront with desktop search and navigation, four-item mobile navigation, persisted UZ/RU language and light/dark controls, account route navigation, optional settings-backed support links, and a Telegram WebView back affordance. `/profile`, `/favorites`, and `/profile/addresses` use an interim sign-in/account navigation page pending the Task 7 account page work. Admin remains routed through its separate application.

The catalog uses two columns by default and four columns at the `xl` breakpoint. Existing cart and checkout surfaces now use the shared theme classes; cart amounts retain decimal precision.

## TDD evidence

- **RED — shell/theme:** `npx --yes --package=node@24 --call 'npm test -- src/components/storefront/StorefrontShell.test.tsx src/store/theme.test.ts'` failed on five expected assertions: the theme hook was unavailable, the named desktop/mobile navigation was absent, and the profile/language/control contracts were missing.
- **GREEN — shell/theme:** the same focused command passed, **7/7 tests**.
- **RED — cart precision:** `npx --yes --package=node@24 --call 'npm test -- src/pages/CartPage.test.tsx'` failed the new decimal case: expected `600.5`, rendered `601` for line total and subtotal because the old formatter rounded. The other five cart tests passed.
- **GREEN — cart precision:** `npx --yes --package=node@24 --call 'npm test -- src/pages/CartPage.test.tsx'` passed, **6/6 tests**.
- **RED — saved language:** `npx --yes --package=node@24 --call 'npm test -- src/hooks/useCartActions.test.tsx -t "saved language"'` failed because Telegram's `uz` profile locale replaced the saved `ru` choice.
- **GREEN — saved language:** the same focused command passed, **1/1 test**; Telegram locale is now used only when no explicit language preference exists.
- **RED — visible language control:** `npx --yes --package=node@24 --call 'npm test -- src/components/storefront/StorefrontShell.test.tsx -t "44px"'` failed because the select itself was wrapped in a visually hidden label.
- **GREEN — visible language control:** the same focused command passed, **1/1 test**, after separating the visible select from its screen-reader label.
- **RED — sign-in dialog sizing:** `npx --yes --package=node@24 --call 'npm test -- src/components/storefront/StorefrontShell.test.tsx -t "44px tall"'` failed because the login code input was shorter than the requested control size.
- **GREEN — sign-in dialog sizing:** the same focused command passed, **1/1 test**, after sizing the input, Telegram link, submit, and cancel controls to at least 44px.

## Verification

- Installed dependencies with Node `v24.21.0` using `npx --yes --package=node@24 --call 'node --version && npm --version && npm ci'`; install completed with 0 vulnerabilities.
- Required focused command: `npx --yes --package=node@24 --call 'npm test -- src/components/storefront/StorefrontShell.test.tsx src/store/theme.test.ts'` — **2 files, 6 tests passed**.
- Full suite: `npx --yes --package=node@24 --call 'npm test'` — **13 files, 73 tests passed**.
- Typecheck: `npx --yes --package=node@24 --call 'npm run typecheck'` — passed.
- Production build: `npx --yes --package=node@24 --call 'npm run build'` — passed; 173 modules transformed.
- Breakpoint output: built CSS includes the two-column base grid, four-column grid rules, and `@media (width>=80rem)` (`1280px`). The generated CSS also includes `@media (prefers-reduced-motion:reduce)`.
- `git diff --check` — passed.

## Files changed

Added `StorefrontHeader`, `MobileNavigation`, `LanguageSwitcher`, `ThemeToggle`, `SupportLinks`, the persisted theme store and tests, and `AccountNavigationPage`. Updated `App`, `Layout`, catalog search/grid behavior, i18n and language persistence, Telegram theme/back handling, shared storefront CSS, cart/checkout styling and exact cart amount formatting, relevant tests, and Vitest CSS processing.

## Self-review and concerns

- The customer auth provider is reused for sign-in, account switching, and logout; no second account provider was introduced.
- Support content renders only when actual public settings provide a Telegram handle, phone number, or work hours.
- Account content is intentionally an interim sign-in/navigation surface until Task 7 supplies the profile, favorites, and address page implementations.
- No live API, deployment, or production data was used.
