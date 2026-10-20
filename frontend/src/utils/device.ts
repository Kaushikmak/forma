const DEVICE_ID_KEY = "forma_device_id";

export function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") {
    return "client-device-id";
  }

  // localStorage
  let deviceId: string | null = null;
  try {
    deviceId = localStorage.getItem(DEVICE_ID_KEY);
  } catch {
    // localStorage might be blocked in strict mode
  }

  // cookie
  if (!deviceId) {
    const match = document.cookie
      .split(";")
      .map((c) => c.trim())
      .find((c) => c.startsWith(`${DEVICE_ID_KEY}=`));
    if (match) {
      deviceId = match.split("=")[1];
    }
  }

  // Generate if absent
  if (!deviceId || deviceId.trim().length === 0) {
    deviceId =
      typeof crypto?.randomUUID === "function"
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2) + Date.now().toString(36);
  }

  // Persist to both localStorage & cookie
  try {
    localStorage.setItem(DEVICE_ID_KEY, deviceId);
  } catch {
    // ignore
  }

  try {
    document.cookie = `${DEVICE_ID_KEY}=${deviceId}; Path=/; Max-Age=31536000; SameSite=Lax`;
  } catch {
    // ignore
  }

  return deviceId;
}
