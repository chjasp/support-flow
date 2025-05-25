import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { GoogleAuth } from "google-auth-library";

const auth = new GoogleAuth();

async function proxyRequest(req: NextRequest) {
  // Read the API base URL from environment variables
  const apiBaseUrl: string | undefined = process.env.API_BASE_URL;

  // Ensure the API base URL is configured
  if (!apiBaseUrl) {
    console.error("API_BASE_URL environment variable is not set.");
    return new NextResponse("Internal Server Error: API configuration missing.", {
      status: 500,
    });
  }

  // Strip the /api prefix and rebuild the backend URL
  const path = req.nextUrl.pathname.replace(/^\/api\/?/, "");
  const backendUrl = `${apiBaseUrl}/${path}${req.nextUrl.search}`;

  // Obtain an ID-token-enabled client for this backend URL
  const idTokenClient = await auth.getIdTokenClient(backendUrl);

  // Forward incoming headers to the backend, preserving content-type and others
  // the API depends on. We explicitly forward the authorization header if present.
  const headers: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    // The Host header should not be forwarded as it would be incorrect for the backend
    if (key.toLowerCase() === "host") return;
    headers[key] = value;
  });

  // Ensure we forward the user's ID token if provided
  const userAuth = req.headers.get("authorization");
  if (userAuth) {
    headers["authorization"] = userAuth;
  }

  // Determine if the request has a body
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.clone().arrayBuffer() : undefined;

  // Make the request to the backend
  const backendResp = await idTokenClient.request({
    url: backendUrl,
    method: req.method as "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | "HEAD" | "OPTIONS",
    headers,
    data: body,
  });

  // Forward the backend response to the client
  return new NextResponse(JSON.stringify(backendResp.data), {
    status: backendResp.status,
    headers: {
      'Content-Type': 'application/json',
      ...Object.fromEntries(
        Object.entries(backendResp.headers).map(([key, value]) => [
          key,
          Array.isArray(value) ? value.join(', ') : String(value)
        ])
      )
    },
  });
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
