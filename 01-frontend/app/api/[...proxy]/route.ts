import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

async function proxyRequest(req: NextRequest) {
  const apiBaseUrl = process.env.API_BASE_URL!;
  const path = req.nextUrl.pathname.replace(/^\/api\/?/, "");
  const backendUrl = `${apiBaseUrl}/${path}${req.nextUrl.search}`;

  // ===== LOGGING POINT 1: Request Details =====
  console.log("===== FRONTEND PROXY DEBUG =====");
  console.log("Original URL path:", req.nextUrl.pathname);
  console.log("Backend URL:", backendUrl);
  console.log("Method:", req.method);
  
  // Just forward incoming headers (keep Authorization!)
  const headers = new Headers(req.headers);
  headers.delete("host");               // Cloud Run doesn't like foreign hosts

  // Forward the user's ID token using a custom header
  const userAuth = req.headers.get("authorization");
  if (userAuth) {
    headers.append("x-user-authorization", userAuth);
  }

  // Prepare body
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.clone().arrayBuffer() : undefined;
  
  // No additional body transformation required — we'll forward it as-is.

  // ===== LOGGING POINT 2: Request Body =====
  if (body) {
    const bodyText = new TextDecoder().decode(body);
    console.log("Request body:", bodyText);
    
    // Only try to parse as JSON if the body is not empty
    if (bodyText.trim()) {
      try {
        const bodyJson = JSON.parse(bodyText);
        console.log("Parsed request body:", JSON.stringify(bodyJson, null, 2));
      } catch (e) {
        console.log("Could not parse body as JSON:", e);
      }
    } else {
      console.log("Request body is empty, skipping JSON parsing");
    }
  }
  console.log("================================");

  try {
    // Make the request to the backend
    const backendResp = await fetch(backendUrl, {
      method: req.method,
      headers,
      body: body ? body : undefined,
    });

    // Forward the backend response to the client
    // Handle 204 No Content responses (common for DELETE operations)
    if (backendResp.status === 204) {
      return new NextResponse(null, {
        status: 204,
        headers: Object.fromEntries(
          Object.entries(backendResp.headers).map(([key, value]) => [
            key,
            Array.isArray(value) ? value.join(', ') : String(value)
          ])
        )
      });
    }

    return new NextResponse(backendResp.body, {
      status: backendResp.status,
      headers: backendResp.headers,       // will include content-type, etc.
    });
  } catch (error: unknown) {
    // ===== LOGGING POINT 3: Error Details =====
    console.log("===== BACKEND REQUEST ERROR =====");
    console.log("Error object:", error);
    if (error && typeof error === 'object') {
      console.log("Error keys:", Object.keys(error));

      type ErrorWithConfig = {
        response?: {
          status?: number;
          data?: unknown;
          headers?: unknown;
        };
        config?: {
          url?: string;
          method?: string;
          data?: unknown;
        };
      };

      const err = error as ErrorWithConfig;

      if (err.response) {
        console.log("Error response status:", err.response.status);
        console.log("Error response data:", err.response.data);
        console.log("Error response headers:", err.response.headers);
      }
      if (err.config) {
        console.log("Error config URL:", err.config.url);
        console.log("Error config method:", err.config.method);
        console.log("Error config data:", err.config.data);
      }
    }
    console.log("==================================");
    const errResp = error as { response?: { status?: number; data?: unknown } };
    const status = errResp.response?.status ?? 500;
    const data = errResp.response?.data ?? { message: "Proxy request failed" };
    return new NextResponse(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export async function GET(req: NextRequest) {
  return proxyRequest(req);
}

export async function POST(req: NextRequest) {
  return proxyRequest(req);
}

export async function PUT(req: NextRequest) {
  return proxyRequest(req);
}

export async function DELETE(req: NextRequest) {
  return proxyRequest(req);
}

export async function PATCH(req: NextRequest) {
  return proxyRequest(req);
}
