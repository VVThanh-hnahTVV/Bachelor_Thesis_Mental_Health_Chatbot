/** Default English welcome when opening a new therapy chat. */
export function getDefaultLunaGreeting(displayName?: string | null): string {
  const name = displayName?.trim();
  if (name) {
    return (
      `Hello, ${name}! I'm Luna — your companion for emotional wellness. ` +
      "I'm glad you're here, and I'm ready to listen and support you at your own pace. " +
      "How are you feeling today?"
    );
  }
  return (
    "Hello! I'm Luna — your companion for emotional wellness. " +
    "I'm glad you're here, and I'm ready to listen and support you at your own pace. " +
    "How are you feeling today?"
  );
}
