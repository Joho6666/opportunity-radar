import { describe, expect, it } from "vitest";
import { hasUntrustedNextHeaders } from "@/lib/local-request-guards";

describe("local request forwarding guards", () => {
  it.each(["127.0.0.1:3004", "localhost:3004"])("accepts Next.js loopback forwarding headers for %s", (host) => {
    const headers = new Headers({
      "x-forwarded-for": "127.0.0.1",
      "x-forwarded-host": host,
      "x-forwarded-port": "3004",
      "x-forwarded-proto": "http",
    });
    expect(hasUntrustedNextHeaders(headers, host, "http:")).toBe(false);
  });

  it.each([
    ["forwarded", "for=127.0.0.1;host=127.0.0.1:3004;proto=http"],
    ["x-real-ip", "127.0.0.1"],
    ["x-forwarded-for", "127.0.0.1, 203.0.113.12"],
    ["x-forwarded-host", "evil.example"],
    ["x-forwarded-port", "443"],
    ["x-forwarded-proto", "https"],
  ])("rejects untrusted %s", (name, value) => {
    expect(hasUntrustedNextHeaders(new Headers({ [name]: value }), "127.0.0.1:3004", "http:")).toBe(true);
  });
});
