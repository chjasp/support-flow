'use client';

import { signOut } from 'next-auth/react';

export async function authFetch(
  session: { idToken?: string } | null | undefined,
  input: RequestInfo,
  init: RequestInit = {}
) {
  if (!session?.idToken) {
    throw new Error('Missing authentication token');
  }

  const resp = await fetch(input, {
    ...init,
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${session.idToken}`,
    },
  });

  if (resp.status === 401 || resp.status === 403) {
    console.error('Authentication failed, signing out');
    signOut();
  }

  return resp;
}
