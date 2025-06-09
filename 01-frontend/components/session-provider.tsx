"use client";

import { SessionProvider } from "next-auth/react";
import React from "react";

type Props = {
  children?: React.ReactNode;
};

export const NextAuthProvider = ({ children }: Props) => {
  // By default, NextAuth refetches the session when the window gains focus.
  // Setting `refetchOnWindowFocus` to `false` disables this behavior,
  // preventing re-renders when you switch back to the application tab.
  return <SessionProvider refetchOnWindowFocus={false}>{children}</SessionProvider>;
}; 