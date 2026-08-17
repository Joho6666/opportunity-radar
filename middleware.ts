import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const protectedPrefixes = ["/dashboard", "/opportunities", "/radars", "/daily-brief", "/pipeline", "/saved", "/skills", "/profile", "/settings"];

export async function middleware(request: NextRequest) {
  // 演示模式（未关闭 Mock）下不做路由保护，保证开箱即用。
  if (process.env.NEXT_PUBLIC_USE_MOCK !== "false") return NextResponse.next();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) return NextResponse.next();

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
  const { data: { session } } = await supabase.auth.getSession();
  const path = request.nextUrl.pathname;
  const needsAuth = protectedPrefixes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
  if (needsAuth && !session) { const redirect = request.nextUrl.clone(); redirect.pathname = "/login"; return NextResponse.redirect(redirect); }
  if (session && path === "/login") { const redirect = request.nextUrl.clone(); redirect.pathname = "/dashboard"; return NextResponse.redirect(redirect); }
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|screenshots|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js|map)$).*)"] };
