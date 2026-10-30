import type { CapacitorConfig } from '@capacitor/cli'

// The Android app is a thin native shell around the live website, so it always runs the
// latest deployed version and talks to the API on the same origin (no CORS, no rebuilds
// for web changes). CAP_SERVER_URL is set by the GitHub Actions build from the stack output.
const serverUrl = process.env.CAP_SERVER_URL

const config: CapacitorConfig = {
  appId: 'com.spendathon.app',
  appName: 'spend-a-thon',
  webDir: 'dist',
  server: serverUrl
    ? { url: serverUrl, cleartext: false, errorPath: 'offline.html' }
    : undefined,
  android: {
    backgroundColor: '#0f766e',
    // Android 15 draws apps edge-to-edge; keep content clear of the status/nav bars.
    adjustMarginsForEdgeToEdge: 'auto',
  },
}

export default config
