import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const protectedPrefixes = ["/evidence", "/dashboard", "/opportunities", "/radars", "/daily-brief", "/pipeline", "/saved", "/skills", "/profile", "/settings"];

export async function middleware(request: NextRequest) {
  // Next dev adds x-forwarded-for from its socket. Bind dev to loopback; the API
  // independently rejects every proxy header. Production never uses this UI bypass.
  if (process.env.NEXT_PUBLIC_AUTH_DISABLED === "true" && process.env.NODE_ENV === "development" && ["localhost", "127.0.0.1", "[::1]"].includes(request.nextUrl.hostname) && !["forwarded", "x-real-ip"].some(h => request.headers.has(h)) && (request.headers.get("x-forwarded-for") ?? "127.0.0.1").split(",").every(peer => ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(peer.trim()))) return NextResponse.next();
  // 演示模式（未关闭 Mock）下不做路由保护，保证开箱即用。
  if (process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_USE_MOCK === "true") return NextResponse.next();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    if (protectedPrefixes.some(prefix => request.nextUrl.pathname === prefix || request.nextUrl.pathname.startsWith(`${prefix}/`))) return NextResponse.redirect(new URL("/login", request.url));
    return NextResponse.next();
  }

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (cookiesToSet) => {
        for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) response.cookies.set(name, value, options);
      },
    },
  });
  const { data: { user } } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;
  const needsAuth = protectedPrefixes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
  if (needsAuth && !user) { const redirect = request.nextUrl.clone(); redirect.pathname = "/login"; return NextResponse.redirect(redirect); }
  if (user && path === "/login") { const redirect = request.nextUrl.clone(); redirect.pathname = "/dashboard"; return NextResponse.redirect(redirect); }
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|screenshots|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js|map)$).*)"] };
