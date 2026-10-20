// Shared state of the Telegram sign-in (see telegramSession.ts). Kept free of imports so the
// test setup can reset it without loading the Telegram bridge or the stores it touches.

export const telegramSessionState: { inFlight: Promise<boolean> | null; lastFailureAt: number } = {
  inFlight: null,
  lastFailureAt: 0,
};

/** Test helper: forget the in-flight request and the last refusal between tests. */
export function resetTelegramSessionForTests(): void {
  telegramSessionState.inFlight = null;
  telegramSessionState.lastFailureAt = 0;
}
