// Matches the API's rolling 30-day refresh-token lifetime. Access tokens
// remain short-lived; the refresh cookie restores a session after a break.
export const REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30;
