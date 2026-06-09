/** Welcome when starting a medical-mode session. */
export function getDefaultMedicalGreeting(): string {
  return (
    "Hello! I'm Helios — your companion for health and wellness questions. " +
    "I'm here to help you understand symptoms, self-care, and health topics in clear, calm language. " +
    "What I share is for education and support only — not a diagnosis or prescription. " +
    "How can I support you today?"
  );
}

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
