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

  // ===== LOGGING POINT 1: Request Details =====
  console.log("===== FRONTEND PROXY DEBUG =====");
  console.log("Original URL path:", req.nextUrl.pathname);
  console.log("Backend URL:", backendUrl);
  console.log("Method:", req.method);
  console.log("Headers:", Object.fromEntries(req.headers.entries()));
  
  // Obtain an ID-token-enabled client for this backend URL
  const idTokenClient = await auth.getIdTokenClient(backendUrl);

  // Forward incoming headers to the backend, preserving content-type and others
  // the API depends on. We do **not** forward the Authorization header directly
  // because it will be overwritten by the ID token client. Instead, pass the
  // user's ID token in a custom header so the backend can verify it separately.
  const headers: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    // The Host header should not be forwarded as it would be incorrect for the backend
    if (lower === "host") return;
    if (lower === "authorization") return; // handled separately
    headers[key] = value;
  });

  // Forward the user's ID token using a custom header
  const userAuth = req.headers.get("authorization");
  if (userAuth) {
    headers["x-user-authorization"] = userAuth;
  }

  // Determine if the request has a body
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.clone().arrayBuffer() : undefined;
  
  // Convert body to appropriate format for the Google Auth library
  let requestData: any = undefined;
  if (body) {
    const contentType = req.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      // For JSON content, convert ArrayBuffer to string and then parse
      const bodyText = new TextDecoder().decode(body);
      try {
        requestData = JSON.parse(bodyText);
      } catch (e) {
        // If JSON parsing fails, send as string
        requestData = bodyText;
      }
    } else {
      // For non-JSON content, send as ArrayBuffer
      requestData = body;
    }
  }

  // ===== LOGGING POINT 2: Request Body =====
  if (body) {
    const bodyText = new TextDecoder().decode(body);
    console.log("Request body:", bodyText);
    try {
      const bodyJson = JSON.parse(bodyText);
      console.log("Parsed request body:", JSON.stringify(bodyJson, null, 2));
    } catch (e) {
      console.log("Could not parse body as JSON:", e);
    }
  }
  console.log("Final headers to backend:", headers);
  console.log("================================");

  try {
    // Make the request to the backend
    const backendResp = await idTokenClient.request({
      url: backendUrl,
      method: req.method as "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | "HEAD" | "OPTIONS",
      headers,
      data: requestData,
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
  } catch (error) {
    // ===== LOGGING POINT 3: Error Details =====
    console.log("===== BACKEND REQUEST ERROR =====");
    console.log("Error object:", error);
    if (error && typeof error === 'object') {
      console.log("Error keys:", Object.keys(error));
      if ('response' in error && error.response && typeof error.response === 'object') {
        console.log("Error response status:", (error.response as any).status);
        console.log("Error response data:", (error.response as any).data);
        console.log("Error response headers:", (error.response as any).headers);
      }
      if ('config' in error && error.config && typeof error.config === 'object') {
        console.log("Error config URL:", (error.config as any).url);
        console.log("Error config method:", (error.config as any).method);
        console.log("Error config data:", (error.config as any).data);
      }
    }
    console.log("==================================");
    const status = (error as any)?.response?.status || 500;
    const data = (error as any)?.response?.data || { message: "Proxy request failed" };
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
