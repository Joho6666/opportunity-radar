const LOOPBACK_ADDRESSES = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

/**
 * Next.js adds these forwarding headers itself before middleware and route
 * handlers run. Accept only values that describe the direct loopback request;
 * reject standard proxy assertions and any mismatched forwarded destination.
 */
export function hasUntrustedNextHeaders(headers: Headers, expectedHost: string, expectedProtocol: string): boolean {
  if (headers.has("forwarded") || headers.has("x-real-ip")) return true;

  const forwardedHost = headers.get("x-forwarded-host");
  if (forwardedHost && forwardedHost.toLowerCase() !== expectedHost.toLowerCase()) return true;

  const expected = new URL(`${expectedProtocol}//${expectedHost}`);
  const forwardedProtocol = headers.get("x-forwarded-proto");
  if (forwardedProtocol && forwardedProtocol.toLowerCase().replace(/:$/, "") !== expected.protocol.slice(0, -1)) return true;

  const forwardedPort = headers.get("x-forwarded-port");
  if (forwardedPort && forwardedPort !== expected.port) return true;

  const forwardedFor = headers.get("x-forwarded-for");
  if (forwardedFor && forwardedFor.split(",").some((address) => !LOOPBACK_ADDRESSES.has(address.trim().toLowerCase()))) return true;

  return false;
}
